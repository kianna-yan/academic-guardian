<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus/es/components/message/index";
import { useAuthStore } from "@/stores/auth";
import { useNoticeStore } from "@/stores/notices";

/**
 * 家校沟通独立整页：家长端 ↔ 辅导员端双向对话。
 *
 * - 家长端：只有一个会话（和自家孩子的辅导员），左侧不显示列表
 * - 辅导员端：左侧按学生列出所有家长会话，点谁和谁聊；带搜索框快速跳到某学生
 * - 对话头部显示对方联系方式（电话），方便双方互相找
 * - 复用 notices store 的 threads / sendMessage / markThreadRead
 */
const auth = useAuthStore();
const notices = useNoticeStore();
const route = useRoute();
const router = useRouter();

const role = computed(() => auth.profile?.role || "");
const isParent = computed(() => role.value === "parent");
const isCounselor = computed(() => role.value === "counselor");

// 当前展示的会话（家长端唯一一条；导员端选中的那条）
const currentThread = computed(() => {
  if (isParent.value) return notices.threads[0] || null;
  if (isCounselor.value) {
    return (
      notices.threads.find((t) => t.sid === notices.activeThread) ||
      notices.threads[0] ||
      null
    );
  }
  return null;
});

const draft = ref("");
const bodyRef = ref<HTMLDivElement | null>(null);
// 导员端会话搜索关键字（按学生姓名/学号/班级过滤）
const kw = ref("");

const filteredThreads = computed(() => {
  const q = kw.value.trim();
  if (!q) return notices.threads;
  return notices.threads.filter((t) =>
    (t.student_name || t.peer_name).includes(q) ||
    t.sid.includes(q) ||
    (t.student_class || "").includes(q),
  );
});

function selectThread(sid: string) {
  notices.activeThread = sid;
  const t = notices.threads.find((x) => x.sid === sid);
  if (t && t.unread > 0) void notices.markThreadRead(t.thread_id);
  // 选完滚到底部
  nextTick(scrollBottom);
}

async function send() {
  const text = draft.value.trim();
  if (!text || !currentThread.value) return;
  const sid = currentThread.value.sid;
  try {
    await notices.sendMessage(sid, text);
    draft.value = "";
    await nextTick();
    scrollBottom();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "发送失败");
  }
}

function scrollBottom() {
  if (bodyRef.value) bodyRef.value.scrollTop = bodyRef.value.scrollHeight;
}

// 进入页面就拉一次消息并标已读
onMounted(async () => {
  await notices.refreshMessages(true);
  // 路由带了 sid 时（从辅导员端学生抽屉跳来）自动选中
  const wantSid = (route.query.sid as string) || "";
  if (wantSid && isCounselor.value) {
    const hit = notices.threads.find((t) => t.sid === wantSid);
    if (hit) notices.activeThread = hit.sid;
  }
  await nextTick();
  scrollBottom();
  if (currentThread.value && currentThread.value.unread > 0) {
    void notices.markThreadRead(currentThread.value.thread_id);
  }
});

// route.query.sid 变化时也跟随（同一组件实例下从辅导员端跳来）
watch(
  () => route.query.sid,
  (sid) => {
    if (sid && isCounselor.value) {
      const hit = notices.threads.find((t) => t.sid === sid);
      if (hit) notices.activeThread = hit.sid;
      nextTick(scrollBottom);
    }
  },
);

function backHome() {
  router.push(auth.home());
}
</script>

