import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { api } from "@/api/client";
import type { NoticeItem, TodoItem } from "@/types";
import { useAuthStore } from "@/stores/auth";

const POLL_MS = 25_000;

/**
 * 消息中心：四端各自的通知与待办。
 * - 登录后立即拉一次，之后每 25 秒轮询；
 * - 有新的未读通知时触发 onArrive 回调（App.vue 用来弹窗）；
 * - 通知/待办按「角色:账号」在后端隔离，前端只管展示与已读。
 */
export const useNoticeStore = defineStore("notices", () => {
  const auth = useAuthStore();
  const unread = ref<NoticeItem[]>([]);
  const todos = ref<TodoItem[]>([]);
  const panelOpen = ref(false);
  const tab = ref<"notice" | "todo" | "appeals">("notice");

  let timer: number | null = null;
  let seen = new Set<string>();       // 已经弹过窗的通知 id，避免重复弹
  let lastKey = "";                   // 登录身份变了要重置
  const listeners = new Set<(items: NoticeItem[]) => void>();

  const unreadCount = computed(() => unread.value.length);
  const todoCount = computed(() => todos.value.filter((t) => !t.done).length);

  function onArrive(fn: (items: NoticeItem[]) => void): () => void {
    listeners.add(fn);
    return () => listeners.delete(fn);
  }

  async function refresh(silent = false) {
    const profile = auth.profile;
    if (!profile) return;
    const key = `${profile.role}:${profile.account}`;
    if (key !== lastKey) {
      lastKey = key;
      seen = new Set();               // 换了身份，弹窗历史清零
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
    row.done = true;                    // 乐观更新，失败再回滚
    try {
      await api.finishTodo(id);
    } catch {
      row.done = false;
    }
  }

  function openPanel(which: "notice" | "todo" | "appeals" = "notice") {
    tab.value = which;
    panelOpen.value = true;
  }

  return {
    unread, todos, unreadCount, todoCount,
    panelOpen, tab,
    refresh, start, stop, markRead, finishTodo, onArrive, openPanel,
  };
});
