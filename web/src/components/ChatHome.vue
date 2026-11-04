<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import AgentBriefing from "@/components/AgentBriefing.vue";
import CitationList from "@/components/CitationList.vue";
import MarkdownBody from "@/components/MarkdownBody.vue";
import TraceSteps from "@/components/TraceSteps.vue";
import { useChatStore, DEFAULT_SUGGEST } from "@/stores/chat";
import { api } from "@/api/client";
import {
  humanSize,
  pickImage,
  pickVideo,
  startRecording,
  type PickedMedia,
  type Recorder,
} from "@/composables/media";
import type { Role } from "@/types";

const props = defineProps<{ role: Role; sid: string | null }>();

const chat = useChatStore();
const draft = ref("");
const stream = ref<HTMLElement | null>(null);

/** 每个端的整页对话：标题、副标题、以及「去看板」按键文案 */
const HOME: Record<Role, { title: string; sub: string; dash: string }> = {
  student: {
    title: "学业助手",
    sub: "基于你的学情数据回答，不猜不编",
    dash: "我的学情档案",
  },
  counselor: {
    title: "辅导员助手",
    sub: "名单、原因、谈话建议，问我就行",
    dash: "预警名单 · 台账",
  },
  admin: {
    title: "教务助手",
    sub: "全校统计与规则问题",
    dash: "规则 · 看板",
  },
  parent: {
    title: "家校助手",
    sub: "用通俗的话说明孩子的情况",
    dash: "孩子的学情报告",
  },
  teacher: {
    title: "教学助手",
    sub: "你课上学生的考勤、作业与风险",
    dash: "课堂学情看板",
  },
};

const PLACEHOLDER: Record<Role, string> = {
  student: "问点什么，比如：我的风险分为什么这么高？",
  counselor: "比如：本班谁的风险上升最快？",
  admin: "比如：全校风险分布如何？",
  parent: "比如：孩子这学期情况怎么样？",
  teacher: "比如：我课上的学生？谁的风险最高？",
};

const home = computed(() => HOME[props.role] ?? HOME.student);
const placeholder = computed(() => PLACEHOLDER[props.role] ?? PLACEHOLDER.student);

/**
 * 建议词必须跟本页的端口一致。
 * store 里的建议词可能还是上一个端（或登录前的默认学生态）留下的，
 * 这里以页面自己声明的 role 为准：对不上就直接用本端默认提问兜住。
 */
const suggestList = computed(() =>
  chat.suggRole === props.role ? chat.suggestions : DEFAULT_SUGGEST[props.role],
);

/**
 * 这个组件就是某个端的对话主界面，进来先把会话锚定到自己身上：
 * 问候语、建议词、（若换了账号）历史记录都会跟着 role 走。
 * 不依赖 App 里那个 watch —— 登录跳转与路由切换的先后顺序会让它漏触发。
 */
watch(
  () => props.role,
  (r) => chat.ensure(r as Role),
  { immediate: true },
);

function goDash() {
  chat.homeMode = "dash";
}

function scrollToBottom() {
  nextTick(() => {
    if (stream.value) stream.value.scrollTop = stream.value.scrollHeight;
  });
}

// 流式输出时文本逐字增长，靠深度监听把视口钉在底部
watch(() => chat.messages, scrollToBottom, { deep: true });
watch(() => props.role, scrollToBottom);

// 页面切走时把还在跑的流掐掉，否则请求会悬挂并往已卸载的视图里写数据
onBeforeUnmount(() => {
  cleanupRec();
  chat.abort();
});

/* ------------------------------------------------------------------
 * 多模态输入：图片 / 视频 / 语音
 * 图片在本地压到长边 1280，视频在本地抽 4 帧，录音走 MediaRecorder。
 * 后端只收「收拾干净的数据」，不用为了看一张图在服务器上装 ffmpeg。
 * ---------------------------------------------------------------- */
const attachments = ref<PickedMedia[]>([]);
const recording = ref(false);
const recSeconds = ref(0);
const busy = ref(false);
const mediaError = ref("");
const imageInput = ref<HTMLInputElement | null>(null);
const videoInput = ref<HTMLInputElement | null>(null);

/* 「+」里的附件菜单、以及「按住说话」的手势状态 */
const menuOpen = ref(false);
const holding = ref(false);
const willCancel = ref(false);
const draftEl = ref<HTMLTextAreaElement | null>(null);

