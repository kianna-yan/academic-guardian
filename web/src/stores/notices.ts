import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { api } from "@/api/client";
import type { MessageThread, NoticeItem, TodoItem } from "@/types";
import { useAuthStore } from "@/stores/auth";

const POLL_MS = 25_000;

/**
 * 消息中心：各端各自的通知与待办 + 家长端↔辅导员端双向消息。
 * - 登录后立即拉一次，之后每 25 秒轮询；
 * - 有新的未读通知时触发 onArrive 回调（App.vue 用来弹窗）；
 * - 通知/待办按「角色:账号」在后端隔离，前端只管展示与已读。
 * - 家长端和辅导员端额外拉取双向消息（家校沟通）。
 */
export const useNoticeStore = defineStore("notices", () => {
  const auth = useAuthStore();
  const unread = ref<NoticeItem[]>([]);
  const todos = ref<TodoItem[]>([]);
  const panelOpen = ref(false);
  const tab = ref<"notice" | "todo" | "appeals" | "message">("notice");

  // 家校双向消息
  const threads = ref<MessageThread[]>([]);
  const activeThread = ref<string>("");   // 导员端当前选中的会话 sid
  const sending = ref(false);

  let timer: number | null = null;
  let seen = new Set<string>();       // 已经弹过窗的通知 id，避免重复弹
  let lastKey = "";                   // 登录身份变了要重置
  const listeners = new Set<(items: NoticeItem[]) => void>();

  const unreadCount = computed(() => unread.value.length);
  /** 面板只列「还没做的」：勾掉的待办直接消失，而不是留在列表里划横线 */
  const openTodos = computed(() => todos.value.filter((t) => !t.done));
  const todoCount = computed(() => openTodos.value.length);
  const messageUnread = computed(() =>
    threads.value.reduce((s, t) => s + t.unread, 0),
  );
  // 家校消息仅家长端和辅导员端可用
  const canMessage = computed(
    () => auth.profile?.role === "parent" || auth.profile?.role === "counselor",
  );

  function onArrive(fn: (items: NoticeItem[]) => void): () => void {
    listeners.add(fn);
    return () => listeners.delete(fn);
  }

  async function refreshMessages(silent = false) {
    if (!canMessage.value) {
      threads.value = [];
      return;
    }
    try {
      const data = await api.messages();
      threads.value = data.threads || [];
      // 家长端只有一条线，自动选中
      if (auth.profile?.role === "parent" && threads.value[0]) {
        activeThread.value = threads.value[0].sid;
      }
      // 不再在这里合成“发来家校消息”的弹窗推送：
      // 后端 MESSAGES.send 已经通过 NOTIFS.push 推过一份 family_message 通知，
      // refresh() 拉到 unread 时会经 onArrive 弹一次窗。以前这里再推一份会
      // 导致同一封家校消息弹两个标题不同的窗（“发来一条消息” + “发来家校消息”）。
    } catch {
      /* 轮询失败静默 */
    }
  }

  async function refresh(silent = false) {
    const profile = auth.profile;
    if (!profile) return;
    const key = `${profile.role}:${profile.account}`;
    if (key !== lastKey) {
      lastKey = key;
      seen = new Set();               // 换了身份，弹窗历史清零
      threads.value = [];
      activeThread.value = "";
    }
    try {
      const data = await api.notifications();
      const fresh = (data.unread || []).filter((n) => !seen.has(n.id));
      unread.value = data.unread || [];
      todos.value = data.todos || [];
      if (fresh.length && !silent) {
        fresh.forEach((n) => seen.add(n.id));
        listeners.forEach((fn) => fn(fresh));
      }
    } catch {
      /* 轮询失败静默，下轮再试 */
    }
    // 家长/导员顺便拉消息
    void refreshMessages(silent);
  }

  function start() {
    stop();
    void refresh();
    timer = window.setInterval(() => void refresh(), POLL_MS);
  }

  function stop() {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  }

  async function markRead(ids: string[]) {
    if (!ids.length) return;
    try {
      await api.markNoticesRead(ids);
      unread.value = unread.value.filter((n) => !ids.includes(n.id));
    } catch {
      /* 忽略 */
    }
  }

  async function finishTodo(id: string) {
    const row = todos.value.find((t) => t.id === id);
    if (!row || row.done) return;
    row.done = true;                    // 先乐观置灰，接口回来再从列表里摘掉
    try {
      await api.finishTodo(id);
      // 勾掉就消失：待办列表是「还欠着的事」，做完了不该继续占位。
      // 以前只把 done 置 true，模板照样渲染出来划一道横线，看着像没生效。
      const at = todos.value.findIndex((t) => t.id === id);
      if (at >= 0) todos.value.splice(at, 1);
    } catch {
      row.done = false;
    }
  }

  async function sendMessage(sid: string, text: string) {
    if (!text.trim()) return;
    sending.value = true;
    try {
      await api.sendMessage(sid, text);
      await refreshMessages(true);
    } finally {
      sending.value = false;
    }
  }

  async function markThreadRead(threadId: string) {
    try {
      await api.markMessagesRead(threadId);
      const t = threads.value.find((x) => x.thread_id === threadId);
      if (t) t.unread = 0;
    } catch {
      /* 忽略 */
    }
  }

  function openPanel(which: "notice" | "todo" | "appeals" | "message" = "notice") {
    tab.value = which;
    panelOpen.value = true;
    // 打开面板永远先拉一次：别的端刚推过来的通知要当场看到，
    // 不能等 25 秒那一轮轮询。
    void refresh(true);
    if (which === "message") void refreshMessages(true);
  }

  return {
    unread, todos, openTodos, unreadCount, todoCount,
    panelOpen, tab,
    threads, activeThread, messageUnread, canMessage, sending,
    refresh, start, stop, markRead, finishTodo, onArrive, openPanel,
    sendMessage, markThreadRead, refreshMessages,
  };
});
