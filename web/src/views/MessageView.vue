<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus/es/components/message/index";
import { useAuthStore } from "@/stores/auth";
import { useNoticeStore } from "@/stores/notices";
import { api } from "@/api/client";
import {
  humanSize,
  pickImage,
  startRecording,
  type PickedMedia,
  type Recorder,
} from "@/composables/media";
import type { MessageMedia } from "@/types";

/**
 * 家校沟通独立整页：家长端 ↔ 辅导员端双向对话。
 *
 * - 家长端：只有一个会话（和自家孩子的辅导员），左侧不显示列表
 * - 辅导员端：左侧按学生列出所有家长会话，点谁和谁聊；带搜索框快速跳到某学生
 * - 对话头部显示对方联系方式（电话），方便双方互相找
 * - 除了打字，家长还能拍张照片发过去、按住说一段话——很多事说不清，拍一张更快
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

/* ------------------------------------------------------------------
 * 照片 / 语音
 *
 * 家长端最常发的不是长句子，是「这张作业照片」「我说两句」。
 * 图片在本地压到长边 1280 再发；语音走 MediaRecorder，反过来还能顺便
 * 交给后端转写一份文字，导员不点播放也能扫一眼知道说了什么。
 * ---------------------------------------------------------------- */
const pending = ref<PickedMedia[]>([]);
const imgInput = ref<HTMLInputElement | null>(null);
const busy = ref(false);
const recording = ref(false);
const recSeconds = ref(0);
const holding = ref(false);
const willCancel = ref(false);
const hint = ref("");
const MAX_ATTACH = 3;

let rec: Recorder | null = null;
let recTimer: number | null = null;
let pressAt = 0;
let pressY = 0;

function note(msg: string) {
  hint.value = msg;
  window.setTimeout(() => {
    if (hint.value === msg) hint.value = "";
  }, 4000);
}

function addAttach(m: PickedMedia) {
  if (pending.value.length >= MAX_ATTACH) {
    note(`一次最多带 ${MAX_ATTACH} 个附件`);
    return;
  }
  pending.value = [...pending.value, m];
}

function removeAttach(id: string) {
  pending.value = pending.value.filter((x) => x.id !== id);
}

async function onImagePicked(ev: Event) {
  const input = ev.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  if (file.size > 12 * 1024 * 1024) {
    note(`照片太大了（${humanSize(file.size)}），换一张小于 12MB 的`);
    return;
  }
  busy.value = true;
  try {
    addAttach(await pickImage(file));
  } catch (e: any) {
    note(e?.message || "这张照片读不出来");
  } finally {
    busy.value = false;
  }
}

function clearTimer() {
  if (recTimer) {
    window.clearInterval(recTimer);
    recTimer = null;
  }
}

function detachHold() {
  window.removeEventListener("pointermove", onHoldMove);
  window.removeEventListener("pointerup", endHold);
  window.removeEventListener("pointercancel", endHold);
}

function onHoldMove(ev: PointerEvent) {
  if (!holding.value) return;
  willCancel.value = pressY - ev.clientY > 60;
}

async function beginHold(ev: PointerEvent) {
  if (busy.value || recording.value || holding.value || notices.sending) return;
  pressAt = Date.now();
  pressY = ev.clientY;
  holding.value = true;
  willCancel.value = false;
  window.addEventListener("pointermove", onHoldMove);
  window.addEventListener("pointerup", endHold);
  window.addEventListener("pointercancel", endHold);
  try {
    rec = await startRecording();
    if (!holding.value) {
      rec.cancel();
      rec = null;
      return;
    }
    recording.value = true;
    recSeconds.value = 0;
    recTimer = window.setInterval(() => {
      recSeconds.value += 1;
      if (recSeconds.value >= 60) void stopRec();
    }, 1000);
  } catch (e: any) {
    detachHold();
    holding.value = false;
    note(e?.message || "打不开麦克风，检查一下浏览器权限");
  }
}