<template>
  <div class="msg-page">
    <!-- 顶栏已显示路由 title 与 sub，这里只放返回按钮，不再重复副标题 -->
    <div class="msg-head">
      <span class="muted tiny">
        <template v-if="isParent">下方是与孩子辅导员的对话</template>
        <template v-else>左侧按风险排序，红黄学生优先联系；可搜索任意学生</template>
      </span>
      <button class="btn ghost" @click="backHome">返回工作台</button>
    </div>

    <div v-if="!notices.canMessage" class="msg-empty">
      家校沟通仅家长端和辅导员端可用。
    </div>

    <div v-else class="msg-layout">
      <!-- 导员端：会话列表 + 搜索 -->
      <aside v-if="isCounselor" class="thread-list">
        <div class="thread-list-head">
          <span>风险学生优先</span>
          <em>{{ notices.threads.length }} 位学生</em>
        </div>
        <div class="thread-search">
          <input v-model="kw" placeholder="搜姓名 / 学号 / 班级" />
        </div>
        <div v-if="!filteredThreads.length" class="thread-empty">
          没找到匹配的学生
        </div>
        <div class="thread-scroll">
          <button
            v-for="t in filteredThreads"
            :key="t.thread_id"
            class="thread-row"
            :class="[{ on: t.sid === (currentThread?.sid || '') }, t.level || 'green']"
            @click="selectThread(t.sid)"
          >
            <div class="thread-row-top">
              <span class="lv-dot" :class="t.level || 'green'" :title="t.top_factor"></span>
              <b>{{ t.student_name || t.peer_name }}</b>
              <span v-if="t.unread" class="dot">{{ t.unread }}</span>
            </div>
            <div class="thread-row-meta">
              <span class="thread-cls">{{ t.student_class || "—" }}</span>
              <span class="thread-score" :class="t.level || 'green'">{{ t.score ?? "—" }}</span>
            </div>
            <span v-if="t.last_ts" class="thread-ts">
              {{ t.last_ts }} · {{ t.last_text?.slice(0, 18) }}{{ t.last_text?.length > 18 ? "…" : "" }}
            </span>
            <span v-else class="thread-ts muted">暂无消息，点此开始</span>
          </button>
        </div>
      </aside>

      <!-- 对话区 -->
      <section class="conv">
        <div v-if="!currentThread" class="conv-empty">
          {{ isParent ? "暂无会话，发一条消息给辅导员吧。" : "请在左侧选择一位家长开始对话。" }}
        </div>
        <template v-else>
          <!-- 对方信息条：姓名 + 联系方式（任务 9） -->
          <div class="conv-peer">
            <div class="peer-name">
              <span class="peer-label">{{ isParent ? "辅导员" : "家长" }}</span>
              <b>{{ currentThread.peer_name }}</b>
            </div>
            <div v-if="currentThread.peer_phone" class="peer-contact">
              <span class="peer-ico" aria-hidden="true">☎</span>
              <a :href="`tel:${currentThread.peer_phone}`">{{ currentThread.peer_phone }}</a>
            </div>
            <span v-if="currentThread.unread" class="peer-unread">{{ currentThread.unread }} 条未读</span>
          </div>
          <div ref="bodyRef" class="conv-body">
            <div v-if="!currentThread.messages.length" class="conv-hint">
              还没有消息，发一条开启沟通吧。
            </div>
            <div
              v-for="m in currentThread.messages"
              :key="m.id"
              class="bubble"
              :class="{ mine: m.from_role === role }"
            >
              <div class="bubble-head">
                <b>{{ m.from_name }}</b>
                <span class="bubble-ts">{{ m.ts }}</span>
              </div>
              <p class="bubble-text">{{ m.text }}</p>
            </div>
          </div>
          <div class="conv-input">
            <textarea
              v-model="draft"
              rows="2"
              placeholder="输入消息，回车发送（Shift+回车换行）"
              @keydown.enter.exact.prevent="send"
            ></textarea>
            <button class="btn ok" :disabled="notices.sending || !draft.trim()" @click="send">
              {{ notices.sending ? "发送中…" : "发送" }}
            </button>
          </div>
        </template>
      </section>
    </div>
  </div>
</template>

<style scoped>
/* 撑满视口：高度 = 100vh - 顶栏(~46px) - .view padding(~38px)，
   不再用 min-height 让外层 .view 滚动，避免输入框虚高、底部黑色溢出。 */
.msg-page {
  height: calc(100vh - 96px);
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
}
.msg-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex: none;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--line);
}
.msg-head .tiny {
  font-size: 11.5px;
  margin: 0;
}
.btn.ghost {
  border: 1px solid var(--line);
  background: #fff;
  color: var(--text-2);
  padding: 6px 14px;
  border-radius: 8px;
  font-size: 12.5px;
  cursor: pointer;
  flex: none;
}
.btn.ghost:hover {
  border-color: var(--brand);
  color: var(--brand);
}

.msg-empty {
  padding: 48px 0;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}

.msg-layout {
  display: flex;
  gap: 12px;
  flex: 1;
  min-height: 0; /* 关键：让子元素能正确滚动 */
}

