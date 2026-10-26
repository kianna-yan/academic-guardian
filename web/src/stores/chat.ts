import { defineStore } from "pinia";
import { ref } from "vue";
import { chatStream } from "@/api/client";
import type { ChatTrace, Citation, Role } from "@/types";

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
};

export const DEFAULT_SUGGEST: Record<Role, string[]> = {
  student: ["我的风险分为什么这么高？", "这学期还来得及吗？", "挂多少学分会被降级？"],
  counselor: ["本班谁的风险上升最快？", "哪些班级红色预警最多？", "这周该找谁谈话？"],
  admin: ["全校风险分布如何？", "哪些班级问题最集中？", "缺勤和挂科是什么关系？"],
  parent: ["孩子这学期情况怎么样？", "学校什么情况下会通知家长？", "他还来得及毕业吗？"],
};

export const useChatStore = defineStore("chat", () => {
  /** 对话是主入口：chat = 整页 AI 问答（默认），dash = 数据看板 */
  const homeMode = ref<"chat" | "dash">("chat");
  const messages = ref<ChatMessage[]>([]);
  const suggestions = ref<string[]>([]);
  const streaming = ref(false);
  const currentRole = ref<Role | null>(null);

  let seq = 0;
  // 在途请求的取消句柄：切端 / 关面板 / 组件卸载时都要掐断，否则流还在往已卸载的组件里写
  let inflight: AbortController | null = null;

  function abort() {
    if (inflight) {
      inflight.abort();
      inflight = null;
    }
    streaming.value = false;
  }

  function greeting(role: Role) {
    return {
      id: ++seq,
      from: "assistant" as const,
      text: GREETING[role],
      trace: [],
      citations: [],
      thoughts: [],
    };
  }

  /** 切换端时重置会话，避免把学生端的上下文带进家长端 */
  function reset(role: Role) {
    abort();
    currentRole.value = role;
    messages.value = [greeting(role)];
    suggestions.value = [...DEFAULT_SUGGEST[role]];
    homeMode.value = "chat";
  }

  function ensure(role: Role) {
    if (currentRole.value !== role) reset(role);
  }

  async function send(role: Role, sid: string | null, text: string) {
    const content = text.trim();
    if (!content || streaming.value) return;
    ensure(role);

    messages.value.push({ id: ++seq, from: "user", text: content, trace: [], citations: [], thoughts: [] });
    messages.value.push({
      id: ++seq,
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
    }
  }

  /** 页面上任何位置的「问 AI」都走这里：回到整页对话并直接发问 */
  function ask(role: Role, sid: string | null, question: string) {
    homeMode.value = "chat";
    void send(role, sid, question);
  }

  return { homeMode, messages, suggestions, streaming, send, reset, ensure, abort, ask };
});
