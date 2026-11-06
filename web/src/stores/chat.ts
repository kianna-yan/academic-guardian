import { defineStore } from "pinia";
import { ref } from "vue";
import { chatStream, api, type MediaPayload } from "@/api/client";
import type { PickedMedia } from "@/composables/media";
import type { ChatTrace, Citation, Role } from "@/types";
import { useAuthStore } from "@/stores/auth";

export interface ChatMessage {
  id: number;
  from: "user" | "assistant";
  text: string;
  trace: ChatTrace[];
  citations: Citation[];
  /** 思考链：实时推过来的推理过程，pending 时也在长 */
  thoughts: string[];
  /** 这条消息带的图片 / 视频 / 语音（只留缩略图与转写，不存原始 base64） */
  media?: ChatMedia[];
  intent?: string;
  elapsed?: number;
  pending?: boolean;
  error?: string;
}

/** 气泡里回显附件用的轻量结构：大块 base64 不进 localStorage */
export interface ChatMedia {
  kind: "image" | "video" | "audio" | "text";
  name: string;
  thumb?: string;
  duration?: number;
  transcript?: string;
  /** kind=text（上传文档）时抽出来的字数 */
  chars?: number;
}

const GREETING: Record<Role, string> = {
  student: "我是你的学业助手。可以问我风险分怎么来的、哪门课最危险、这学期还来不来得及。",
  counselor: "我是辅导员助手。可以问「本班谁风险上升最快」，或让我给某个学生生成谈话要点。",
  admin: "我是教务助手。可以问全校分布、班级对比，或某条校规的具体规定。",
  parent: "我是家校助手。可以问孩子这学期的情况，或学校什么情况下会通知家长。",
  teacher: "我是你的教学助手。可以问「我课上的学生」「谁的风险最高」「班均多少」「我该重点关注谁」。",
};

export const DEFAULT_SUGGEST: Record<Role, string[]> = {
  student: ["我的风险分为什么这么高？", "这学期还来得及吗？", "挂多少学分会被降级？"],
  counselor: ["本班谁的风险上升最快？", "哪些班级红色预警最多？", "这周该找谁谈话？"],
  admin: ["全校风险分布如何？", "哪些班级问题最集中？", "缺勤和挂科是什么关系？"],
  parent: ["孩子这学期情况怎么样？", "学校什么情况下会通知家长？", "他还来得及毕业吗？"],
  teacher: ["我课上的学生", "谁的风险最高？", "我该重点关注谁？"],
};

/* ------------------------------------------------------------------
 * 五端 AI 完全分离：
 * - 会话按「角色:账号」各自独立存储（localStorage），学生 A 的对话
 *   学生 B 看不到，学生端与导员端更是两套互不相通的会话；
 * - 后端 system prompt 也按角色分四套人设（见 engine/agent.py PERSONAS），
 *   同一个问题在五个端会得到各自视角的回答。
 * ---------------------------------------------------------------- */
const MSG_CAP = 40; // 每个会话最多保留多少条

function sessionKey(role: Role, account: string): string {
  return `ag.chat.${role}.${account}`;
}

function loadSession(role: Role, account: string): ChatMessage[] {
  try {
    const raw = localStorage.getItem(sessionKey(role, account));
    if (!raw) return [];
    const rows = JSON.parse(raw) as ChatMessage[];
    return Array.isArray(rows) ? rows : [];
  } catch {
    return [];
  }
}

function saveSession(role: Role, account: string, msgs: ChatMessage[]): void {
  try {
    localStorage.setItem(sessionKey(role, account), JSON.stringify(msgs.slice(-MSG_CAP)));
  } catch {
    /* 存储满就放弃持久化，对话照常 */
  }
}

function clearSession(role: Role, account: string): void {
  try {
    localStorage.removeItem(sessionKey(role, account));
  } catch {
    /* 忽略 */
  }
}