function endHold() {
  const wasHolding = holding.value;
  detachHold();
  if (!wasHolding) return;
  holding.value = false;
  if (!recording.value) return;
  if (willCancel.value) {
    void cancelRec("已取消");
    return;
  }
  if (Date.now() - pressAt < 500) {
    void cancelRec("按住麦克风说话，说完再松开");
    return;
  }
  void stopRec();
}

function cancelRec(msg: string) {
  clearTimer();
  recording.value = false;
  willCancel.value = false;
  recSeconds.value = 0;
  const handle = rec;
  rec = null;
  handle?.cancel();
  note(msg);
}

async function stopRec() {
  clearTimer();
  recording.value = false;
  willCancel.value = false;
  const handle = rec;
  rec = null;
  if (!handle) return;
  busy.value = true;
  try {
    const media = await handle.stop();
    // 顺手转一手文字：导员不点播放也能知道这段语音说了什么
    try {
      const r = await api.asr({ kind: "audio", data: media.data, mime: media.mime });
      if (r?.ok && r.text) media.transcript = r.text;
    } catch {
      /* 转写不通就只发语音 */
    }
    addAttach(media);
  } catch (e: any) {
    note(e?.message || "录音失败");
  } finally {
    busy.value = false;
  }
}

function toMessageMedia(list: PickedMedia[]): MessageMedia[] {
  return list.map((m) => ({
    kind: m.kind === "text" ? "text" : m.kind === "audio" ? "audio" : "image",
    name: m.name,
    mime: m.mime,
    data: m.data || (m.frames && m.frames[0]) || "",
    duration: m.duration,
    transcript: m.transcript,
  }));
}

function previewOf(a: PickedMedia): string {
  if (a.kind === "audio") return a.duration ? `${a.duration} 秒` : "语音";
  return humanSize(a.size);
}

const MEDIA_ICON: Record<string, string> = { image: "🖼", audio: "🎤", video: "🎬", text: "📄" };

async function send() {
  const text = draft.value.trim();
  if ((!text && !pending.value.length) || !currentThread.value) return;
  const sid = currentThread.value.sid;
  try {
    await notices.sendMessage(sid, text, toMessageMedia(pending.value));
    draft.value = "";
    pending.value = [];
    await nextTick();
    scrollBottom();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || "发送失败");
  }
}