/* 导员端会话列表 */
.thread-list {
  flex: none;
  width: 260px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fff;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.thread-list-head {
  padding: 10px 14px;
  font-size: 12px;
  letter-spacing: 1px;
  color: var(--text-2);
  border-bottom: 1px solid var(--line);
  background: var(--brand-soft);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex: none;
}
.thread-list-head em {
  font-style: normal;
  font-size: 11px;
  color: var(--muted);
}
.thread-search {
  flex: none;
  padding: 8px 10px;
  border-bottom: 1px solid var(--line);
  background: #fbf7ef;
}
.thread-search input {
  width: 100%;
  height: 30px;
  border: 1px solid var(--line);
  border-radius: 7px;
  padding: 0 10px;
  font-size: 12.5px;
  color: var(--text);
  background: #fff;
  outline: none;
  transition: border-color 0.14s;
}
.thread-search input:focus {
  border-color: var(--brand);
}
.thread-empty {
  padding: 28px 12px;
  text-align: center;
  color: var(--muted);
  font-size: 12.5px;
}
.thread-scroll {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
.thread-row {
  width: 100%;
  border: 0;
  border-bottom: 1px solid var(--line);
  background: transparent;
  text-align: left;
  padding: 9px 12px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 3px;
  transition: background 0.14s;
  border-left: 3px solid transparent;
}
.thread-row:hover {
  background: var(--brand-soft);
}
.thread-row.on {
  background: var(--brand-soft);
}
.thread-row.red {
  border-left-color: #dc2626;
}
.thread-row.yellow {
  border-left-color: #d97706;
}
.thread-row.green {
  border-left-color: #16a34a;
}
.thread-row.on b {
  color: var(--brand);
}
.thread-row-top {
  display: flex;
  align-items: center;
  gap: 6px;
}
.lv-dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #16a34a;
}
.lv-dot.red { background: #dc2626; }
.lv-dot.yellow { background: #d97706; }
.lv-dot.green { background: #16a34a; }
.thread-row b {
  flex: 1;
  font-size: 13px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.thread-row-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
}
.thread-cls {
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.thread-score {
  flex: none;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 6px;
}
.thread-score.red { color: #b91c1c; background: #fef2f2; }
.thread-score.yellow { color: #b45309; background: #fffbeb; }
.thread-score.green { color: #047857; background: #ecfdf5; }
.thread-ts {
  font-size: 10.5px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.thread-ts.muted {
  font-style: italic;
  opacity: 0.7;
}
.dot {
  flex: none;
  min-width: 17px;
  height: 17px;
  padding: 0 5px;
  border-radius: 999px;
  background: #dc2626;
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  display: grid;
  place-items: center;
  line-height: 1;
}

/* 对话区 */
.conv {
  flex: 1;
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fff;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}
.conv-empty {
  flex: 1;
  display: grid;
  place-items: center;
  color: var(--muted);
  font-size: 13px;
}
/* 对方信息条：姓名 + 联系方式 + 未读条数 */
.conv-peer {
  flex: none;
  padding: 9px 16px;
  font-size: 13px;
  color: var(--text-2);
  border-bottom: 1px solid var(--line);
  background: var(--brand-soft);
  display: flex;
  align-items: center;
  gap: 16px;
}
.peer-name {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.peer-label {
  font-size: 11px;
  color: var(--muted);
  letter-spacing: 0.5px;
}
.peer-name b {
  color: var(--text);
  font-size: 14px;
}
.peer-contact {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 999px;
  font-size: 12px;
}
.peer-ico {
  color: var(--brand);
  font-size: 12.5px;
}
.peer-contact a {
  color: var(--text);
  text-decoration: none;
  font-variant-numeric: tabular-nums;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.peer-contact a:hover {
  color: var(--brand);
  text-decoration: underline;
}
.peer-unread {
  margin-left: auto;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #dc2626;
  color: #fff;
}
.conv-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: #faf7f2;
  min-height: 0;
}
.conv-hint {
  margin: auto;
  color: var(--muted);
  font-size: 13px;
}
.bubble {
  max-width: 88%;
  padding: 9px 13px;
  border-radius: 12px;
  background: #fff;
  border: 1px solid var(--line);
  font-size: 13px;
  line-height: 1.55;
}
.bubble:not(.mine) {
  align-self: flex-start;
}
.bubble.mine {
  align-self: flex-end;
  background: var(--brand-soft);
  border-color: var(--brand);
}
.bubble-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 3px;
}
.bubble-head b {
  font-size: 11.5px;
  color: var(--text-2);
  font-weight: 600;
}
.bubble-ts {
  font-size: 10.5px;
  color: var(--muted);
}
.bubble-text {
  margin: 0;
  word-break: break-word;
  color: var(--text);
}
/* 输入区：textarea 与按钮同高对齐 */
.conv-input {
  flex: none;
  display: flex;
  gap: 8px;
  padding: 10px;
  border-top: 1px solid var(--line);
  background: #fff;
  align-items: stretch;
}
.conv-input textarea {
  flex: 1;
  resize: none;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 13px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.14s;
  line-height: 1.5;
  min-height: 40px;
}
.conv-input textarea:focus {
  border-color: var(--brand);
}
.btn.ok {
  align-self: stretch;
  border: 0;
  background: var(--brand);
  color: #fff;
  padding: 0 22px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.btn.ok:disabled {
  opacity: 0.5;
  cursor: default;
}

/* 手机端：会话列表收成顶栏横向条 */
@media (max-width: 760px) {
  .msg-page {
    height: calc(100vh - 84px);
  }
  .msg-layout {
    flex-direction: column;
  }
  .thread-list {
    width: 100%;
    max-height: 150px;
    flex: none;
  }
  .thread-row {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
  }
  .conv-peer {
    flex-wrap: wrap;
    gap: 8px;
  }
}
</style>