export const useChatStore = defineStore("chat", () => {
  const auth = useAuthStore();
  /**
   * AI 抽屉是否展开。
   * 端口首屏先给图形门户，AI 收在最下方那条输入条里；点一下向上铺满，
   * 收起后原样退回。对话本身不随抽屉开关丢失（消息在 store 里）。
   */
  const aiOpen = ref(false);
  const messages = ref<ChatMessage[]>([]);
  const suggestions = ref<string[]>([]);
  /**
   * 当前这批建议词属于哪个端。
   * 建议词会被后端按上下文改写，也可能留着上一个端的状态；
   * 记住出处，页面就能在角色对不上时立刻换回本端的默认提问，不会串端。
   */
  const suggRole = ref<Role | null>(null);
  const streaming = ref(false);
  const currentKey = ref<string | null>(null);

  let inflightSeq = 0;
  // 在途请求的取消句柄：切端 / 关面板 / 组件卸载时都要掐断，否则流还在往已卸载的组件里写
  let inflight: AbortController | null = null;

  /** id 生成器：时间戳打底，恢复的旧消息（小数字 id）不会撞车 */
  function nextId(): number {
    return Date.now() + ++inflightSeq;
  }

  function abort() {
    if (inflight) {
      inflight.abort();
      inflight = null;
    }
    streaming.value = false;
  }

  function greeting(role: Role) {
    return {
      id: nextId(),
      from: "assistant" as const,
      text: GREETING[role],
      trace: [],
      citations: [],
      thoughts: [],
    };
  }

  /** 建议词统一从这里落库，顺手记下它属于哪个端，避免端与端之间互相串 */
  function setSuggest(role: Role, list?: string[]) {
    suggestions.value = list?.length ? [...list] : [...DEFAULT_SUGGEST[role]];
    suggRole.value = role;
  }

  /**
   * 切到某端的会话：key = 角色:账号。
   * 同一角色换账号登录也会换会话（修复旧版"同端换人看到上一人对话"的问题）。
   */
  function ensure(role: Role) {
    const account = auth.profile?.account || "anon";
    const key = `${role}:${account}`;
    if (currentKey.value === key) {
      // 会话没变但建议词是别的端留下的（登录跳转顺序会打断 store 的初始化），就地纠正
      if (suggRole.value !== role) setSuggest(role);
      return;
    }
    abort();
    currentKey.value = key;
    const saved = loadSession(role, account);
    if (saved.length) {
      // 恢复历史：把恢复流里可能残留的 pending 标记清掉
      saved.forEach((m) => (m.pending = false));
      messages.value = saved;
    } else {
      messages.value = [greeting(role)];
    }
    setSuggest(role);
  }

  /** 清空当前端的会话（换个思路重新聊）：后端记忆 + 本地存档一起清 */
  async function reset(role: Role) {
    const account = auth.profile?.account || "anon";
    abort();
    clearSession(role, account);
    currentKey.value = `${role}:${account}`;
    messages.value = [greeting(role)];
    setSuggest(role);
    try {
      await api.resetAgent();          // 后端会话记忆一并清掉
    } catch {
      /* 后端不可达时本地已清，够用 */
    }
  }

  async function send(
    role: Role,
    sid: string | null,
    text: string,
    attachments: PickedMedia[] = [],
    skill?: { key: string; sub?: string | null } | null,
  ) {
    const content = text.trim();
    const media = attachments.filter(Boolean);
    if (!content && !media.length) return;
    if (streaming.value) return;
    ensure(role);
    const account = auth.profile?.account || "anon";

    // 气泡里只回显缩略图与转写文字，原始 base64 留在本次请求里，不进会话存档
    const echo: ChatMedia[] = media.map((m) => ({
      kind: m.kind,
      name: m.name,
      thumb: m.thumb,
      duration: m.duration,
      transcript: m.transcript,
      chars: m.chars,
    }));

    messages.value.push({
      id: nextId(),
      from: "user",
      text: content,
      trace: [],
      citations: [],
      thoughts: [],
      media: echo.length ? echo : undefined,
    });
    messages.value.push({
      id: nextId(),
      from: "assistant",
      text: "",
      trace: [],
      citations: [],
      thoughts: [],
      pending: true,
    });

    // 注意：必须拿数组里那个响应式代理再改，直接改 push 进去的原始对象不会触发重渲染
    const reply = messages.value[messages.value.length - 1];
    streaming.value = true;
    inflight = new AbortController();

    const payload: MediaPayload[] = media.map((m) => ({
      kind: m.kind,
      name: m.name,
      mime: m.mime,
      data: m.data,
      frames: m.frames,
      duration: m.duration,
      transcript: m.transcript,
    }));

    try {
      await chatStream(
        {
          role,
          sid,
          message: content || (media.length ? "看看我发的这个" : ""),
          attachments: payload.length ? payload : undefined,
          // 技能这一轮由后端按技能组织回答，不再让意图打分去猜预填的话
          skill: skill?.key || undefined,
          sub: skill?.sub || undefined,
        },
        (ev) => {
        switch (ev.type) {
          case "meta":
            reply.intent = ev.intent;
            break;
          case "thought":
            reply.thoughts.push(ev.text);
            break;
          case "tool":
            reply.trace.push(ev.trace);
            break;
          case "delta":
            reply.text += ev.text;
            break;
          case "citations":
            reply.citations = ev.citations || [];
            break;
          case "suggestions":
            if (ev.suggestions?.length) setSuggest(role, ev.suggestions);
            break;
          case "done":
            reply.elapsed = ev.elapsed_ms;
            break;
          case "error":
            reply.error = ev.message;
            break;
        }
      }, inflight.signal);
    } catch (e: any) {
      // 主动取消不算错误：保持已收到的半截内容，不要再报红
      if (e?.name !== "AbortError") reply.error = e?.message || "对话失败";
    } finally {
      inflight = null;
      reply.pending = false;
      if (!reply.text && !reply.error) reply.error = "没有拿到回答，请稍后再试。";
      streaming.value = false;
      saveSession(role, account, messages.value);
    }
  }

  /** 页面上任何位置的「问 AI」都走这里：展开抽屉并直接发问 */
  function ask(role: Role, sid: string | null, question: string) {
    aiOpen.value = true;
    void send(role, sid, question);
  }

  function openAi() {
    aiOpen.value = true;
  }

  function closeAi() {
    aiOpen.value = false;
  }

  return {
    aiOpen,
    messages,
    suggestions,
    suggRole,
    streaming,
    send,
    reset,
    ensure,
    abort,
    ask,
    openAi,
    closeAi,
  };
});
