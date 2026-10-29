import { defineStore } from "pinia";
import { ref } from "vue";
import { chatStream, api } from "@/api/client";
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
  intent?: string;
  elapsed?: number;
  pending?: boolean;
  error?: string;
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
 * 四端 AI 完全分离：
 * - 会话按「角色:账号」各自独立存储（localStorage），学生 A 的对话
 *   学生 B 看不到，学生端与导员端更是两套互不相通的会话；
 * - 后端 system prompt 也按角色分四套人设（见 engine/agent.py PERSONAS），
 *   同一个问题在四个端会得到各自视角的回答。
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
  /** 对话是主入口：chat = 整页 AI 问答（默认），dash = 数据看板 */
  const homeMode = ref<"chat" | "dash">("chat");
  const messages = ref<ChatMessage[]>([]);
  const suggestions = ref<string[]>([]);
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

  /**
   * 切到某端的会话：key = 角色:账号。
   * 同一角色换账号登录也会换会话（修复旧版"同端换人看到上一人对话"的问题）。
   */
  function ensure(role: Role) {
    const account = auth.profile?.account || "anon";
    const key = `${role}:${account}`;
    if (currentKey.value === key) return;
    abort();
    currentKey.value = key;
    const saved = loadSession(role, account);
    if (saved.length) {
      // 恢复历史：把恢复流里可能残留的 pending 标记清掉
      saved.forEach((m) => (m.pending = false));
      messages.value = saved;
      suggestions.value = [...DEFAULT_SUGGEST[role]];
    } else {
      messages.value = [greeting(role)];
      suggestions.value = [...DEFAULT_SUGGEST[role]];
    }
    homeMode.value = "chat";
  }

  /** 清空当前端的会话（换个思路重新聊）：后端记忆 + 本地存档一起清 */
  async function reset(role: Role) {
    const account = auth.profile?.account || "anon";
    abort();
    clearSession(role, account);
    currentKey.value = `${role}:${account}`;
    messages.value = [greeting(role)];
    suggestions.value = [...DEFAULT_SUGGEST[role]];
    homeMode.value = "chat";
    try {
      await api.resetAgent();          // 后端会话记忆一并清掉
    } catch {
      /* 后端不可达时本地已清，够用 */
    }
  }

  async function send(role: Role, sid: string | null, text: string) {
    const content = text.trim();
    if (!content || streaming.value) return;
    ensure(role);
    const account = auth.profile?.account || "anon";

    messages.value.push({ id: nextId(), from: "user", text: content, trace: [], citations: [], thoughts: [] });
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

    try {
      await chatStream({ role, sid, message: content }, (ev) => {
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
            if (ev.suggestions?.length) suggestions.value = ev.suggestions;
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

  /** 页面上任何位置的「问 AI」都走这里：回到整页对话并直接发问 */
  function ask(role: Role, sid: string | null, question: string) {
    homeMode.value = "chat";
    void send(role, sid, question);
  }

  return { homeMode, messages, suggestions, streaming, send, reset, ensure, abort, ask };
});