onBeforeUnmount(() => {
  clearTimer();
  detachHold();
  if (rec) {
    rec.cancel();
    rec = null;
  }
});

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
        <template v-if="isParent">下方是与孩子辅导员的对话，可以直接发照片、按住说话</template>
        <template v-else>左侧按风险排序，红黄学生优先联系；家长发来的照片和语音都在会话里</template>
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
              <!-- 附件先于文字：照片要占地方，语音要能直接点开听 -->
              <div v-if="m.media && m.media.length" class="bubble-media">
                <template v-for="(a, ai) in m.media" :key="ai">
                  <a
                    v-if="a.kind === 'image' && a.data"
                    class="bm-img"
                    :href="a.data"
                    target="_blank"
                    rel="noopener"
                    :title="a.name || '查看原图'"
                  >
                    <img :src="a.data" :alt="a.name || '照片'" />
                  </a>
                  <div v-else-if="a.kind === 'audio' && a.data" class="bm-audio">
                    <span class="bm-audio-ico" aria-hidden="true">🎤</span>
                    <audio :src="a.data" controls preload="metadata"></audio>
                    <span v-if="a.duration" class="bm-audio-sec">{{ a.duration }}″</span>
                  </div>
                  <div v-else class="bm-file">
                    <span aria-hidden="true">{{ MEDIA_ICON[a.kind] || "📎" }}</span>
                    {{ a.name || "附件" }}
                  </div>
                  <p v-if="a.kind === 'audio' && a.transcript" class="bm-transcript">
                    「{{ a.transcript }}」
                  </p>
                </template>
              </div>
              <p v-if="m.text" class="bubble-text">{{ m.text }}</p>
            </div>
          </div>
          <div class="conv-input">
            <!-- 待发的附件：发之前能看清带的是哪张照片、哪段话 -->
            <div v-if="pending.length" class="ci-attach">
              <div v-for="a in pending" :key="a.id" class="ci-item">
                <img v-if="a.kind === 'image' && a.thumb" :src="a.thumb" :alt="a.name" />
                <span v-else class="ci-ico">{{ MEDIA_ICON[a.kind] }}</span>
                <div class="ci-meta">
                  <b>{{ a.kind === "image" ? "照片" : a.kind === "audio" ? "语音" : a.name }}</b>
                  <i>{{ previewOf(a) }}</i>
                </div>
                <button type="button" title="移除" @click="removeAttach(a.id)">×</button>
              </div>
            </div>

            <div v-if="hint" class="ci-hint">{{ hint }}</div>

            <!-- 录音中：整条变成「松开发送 / 上滑取消」 -->
            <div v-if="recording" class="ci-voice" :class="{ 'will-cancel': willCancel }">
              <span class="ci-wave"><i></i><i></i><i></i><i></i><i></i></span>
              <span>{{ willCancel ? "松开手指，取消发送" : `正在听… ${recSeconds}″` }}</span>
              <button type="button" class="ci-voice-stop" @click.stop="stopRec">结束</button>
            </div>

            <div v-else class="ci-row">
              <button
                type="button"
                class="ci-btn"
                :disabled="busy || notices.sending"
                title="发一张照片"
                aria-label="发照片"
                data-test="msg-photo"
                @click="imgInput?.click()"
              >
                <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">
                  <rect x="3" y="5" width="18" height="14" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.6" />
                  <circle cx="8.6" cy="10.2" r="1.5" fill="currentColor" />
                  <path d="M4.5 17l4.6-4.2 3.4 2.9 2.9-2.4 3.9 3.7" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" />
                </svg>
              </button>
              <textarea
                v-model="draft"
                rows="2"
                placeholder="说点什么，回车发送（Shift+回车换行）"
                @keydown.enter.exact.prevent="send"
              ></textarea>
              <button
                type="button"
                class="ci-btn mic"
                :class="{ on: holding || recording }"
                :disabled="busy || notices.sending"
                title="按住说话，松开结束；上滑可取消"
                aria-label="按住说话"
                data-test="msg-voice"
                @pointerdown.prevent="beginHold"
                @contextmenu.prevent
              >
                <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">
                  <rect x="9" y="2.8" width="6" height="10.4" rx="3" fill="none" stroke="currentColor" stroke-width="1.7" />
                  <path d="M5.2 11.2a6.8 6.8 0 0 0 13.6 0M12 18.2V21" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
                </svg>
              </button>
              <button
                class="btn ok"
                :disabled="notices.sending || (!draft.trim() && !pending.length)"
                @click="send"
              >
                {{ notices.sending ? "发送中…" : "发送" }}
              </button>
            </div>
            <input
              ref="imgInput"
              type="file"
              accept="image/*"
              class="ci-file"
              @change="onImagePicked"
            />
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
  border-left-color: #b3261e;
}
.thread-row.yellow {
  border-left-color: #a9681f;
}
.thread-row.green {
  border-left-color: #17604f;
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
  background: #17604f;
}
.lv-dot.red { background: #b3261e; }
.lv-dot.yellow { background: #a9681f; }
.lv-dot.green { background: #17604f; }
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
.thread-score.red { color: #9c231c; background: #f9e8e5; }
.thread-score.yellow { color: #16564a; background: #f9efdf; }
.thread-score.green { color: #17604f; background: #e2efe9; }
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
  background: #b3261e;
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
  background: #b3261e;
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
/* 输入区：上面是待发附件，下面一行「照片 / 文字 / 语音 / 发送」 */
.conv-input {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border-top: 1px solid var(--line);
  background: #fff;
}
.ci-row {
  display: flex;
  gap: 8px;
  align-items: stretch;
}
.ci-row textarea {
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
.ci-row textarea:focus {
  border-color: var(--brand);
}
.ci-btn {
  flex: 0 0 auto;
  width: 38px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fbf9f3;
  color: var(--text-2);
  display: grid;
  place-items: center;
  cursor: pointer;
  transition: border-color 0.14s, color 0.14s, background 0.14s;
}
.ci-btn:hover:not(:disabled) {
  border-color: var(--brand);
  color: var(--brand);
}
.ci-btn:disabled {
  opacity: 0.5;
  cursor: default;
}
.ci-btn.mic.on {
  border-color: var(--clay);
  background: var(--clay-soft);
  color: var(--clay);
}
.ci-file {
  display: none;
}
/* 待发附件条 */
.ci-attach {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.ci-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 6px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fffdf8;
  max-width: 230px;
}
.ci-item img {
  width: 36px;
  height: 36px;
  object-fit: cover;
  border-radius: 7px;
}
.ci-ico {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 7px;
  background: #f0ebdf;
  font-size: 16px;
}
.ci-meta {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.ci-meta b {
  font-size: 11.5px;
  color: var(--text-2);
  font-weight: 600;
}
.ci-meta i {
  font-style: normal;
  font-size: 10px;
  color: var(--muted);
}
.ci-item button {
  border: 0;
  background: #f1e7d8;
  color: #8a7357;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
  padding: 0;
}
.ci-hint {
  font-size: 11.5px;
  color: var(--clay);
}
/* 录音中 */
.ci-voice {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 46px;
  padding: 0 12px;
  border: 1px solid rgba(180, 85, 45, 0.4);
  border-radius: 8px;
  background: var(--clay-soft);
  color: var(--clay);
  font-size: 13px;
}
.ci-voice.will-cancel {
  border-color: #b3261e;
  background: var(--red-soft);
  color: #9c231c;
}
.ci-wave {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.ci-wave i {
  width: 3px;
  border-radius: 2px;
  background: currentColor;
  animation: cwave 0.9s ease-in-out infinite;
}
.ci-wave i:nth-child(1) { height: 7px; animation-delay: 0s; }
.ci-wave i:nth-child(2) { height: 14px; animation-delay: 0.12s; }
.ci-wave i:nth-child(3) { height: 9px; animation-delay: 0.24s; }
.ci-wave i:nth-child(4) { height: 16px; animation-delay: 0.36s; }
.ci-wave i:nth-child(5) { height: 8px; animation-delay: 0.48s; }
@keyframes cwave {
  50% { transform: scaleY(0.4); opacity: 0.6; }
}
.ci-voice-stop {
  margin-left: auto;
  border: 1px solid currentColor;
  background: transparent;
  color: inherit;
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 12px;
  cursor: pointer;
}
/* 气泡里的照片 / 语音 */
.bubble-media {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 6px;
}
.bm-img {
  display: inline-block;
  max-width: 100%;
  border-radius: 9px;
  overflow: hidden;
  border: 1px solid var(--line);
  line-height: 0;
  background: #fff;
}
.bm-img img {
  display: block;
  width: auto;
  max-width: 240px;
  max-height: 220px;
  height: auto;
  object-fit: contain;
  border-radius: 8px;
}
.bm-audio {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #fff;
  max-width: 300px;
}
.bm-audio-ico {
  font-size: 14px;
}
.bm-audio audio {
  height: 30px;
  max-width: 210px;
}
.bm-audio-sec {
  font-size: 11px;
  color: var(--muted);
}
.bm-transcript {
  margin: 0;
  font-size: 11.5px;
  color: var(--muted);
  line-height: 1.5;
  max-width: 280px;
}
.bm-file {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 9px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
  font-size: 12px;
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