let rec: Recorder | null = null;
let recTimer: number | null = null;
let pressAt = 0;
let pressY = 0;

const MEDIA_ICON: Record<string, string> = { image: "🖼", video: "🎬", audio: "🎤" };
const MAX_ATTACH = 3;

function note(msg: string) {
  mediaError.value = msg;
  window.setTimeout(() => {
    if (mediaError.value === msg) mediaError.value = "";
  }, 4500);
}

function addAttach(m: PickedMedia) {
  if (attachments.value.length >= MAX_ATTACH) {
    note(`一次最多带 ${MAX_ATTACH} 个附件`);
    return;
  }
  attachments.value = [...attachments.value, m];
}

function removeAttach(id: string) {
  attachments.value = attachments.value.filter((x) => x.id !== id);
}

async function onImagePicked(ev: Event) {
  const input = ev.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  if (file.size > 12 * 1024 * 1024) {
    note(`图片太大了（${humanSize(file.size)}），换一张小于 12MB 的`);
    return;
  }
  busy.value = true;
  try {
    addAttach(await pickImage(file));
  } catch (e: any) {
    note(e?.message || "这张图片读不出来");
  } finally {
    busy.value = false;
  }
}

async function onVideoPicked(ev: Event) {
  const input = ev.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  if (file.size > 80 * 1024 * 1024) {
    note(`视频太大了（${humanSize(file.size)}），换一段小于 80MB 的`);
    return;
  }
  busy.value = true;
  note("正在从视频里取画面…");
  try {
    addAttach(await pickVideo(file));
    mediaError.value = "";
  } catch (e: any) {
    note(e?.message || "这段视频读不出来，试试 MP4");
  } finally {
    busy.value = false;
  }
}

/**
 * 语音按微信那套「按住说话」来做：
 * 按下开录 → 松开就结束并转写；按下后往上滑 60px 松开 = 取消；点一下（<0.5s）
 * 当成误触，直接丢掉这段，免得用户以为自己说完了却什么也没发出去。
 */
function tickRec() {
  recTimer = window.setInterval(() => {
    recSeconds.value += 1;
    if (recSeconds.value >= 60) void stopRec(); // 一分钟自动收，别录成会议纪要
  }, 1000);
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
  // 手指往上抬超过 60px 就切到「松开取消」，跟微信一致
  willCancel.value = pressY - ev.clientY > 60;
}

async function beginHold(ev: PointerEvent) {
  if (chat.streaming || busy.value || recording.value || holding.value) return;
  menuOpen.value = false;
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
      // 麦克风还没开好用户就松手了，这段作废
      rec.cancel();
      rec = null;
      return;
    }
    recording.value = true;
    recSeconds.value = 0;
    tickRec();
    if (!rec.canTranscribe) note("这个浏览器不支持实时转写，录完交给后端识别");
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
  if (!recording.value) return; // 还在等麦克风，beginHold 那边会自己收尾
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

async function cancelRec(hint: string) {
  clearTimer();
  recording.value = false;
  willCancel.value = false;
  recSeconds.value = 0;
  const handle = rec;
  rec = null;
  handle?.cancel();
  note(hint);
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
    // 先把音频交给后端转写；不通就用浏览器那份，都没有才说没听清
    try {
      const r = await api.asr({ kind: "audio", data: media.data, mime: media.mime });
      if (r?.ok && r.text) media.transcript = r.text;
    } catch {
      /* 后端不可达就用浏览器转写 */
    }
    addAttach(media);
    if (media.transcript) {
      draft.value = (draft.value + " " + media.transcript).trim();
    } else {
      note("没听清这段语音。可以说慢一点，或直接把问题打字发来");
    }
  } catch (e: any) {
    note(e?.message || "录音失败");
  } finally {
    busy.value = false;
  }
}

/** 附件被删/被发送后，把还在录的音收掉，避免麦克风一直开着 */
function cleanupRec() {
  clearTimer();
  detachHold();
  if (rec) {
    rec.cancel();
    rec = null;
  }
  recording.value = false;
  holding.value = false;
  willCancel.value = false;
}

function send(text: string) {
  const content = (text ?? "").trim();
  const media = attachments.value;
  if (!content && !media.length) return;
  if (chat.streaming) return;
  draft.value = "";
  attachments.value = [];
  cleanupRec();
  chat.send(props.role, props.sid, content, media);
  scrollToBottom();
}

function submit() {
  send(draft.value);
}

/** 输入框随内容长高，最多 120px 后内部滚动 */
function autoGrow() {
  const el = draftEl.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(120, el.scrollHeight)}px`;
}
watch(draft, () => nextTick(autoGrow));
watch(
  () => chat.streaming,
  () => nextTick(autoGrow),
);

/** 回车发送、Shift+回车换行 */
function onKeydown(ev: KeyboardEvent) {
  if (ev.key !== "Enter" || ev.shiftKey || ev.isComposing) return;
  ev.preventDefault();
  submit();
}

function openImage() {
  menuOpen.value = false;
  imageInput.value?.click();
}

function openVideo() {
  menuOpen.value = false;
  videoInput.value?.click();
}

/** 点「+」外面就收起菜单；Esc 同样 */
function onDocClick() {
  menuOpen.value = false;
}
watch(menuOpen, (v) => {
  if (v) document.addEventListener("click", onDocClick);
  else document.removeEventListener("click", onDocClick);
});
onBeforeUnmount(() => document.removeEventListener("click", onDocClick));

// 意图是一个内部枚举值，直接贴 "unknown" 给用户看没意义。
// 这里翻成人话：用户想知道的是「系统怎么理解我这句话的、去哪找的答案」。
const INTENT_LABEL: Record<string, string> = {
  risk: "查风险分",
  roster: "查名单",
  policy: "查校规条款",
  attendance: "查考勤",
  homework: "查作业",
  overview: "查全校统计",
  advice: "生成干预建议",
  contact: "查任课教师",
  letter: "生成家长信",
  report: "生成日报",
  unknown: "关键词没命中，交给模型判断",
  llm_route: "模型直接作答",
  llm_tool: "模型自己决定取哪些数据",
};

function intentLabel(v: string): string {
  return INTENT_LABEL[v] ?? v;
}
</script>

<template>
  <section class="chat-home">
    <header class="chat-home-head">
      <span class="ch-avatar" aria-hidden="true">AI</span>
      <div class="ch-title">
        <strong>{{ home.title }}</strong>
        <span>{{ home.sub }}</span>
      </div>
      <button class="ch-go-dash" @click="goDash">
        📊 {{ home.dash }}
      </button>
    </header>

    <div ref="stream" class="chat-stream">
      <div class="chat-col">
        <!-- AI 先开口：进页面的主动简报，追问点击即发 -->
        <AgentBriefing :role="role" />

        <div v-for="m in chat.messages" :key="m.id" class="msg" :class="{ user: m.from === 'user' }">
          <div class="bubble">
            <template v-if="m.from === 'user'">
              <div v-if="m.media && m.media.length" class="bubble-media">
                <div v-for="(a, i) in m.media" :key="i" class="bm-item">
                  <img v-if="a.thumb" :src="a.thumb" :alt="a.name" class="bm-thumb" />
                  <span v-else class="bm-ico">{{ MEDIA_ICON[a.kind] }}</span>
                  <div class="bm-side">
                    <span class="bm-name">{{ a.name }}</span>
                    <span v-if="a.transcript" class="bm-said">「{{ a.transcript }}」</span>
                    <span v-else-if="a.duration" class="bm-said">{{ a.duration }} 秒</span>
                  </div>
                </div>
              </div>
              {{ m.text }}
            </template>
            <template v-else>
              <!-- 思考链：智能体在说谁、走哪条路，边想边显示 -->
              <div v-if="m.thoughts.length" class="thoughts" :class="{ done: !m.pending }">
                <div v-for="(t, i) in m.thoughts" :key="i" class="thought-line">
                  <span class="thought-ico">{{ m.pending && i === m.thoughts.length - 1 ? "…" : "✓" }}</span>
                  {{ t }}
                </div>
              </div>
              <MarkdownBody v-if="m.text" :text="m.text" />
              <span v-if="m.pending && m.text" class="typing-caret"></span>
              <span v-else-if="m.pending && !m.thoughts.length" class="spinner"></span>
              <div v-if="m.error" class="chat-error">{{ m.error }}</div>
              <div v-if="m.intent && m.intent !== 'why'" class="chat-intent">
                意图识别：{{ intentLabel(m.intent) }}
              </div>
            </template>
          </div>

          <template v-if="m.from === 'assistant'">
            <CitationList :citations="m.citations" :max-chars="90" />
            <TraceSteps :trace="m.trace" :pending="m.pending" :elapsed="m.elapsed" />
          </template>
        </div>
      </div>
    </div>

    <div class="chat-home-foot">
      <div class="chat-col">
        <div v-if="suggestList.length && !attachments.length && !recording" class="ch-suggest">
          <button v-for="s in suggestList" :key="s" class="chip" @click="send(s)">{{ s }}</button>
        </div>

        <div v-if="mediaError" class="ch-media-err">{{ mediaError }}</div>

        <form class="ch-composer" @submit.prevent="submit">
          <!-- 待发送的附件：就贴在输入区里，发之前能确认带对没带对 -->
          <div v-if="attachments.length" class="ch-attach">
            <div v-for="a in attachments" :key="a.id" class="ch-attach-item">
              <img v-if="a.thumb" :src="a.thumb" :alt="a.name" />
              <span v-else class="ch-attach-ico">{{ MEDIA_ICON[a.kind] }}</span>
              <div class="ch-attach-meta">
                <span class="nm">{{ a.name }}</span>
                <span class="sz">
                  {{ a.kind === "video" ? `抽了 ${a.frames?.length || 0} 帧` : a.duration ? `${a.duration} 秒` : humanSize(a.size) }}
                </span>
              </div>
              <button type="button" class="ch-attach-x" title="移除" @click="removeAttach(a.id)">
                ×
              </button>
            </div>
          </div>

          <!-- 录音中：整条输入区变成微信那样的「松开发送 / 上滑取消」 -->
          <div v-if="recording" class="ch-voice" :class="{ 'will-cancel': willCancel }">
            <span class="ch-voice-wave"><i></i><i></i><i></i><i></i><i></i></span>
            <span class="ch-voice-txt">
              {{ willCancel ? "松开手指，取消发送" : `正在听… ${recSeconds}″` }}
            </span>
            <button type="button" class="ch-voice-stop" @click.stop="stopRec">结束</button>
          </div>
          <textarea
            v-else
            ref="draftEl"
            v-model="draft"
            rows="1"
            :placeholder="placeholder"
            :disabled="chat.streaming"
            data-test="chat-input"
            @keydown="onKeydown"
          ></textarea>

          <div class="ch-bar">
            <div class="ch-plus-wrap">
              <button
                type="button"
                class="ch-plus"
                :class="{ on: menuOpen }"
                :disabled="chat.streaming || busy || recording"
                title="添加图片或视频"
                aria-label="添加图片或视频"
                @click.stop="menuOpen = !menuOpen"
              >
                <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">
                  <path
                    d="M12 5v14M5 12h14"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                  />
                </svg>
              </button>

              <transition name="ch-pop">
                <div v-if="menuOpen" class="ch-menu" @click.stop>
                  <button type="button" @click="openImage">
                    <span class="ic">
                      <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">
                        <rect
                          x="3"
                          y="5"
                          width="18"
                          height="14"
                          rx="2.5"
                          fill="none"
                          stroke="currentColor"
                          stroke-width="1.6"
                        />
                        <circle cx="8.6" cy="10.2" r="1.5" fill="currentColor" />
                        <path
                          d="M4.5 17l4.6-4.2 3.4 2.9 2.9-2.4 3.9 3.7"
                          fill="none"
                          stroke="currentColor"
                          stroke-width="1.6"
                          stroke-linejoin="round"
                        />
                      </svg>
                    </span>
                    <span class="tx"><b>照片</b><i>成绩单、板书、聊天截图</i></span>
                  </button>
                  <button type="button" @click="openVideo">
                    <span class="ic">
                      <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">
                        <rect
                          x="3"
                          y="6"
                          width="12.5"
                          height="12"
                          rx="2.5"
                          fill="none"
                          stroke="currentColor"
                          stroke-width="1.6"
                        />
                        <path
                          d="M15.5 11.2l4.3-2.5c.5-.3 1.2.05 1.2.65v5.3c0 .6-.7.95-1.2.65l-4.3-2.5z"
                          fill="none"
                          stroke="currentColor"
                          stroke-width="1.6"
                          stroke-linejoin="round"
                        />
                      </svg>
                    </span>
                    <span class="tx"><b>视频</b><i>本地抽 4 帧，不上传整段</i></span>
                  </button>
                </div>
              </transition>
            </div>

            <span class="ch-tip">图片 · 视频 · 按住说话</span>

            <button
              type="button"
              class="ch-mic"
              :class="{ on: holding || recording }"
              :disabled="chat.streaming || busy"
              title="按住说话，松开结束；上滑可取消"
              aria-label="按住说话"
              @pointerdown.prevent="beginHold"
              @contextmenu.prevent
            >
              <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">
                <rect
                  x="9"
                  y="2.8"
                  width="6"
                  height="10.4"
                  rx="3"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.7"
                />
                <path
                  d="M5.2 11.2a6.8 6.8 0 0 0 13.6 0M12 18.2V21"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.7"
                  stroke-linecap="round"
                />
              </svg>
            </button>

            <button
              type="submit"
              class="ch-send"
              :disabled="chat.streaming || recording || (!draft.trim() && !attachments.length)"
              data-test="chat-send"
              :title="chat.streaming ? '正在回答…' : '发送'"
              aria-label="发送"
            >
              <svg v-if="!chat.streaming" viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">
                <path
                  d="M12 19.5V5M5.5 11.5L12 5l6.5 6.5"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
              <span v-else class="ch-send-dots">…</span>
            </button>
          </div>
        </form>

        <input
          ref="imageInput"
          type="file"
          accept="image/*"
          class="ch-file"
          @change="onImagePicked"
        />
        <input
          ref="videoInput"
          type="file"
          accept="video/*"
          class="ch-file"
          @change="onVideoPicked"
        />
      </div>
    </div>
  </section>
</template>

<style scoped>
.chat-error {
  color: #b91c1c;
  font-size: 12px;
  margin-top: 4px;
}
.chat-intent {
  font-size: 10.5px;
  color: #b09b85;
  margin-top: 6px;
}

/* ---------------- 多模态输入 ---------------- */
.ch-file {
  display: none;
}

/* 待发送的附件条 */
.ch-attach {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.ch-attach-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 6px 5px 5px;
  border: 1px solid #ecdfc9;
  border-radius: 10px;
  background: #fffdf8;
  max-width: 240px;
}
.ch-attach-item img {
  width: 38px;
  height: 38px;
  object-fit: cover;
  border-radius: 7px;
  flex: 0 0 auto;
}
.ch-attach-ico {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 7px;
  background: #f6efe2;
  font-size: 17px;
  flex: 0 0 auto;
}
.ch-attach-meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 1px;
}
.ch-attach-meta .nm {
  font-size: 11.5px;
  color: #6b5947;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 130px;
}
.ch-attach-meta .sz {
  font-size: 10px;
  color: #b09b85;
}
.ch-attach-x {
  flex: 0 0 auto;
  width: 18px;
  height: 18px;
  border: 0;
  border-radius: 50%;
  background: #f1e7d8;
  color: #8a7357;
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
  padding: 0;
}
.ch-attach-x:hover {
  background: #e8d5bd;
}

.ch-media-err {
  margin-bottom: 8px;
  font-size: 11.5px;
  color: #b45309;
}

/* 用户气泡里的附件回显 */
.bubble-media {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 6px;
}
.bm-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.bm-thumb {
  width: 96px;
  max-height: 96px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid rgba(0, 0, 0, 0.06);
}
.bm-ico {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.55);
  font-size: 18px;
}
.bm-side {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.bm-name {
  font-size: 11px;
  opacity: 0.75;
}
.bm-said {
  font-size: 12px;
  font-style: italic;
  opacity: 0.92;
}

.ch-suggest {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
/* 思考链：进行中小字灰色，结束后收成一行高度不抢主体 */
.thoughts {
  margin: 0 0 8px;
  padding: 6px 9px;
  border-left: 2px solid #f0d9b5;
  background: #fbf7ef;
  border-radius: 0 6px 6px 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.thoughts.done {
  opacity: 0.72;
}
.thought-line {
  font-size: 11.5px;
  line-height: 1.55;
  color: #a58c72;
}
.thought-ico {
  color: #b45309;
  margin-right: 4px;
  font-size: 10px;
}
</style>
