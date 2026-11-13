<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import AgentBriefing from "@/components/AgentBriefing.vue";
import CitationList from "@/components/CitationList.vue";
import MarkdownBody from "@/components/MarkdownBody.vue";
import TraceSteps from "@/components/TraceSteps.vue";
import { useChatStore, DEFAULT_SUGGEST } from "@/stores/chat";
import { useAppStore } from "@/stores/app";
import { api } from "@/api/client";
import { PORTAL_PROMPTS } from "@/config/prompts";
import {
  humanSize,
  pickImage,
  pickVideo,
  startRecording,
  type PickedMedia,
  type Recorder,
} from "@/composables/media";
import type { Role, SkillMeta, SkillSub } from "@/types";

const props = defineProps<{ role: Role; sid: string | null; sheet?: boolean }>();
const emit = defineEmits<{ (e: "close"): void }>();

const chat = useChatStore();
const app = useAppStore();
const draft = ref("");
const stream = ref<HTMLElement | null>(null);

/** 右下角那块「已接入大模型」的牌子：模型名直接读后端 /meta，不写死 */
const modelName = computed(() => String(app.meta?.llm?.model || "glm-5.3-flash").trim());
/** 没配 key 就别写「实时推理」：顶上黄条正说着「模型未接入」，两边对不上 */
const modelOnline = computed(() => app.meta?.llm?.enabled !== false);
const modelLine = computed(
  () => `${modelName.value} · ${modelOnline.value ? "实时推理" : "规则兜底"}`,
);
/**
 * 第二个模型：后端 .env 里另配了一只快模型（LLM_ROUTE_MODEL = glm-4.5-air），
 * 只负责「这句话该调哪个工具」，首字延迟比主模型低一个量级。牌子上一并亮出来，
 * 免得看的人以为只接了一个模型。
 */
const routeName = computed(() => String(app.meta?.llm?.route_model || "glm-4.5-air").trim());
const routeLine = computed(() =>
  routeName.value && routeName.value !== modelName.value ? `${routeName.value} · 意图路由` : "",
);

/** 每个端的整页对话：标题、副标题、以及收起按钮的文案 */
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

function closeSheet() {
  emit("close");
}

function scrollToBottom() {
  nextTick(() => {
    const el = stream.value;
    if (!el) return;
    // 只有开场简报和问候语时钉在顶部：否则一进来就看到简报被切掉半个头
    if (chat.messages.length <= 1) {
      el.scrollTop = 0;
      return;
    }
    el.scrollTop = el.scrollHeight;
  });
}

// 流式输出时文本逐字增长，靠深度监听把视口钉在底部
watch(() => chat.messages, scrollToBottom, { deep: true });
watch(() => props.role, scrollToBottom);

// 页面切走时把还在跑的流掐掉，否则请求会悬挂并往已卸载的视图里写数据。
// 抽屉里的对话例外：收起只是把面板滑回底部，回答该继续跑完，再展开还在。
onBeforeUnmount(() => {
  cleanupRec();
  if (!props.sheet) chat.abort();
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

const MEDIA_ICON: Record<string, string> = { image: "🖼", video: "🎬", audio: "🎤", text: "📄" };
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
  const typed = (text ?? "").trim();
  const media = attachments.value;
  // 挂着的提示词胶囊在这一刻才展开成全文，拼在用户输入前面
  const prompts = promptTags.value
    .map((t) => promptText(t))
    .filter(Boolean);
  const content = [...prompts, typed].filter(Boolean).join("\n\n").trim();
  if (!content && !media.length) return;
  if (chat.streaming) return;
  const pick = pendingSkill.value;
  draft.value = "";
  attachments.value = [];
  promptTags.value = [];
  pendingSkill.value = null;
  cleanupRec();
  chat.send(props.role, props.sid, content, media, pick ? { key: pick.skill.key, sub: pick.sub?.key } : null);
  // 技能请求：文字归对话，文件另开一路，互不阻塞（演练类没有文件）
  if (pick && pick.skill.ext) void makeFile(pick, content);
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

/* ------------------------------------------------------------------
 * 「+」里的两个新入口：上传文档 / Skill
 *
 * 上传文档：文件交给后端抽正文，回来当成 kind=text 的附件随提问发出——
 *   和图片走同一条链路，模型看到的就是原文，不需要为它单开一套消息协议。
 * Skill：菜单由后端按端下发（学生/家长/导员/教务看到的项不一样，提示语也不一样）。
 *   报告类点了先预填一句提示（用户可以改），发送时后台按当前学情现场渲染文件，
 *   生成完给一张下载卡；文书辅助进二级菜单选文书类型；家校沟通进二级菜单选家长类型，
 *   之后直接在对话里演练；图表解读不产文件，开的是图片选择，走已有的视觉识别。
 * ---------------------------------------------------------------- */
const docInput = ref<HTMLInputElement | null>(null);
const docBusy = ref(false);
const skillOpen = ref(false);
const skills = ref<SkillMeta[]>([]);
/** 正在展开二级项的技能（文书辅助 / 家校沟通）；null 时显示一级菜单 */
const skillDrill = ref<SkillMeta | null>(null);
interface PendingSkill {
  skill: SkillMeta;
  sub?: SkillSub;
}
const pendingSkill = ref<PendingSkill | null>(null);

interface MadeFile {
  id: string;
  key: string;
  name: string;
  size: string;
  url: string;
  state: "loading" | "ok" | "fail";
  note?: string;
}
const madeFiles = ref<MadeFile[]>([]);

async function loadSkills() {
  if (skills.value.length) return;
  try {
    skills.value = (await api.skills()).items || [];
  } catch {
    /* 拿不到菜单就当没这个入口，别挡住打字 */
  }
}

function openDoc() {
  menuOpen.value = false;
  skillOpen.value = false;
  promptOpen.value = false;
  docInput.value?.click();
}

async function onDocPicked(ev: Event) {
  const input = ev.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  if (file.size > 20 * 1024 * 1024) {
    note(`文件太大了（${humanSize(file.size)}），换一份小于 20MB 的`);
    return;
  }
  docBusy.value = true;
  note("正在把这份文档读成文字…");
  try {
    const d = await api.uploadDoc(file);
    addAttach({
      id: `doc${Date.now().toString(36)}`,
      kind: "text",
      name: d.name || file.name,
      mime: file.type || "text/plain",
      data: d.text,
      size: file.size,
      chars: d.chars,
    });
    if (d.note) note(`${d.name}：${d.note}`);
    else note(`已读入「${d.name}」，共 ${d.chars} 字`);
  } catch (e: any) {
    note((await blobDetail(e)) || e?.message || "这份文档读不出来，换一份试试");
  } finally {
    docBusy.value = false;
  }
}

/** 出错时后端在某些分支把 detail 包在 blob 里，这里统一取出来 */
async function blobDetail(e: any): Promise<string> {
  const d = e?.response?.data;
  if (d instanceof Blob) {
    try {
      const parsed = JSON.parse(await d.text());
      return parsed?.detail || "";
    } catch {
      return "";
    }
  }
  return d?.detail || "";
}

function toggleSkill() {
  void loadSkills();
  skillOpen.value = !skillOpen.value;
  promptOpen.value = false;
  if (!skillOpen.value) skillDrill.value = null;
}

/* ------------------------------------------------------------------
 * 预置提示词：每个端一份「按需写好的提问模板」。
 * 点「添加」后输入框里只落一枚【标签】胶囊，完整内容悬停胶囊即可查看；
 * 发送时才把选中的提示词全文拼在用户输入的前面一起发出去。
 * ---------------------------------------------------------------- */
const promptOpen = ref(false);
const promptPicked = ref<number | null>(null);
const promptList = computed(() => PORTAL_PROMPTS[props.role] ?? []);
/** 已添加到输入框的提示词标签（只存 tag，全文发送时再查） */
const promptTags = ref<string[]>([]);

function togglePrompt() {
  promptOpen.value = !promptOpen.value;
  skillOpen.value = false;
  skillDrill.value = null;
  promptPicked.value = null;
}

/** 选中的提示词以胶囊形式挂在输入框上方，重复添加只留一条 */
function addPrompt() {
  const p = promptPicked.value != null ? promptList.value[promptPicked.value] : null;
  if (!p) return;
  if (!promptTags.value.includes(p.tag)) {
    promptTags.value = [...promptTags.value, p.tag];
  }
  promptOpen.value = false;
  promptPicked.value = null;
  menuOpen.value = false;
  nextTick(() => draftEl.value?.focus());
}

function removePromptTag(tag: string) {
  promptTags.value = promptTags.value.filter((t) => t !== tag);
}

/** 悬停胶囊时展示的完整提示词内容 */
function promptText(tag: string): string {
  return promptList.value.find((p) => p.tag === tag)?.text ?? "";
}

/** 面板里悬停某条提示词时，在旁边浮出完整内容（fixed 定位，避免被滚动面板裁剪） */
const hoverTip = ref<{ x: number; y: number; tag: string; text: string } | null>(null);

function showHoverTip(e: MouseEvent, p: { tag: string; text: string }) {
  const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
  const w = Math.min(340, window.innerWidth - 24);
  let x = r.right + 10;
  if (x + w > window.innerWidth - 8) x = r.left - w - 10;
  if (x < 8) x = 8;
  const y = Math.min(Math.max(r.top - 6, 8), Math.max(8, window.innerHeight - 250));
  hoverTip.value = { x, y, tag: p.tag, text: p.text };
}

function hideHoverTip() {
  hoverTip.value = null;
}

/** 输入框有字、有附件或挂着提示词胶囊，都可以发送 */
const canSend = computed(
  () => Boolean(draft.value.trim()) || attachments.value.length > 0 || promptTags.value.length > 0,
);

/** 有二级项的（文书类型 / 家长类型）先在菜单里选，别把 6 个文书塞进一级菜单 */
function chooseSkill(s: SkillMeta) {
  if (s.subs?.length) {
    skillDrill.value = s;
    return;
  }
  pickSkill(s);
}

function chooseSub(s: SkillMeta, sub: SkillSub) {
  pickSkill(s, sub);
}

function pickSkill(s: SkillMeta, sub?: SkillSub) {
  skillOpen.value = false;
  skillDrill.value = null;
  menuOpen.value = false;
  if (s.kind === "image") {
    // 图表解读：直接开图片选择，选完图再配一句话就能发
    if (!draft.value.trim()) draft.value = s.hint;
    imageInput.value?.click();
    return;
  }
  pendingSkill.value = { skill: s, sub };
  if (!draft.value.trim()) {
    // 预填的话必须带端口味：这句会原样显示在输入框里
    if (sub) {
      draft.value =
        s.kind === "draft" ? `帮我起草一份《${sub.name}》` : `开始一场「${sub.name}」的沟通演练`;
    } else {
      draft.value = s.hint;
    }
  }
}

/** 生成技能文件：先摆一张「正在生成」的卡片，回来换成下载链接 */
async function makeFile(pick: PendingSkill, note = "") {
  const s = pick.skill;
  const what = pick.sub ? pick.sub.name : s.name.replace(" 生成", "");
  const row: MadeFile = {
    id: `f${Date.now().toString(36)}`,
    key: s.key,
    name: `正在生成${what}…`,
    size: "",
    url: "",
    state: "loading",
  };
  madeFiles.value = [...madeFiles.value, row];
  try {
    // note 是刚发出去的那句话：导员没固定学生，后端要靠它把名字解析出来
    const { blob, name } = await api.exportSkill(s.key, props.sid, pick.sub?.key, note);
    row.name = name;
    row.size = humanSize(blob.size);
    row.url = URL.createObjectURL(blob);
    row.state = "ok";
  } catch (e: any) {
    row.state = "fail";
    row.name = `${s.name}没成功`;
    row.note = (await blobDetail(e)) || "后端没返回文件，稍后再试一次";
  }
  madeFiles.value = [...madeFiles.value];
}

/** 点「+」外面就收起菜单；Esc 同样 */
function onDocClick() {
  menuOpen.value = false;
  skillOpen.value = false;
  skillDrill.value = null;
  promptOpen.value = false;
}
watch(menuOpen, (v) => {
  if (v) document.addEventListener("click", onDocClick);
  else document.removeEventListener("click", onDocClick);
});
onBeforeUnmount(() => document.removeEventListener("click", onDocClick));

/** 文件卡的 blob URL 要自己回收，否则整页一直挂着几份 PPT 的内存 */
onBeforeUnmount(() => {
  madeFiles.value.forEach((f) => f.url && URL.revokeObjectURL(f.url));
});
watch(() => madeFiles.value.length, scrollToBottom);

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
  skill: "按技能生成",
  doc: "按模板起草文书",
  family: "家校沟通演练",
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
      <button class="ch-go-dash" data-test="sheet-close" @click="closeSheet">
        <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true">
          <path
            d="M6 9.5 12 15.5l6-6"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        收起
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
                    <span v-else-if="a.chars" class="bm-said">约 {{ a.chars }} 字</span>
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

        <!-- 技能产出的文件：生成中就占位，好了直接点下载 -->
        <div v-for="f in madeFiles" :key="f.id" class="ch-filecard" :class="f.state">
          <span class="fc-ico">
            {{
              f.key === "ppt" ? "📊" : f.key === "pdf" ? "📄" : "📝"
            }}
          </span>
          <div class="fc-body">
            <b>{{ f.name }}</b>
            <i v-if="f.state === 'loading'">正在按当前学情排版…</i>
            <i v-else-if="f.state === 'fail'">{{ f.note }}</i>
            <i v-else>{{ f.size }} · 已生成，点右侧下载</i>
          </div>
          <a v-if="f.state === 'ok'" class="fc-dl" :href="f.url" :download="f.name">下载</a>
          <span v-else-if="f.state === 'loading'" class="fc-spin"></span>
        </div>
      </div>
    </div>

    <div class="chat-home-foot">
      <!-- 输入区左边那块空地：明说一句「这里接的是大模型」，不是关键词匹配 -->
      <div class="ch-model" data-test="model-badge">
        <span class="mm-live" aria-hidden="true"></span>
        <div class="mm-tx">
          <b>已接入教育大模型</b>
          <i>{{ modelLine }}</i>
          <i v-if="routeLine" class="mm-alt">{{ routeLine }}</i>
        </div>
      </div>
      <div class="chat-col">
        <div v-if="suggestList.length && !attachments.length && !recording" class="ch-suggest">
          <button v-for="s in suggestList" :key="s" class="chip" @click="send(s)">{{ s }}</button>
        </div>

        <div v-if="mediaError" class="ch-media-err">{{ mediaError }}</div>

        <form class="ch-composer" @submit.prevent="submit">
          <!-- 选中的技能：发出去才会真的生成文件，先给个可撤的标签 -->
          <div v-if="pendingSkill" class="ch-skilltag">
            <span>
              {{ pendingSkill.skill.icon }} {{ pendingSkill.skill.name }}
              <template v-if="pendingSkill.sub">· {{ pendingSkill.sub.name }}</template>
            </span>
            <i>
              {{
                pendingSkill.skill.kind === "roleplay"
                  ? "演练即将开始"
                  : pendingSkill.skill.kind === "draft"
                    ? "只起草，不代提交"
                    : "发出去就按当前学情生成"
              }}
            </i>
            <button type="button" title="取消这个技能" @click="pendingSkill = null">×</button>
          </div>

          <!-- 待发送的附件：就贴在输入区里，发之前能确认带对没带对 -->
          <div v-if="attachments.length" class="ch-attach">
            <div v-for="a in attachments" :key="a.id" class="ch-attach-item">
              <img v-if="a.thumb" :src="a.thumb" :alt="a.name" />
              <span v-else class="ch-attach-ico">{{ MEDIA_ICON[a.kind] }}</span>
              <div class="ch-attach-meta">
                <span class="nm">{{ a.name }}</span>
                <span class="sz">
                  {{
                    a.kind === "text"
                      ? `约 ${a.chars || 0} 字`
                      : a.kind === "video"
                        ? `抽了 ${a.frames?.length || 0} 帧`
                        : a.duration
                          ? `${a.duration} 秒`
                          : humanSize(a.size)
                  }}
                </span>
              </div>
              <button type="button" class="ch-attach-x" title="移除" @click="removeAttach(a.id)">
                ×
              </button>
            </div>
          </div>

          <!-- 已添加的预置提示词：输入框里只显示【标签】胶囊，悬停看全文，可单个移除 -->
          <div v-if="promptTags.length" class="ch-ptags">
            <div v-for="t in promptTags" :key="t" class="ch-ptag" tabindex="0">
              <span class="pt-label">【{{ t }}】</span>
              <button type="button" class="pt-x" title="移除" @click="removePromptTag(t)">×</button>
              <div class="pt-tip" role="tooltip">
                <b>【{{ t }}】</b>
                <p>{{ promptText(t) }}</p>
              </div>
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
                  <!-- 上传文档：PDF / Word / PPT / Excel / TXT 都交给后端抽正文 -->
                  <button type="button" :disabled="docBusy" @click="openDoc">
                    <span class="ic">
                      <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">
                        <path
                          d="M6 3.2h7.2L19 9v11.2a1.6 1.6 0 0 1-1.6 1.6H6a1.6 1.6 0 0 1-1.6-1.6V4.8A1.6 1.6 0 0 1 6 3.2z"
                          fill="none"
                          stroke="currentColor"
                          stroke-width="1.6"
                          stroke-linejoin="round"
                        />
                        <path
                          d="M13 3.4V9h5.6M8 13h7M8 16.4h5"
                          fill="none"
                          stroke="currentColor"
                          stroke-width="1.5"
                          stroke-linecap="round"
                        />
                      </svg>
                    </span>
                    <span class="tx">
                      <b>上传文档</b>
                      <i>{{ docBusy ? "正在读…" : "PDF / Word / PPT / Excel" }}</i>
                    </span>
                  </button>

                  <!-- 预置提示词：按端预写好的提问模板，选中后点「添加」落进输入框 -->
                  <button
                    type="button"
                    class="has-sub"
                    :class="{ on: promptOpen }"
                    @click.stop="togglePrompt"
                  >
                    <span class="ic">
                      <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">
                        <path
                          d="M4.5 5.5h15a1.4 1.4 0 0 1 1.4 1.4v8.2a1.4 1.4 0 0 1-1.4 1.4H12l-4.2 3.4v-3.4H4.5a1.4 1.4 0 0 1-1.4-1.4V6.9a1.4 1.4 0 0 1 1.4-1.4z"
                          fill="none"
                          stroke="currentColor"
                          stroke-width="1.6"
                          stroke-linejoin="round"
                        />
                        <path
                          d="M8 10h8M8 13h5"
                          fill="none"
                          stroke="currentColor"
                          stroke-width="1.5"
                          stroke-linecap="round"
                        />
                      </svg>
                    </span>
                    <span class="tx"><b>提示词</b><i>预写好的专业提问，选了就能发</i></span>
                    <span class="arr">›</span>
                  </button>

                  <!-- Skill：右侧展开二级菜单；文书/家校沟通有第二层（类型） -->
                  <button
                    type="button"
                    class="has-sub"
                    :class="{ on: skillOpen }"
                    @click.stop="toggleSkill"
                  >
                    <span class="ic">
                      <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">
                        <path
                          d="M12 3.2l1.9 4.4 4.4 1.9-4.4 1.9L12 15.8l-1.9-4.4L5.7 9.5l4.4-1.9z"
                          fill="none"
                          stroke="currentColor"
                          stroke-width="1.6"
                          stroke-linejoin="round"
                        />
                        <path
                          d="M17.6 15.2l.9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9z"
                          fill="none"
                          stroke="currentColor"
                          stroke-width="1.4"
                          stroke-linejoin="round"
                        />
                      </svg>
                    </span>
                    <span class="tx"><b>Skill</b><i>报告 · 文书 · 家校演练</i></span>
                    <span class="arr">›</span>
                  </button>

                  <!-- 二级菜单必须是「+ 菜单」的兄弟节点：
                       塞进上面的 button 里就变成按钮套按钮，浏览器会把结构拆坏 -->
                  <transition name="ch-pop">
                    <div v-if="skillOpen" class="ch-sub" @click.stop>
                      <!-- 二级项：文书类型 / 家长类型。就地展开，不做第三层浮层 -->
                      <template v-if="skillDrill">
                        <div class="sub-head sub-head-back">
                          <button type="button" class="sub-back" @click="skillDrill = null">‹ 返回</button>
                          <span>{{ skillDrill.name }}</span>
                        </div>
                        <button
                          v-for="d in skillDrill.subs"
                          :key="d.key"
                          type="button"
                          class="sub-item"
                          :data-sub="d.key"
                          @click="chooseSub(skillDrill, d)"
                        >
                          <span class="sub-ic">{{ skillDrill.icon }}</span>
                          <span class="tx"><b>{{ d.name }}</b><i>{{ d.desc }}</i></span>
                        </button>
                        <div v-if="skillDrill.note" class="sub-note">{{ skillDrill.note }}</div>
                      </template>

                      <template v-else>
                        <div class="sub-head">选一个技能</div>
                        <button
                          v-for="s in skills"
                          :key="s.key"
                          type="button"
                          class="sub-item"
                          :data-skill="s.key"
                          @click="chooseSkill(s)"
                        >
                          <span class="sub-ic">{{ s.icon }}</span>
                          <span class="tx"><b>{{ s.name }}</b><i>{{ s.desc }}</i></span>
                          <span v-if="s.subs?.length" class="sub-arr">›</span>
                        </button>
                        <div v-if="!skills.length" class="sub-empty">技能列表没加载出来，再点一次 Skill</div>
                      </template>
                    </div>
                  </transition>

                  <!-- 提示词二级面板：列表选一条，底部「添加」落进输入框 -->
                  <transition name="ch-pop">
                    <div v-if="promptOpen" class="ch-sub ch-prompts" @click.stop>
                      <div class="sub-head">选一条提示词</div>
                      <button
                        v-for="(p, i) in promptList"
                        :key="p.tag"
                        type="button"
                        class="sub-item"
                        :class="{ picked: promptPicked === i }"
                        @click="promptPicked = promptPicked === i ? null : i"
                        @mouseenter="showHoverTip($event, p)"
                        @mouseleave="hideHoverTip"
                      >
                        <span class="sub-ic pt-ic" :class="{ on: promptPicked === i }">
                          <svg
                            v-if="promptPicked !== i"
                            viewBox="0 0 24 24"
                            width="14"
                            height="14"
                            fill="none"
                            stroke="currentColor"
                            stroke-width="2.2"
                            stroke-linecap="round"
                          >
                            <path d="M4 6h16M4 12h16M4 18h9" />
                          </svg>
                          <template v-else>✓</template>
                        </span>
                        <span class="tx">
                          <b>【{{ p.tag }}】</b>
                          <i>{{ p.desc }}</i>
                        </span>
                      </button>
                      <div class="prompt-add-row">
                        <button
                          type="button"
                          class="prompt-add"
                          :disabled="promptPicked == null"
                          @click="addPrompt"
                        >
                          {{ promptPicked == null ? "先选一条" : "添加到输入框" }}
                        </button>
                      </div>
                    </div>
                  </transition>
                </div>
              </transition>
            </div>

            <span class="ch-tip">图片 · 文档 · 技能 · 按住说话</span>

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
              :disabled="chat.streaming || recording || !canSend"
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
        <input
          ref="docInput"
          type="file"
          accept=".pdf,.docx,.pptx,.xlsx,.xls,.txt,.md,.markdown,.csv"
          class="ch-file"
          @change="onDocPicked"
        />
      </div>
    </div>
  </section>

  <!-- 面板悬停浮卡：挂到 body 上，fixed 定位跟着条目走，不受面板滚动裁剪 -->
  <Teleport to="body">
    <div
      v-if="hoverTip"
      class="pt-fly"
      :style="{ left: hoverTip.x + 'px', top: hoverTip.y + 'px' }"
    >
      <b>【{{ hoverTip.tag }}】</b>
      <p>{{ hoverTip.text }}</p>
    </div>
  </Teleport>
</template>

<style scoped>
.chat-error {
  color: #9c231c;
  font-size: 12px;
  margin-top: 4px;
}
.chat-intent {
  font-size: 10.5px;
  color: #7c8175;
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
  background: #f0ebdf;
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
  color: #7c8175;
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

/* 选中的技能：一条可撤销的标签，说明「发出去会生成文件」 */
.ch-skilltag {
  display: flex;
  align-items: center;
  gap: 8px;
  width: fit-content;
  max-width: 100%;
  margin-bottom: 8px;
  padding: 5px 9px;
  border: 1px dashed #e2b884;
  border-radius: 9px;
  background: #fdf7ec;
  font-size: 11.5px;
  color: #8a5a1f;
}
.ch-skilltag i {
  font-style: normal;
  font-size: 10.5px;
  color: #b08a5a;
}
.ch-skilltag button {
  border: 0;
  background: transparent;
  color: #a98b62;
  font-size: 13px;
  line-height: 1;
  padding: 0 2px;
  cursor: pointer;
}
.ch-skilltag button:hover {
  color: #16564a;
}

/* 预置提示词胶囊：只显示【标签】，悬停浮出完整内容 */
.ch-ptags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.ch-ptag {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 6px 4px 9px;
  border: 1px solid #e2b884;
  border-radius: 9px;
  background: #fdf7ec;
  font-size: 12px;
  font-weight: 600;
  color: #8a5a1f;
  cursor: default;
}
.pt-x {
  border: 0;
  background: transparent;
  color: #b08a5a;
  font-size: 13px;
  line-height: 1;
  padding: 0 2px;
  cursor: pointer;
}
.pt-x:hover {
  color: #9c231c;
}
.pt-tip {
  position: absolute;
  left: 0;
  bottom: calc(100% + 9px);
  width: min(340px, 72vw);
  padding: 10px 12px;
  border: 1px solid #ecdfc9;
  border-radius: 10px;
  background: #fffdf8;
  box-shadow: 0 10px 28px rgba(35, 38, 31, 0.14);
  opacity: 0;
  visibility: hidden;
  transform: translateY(4px);
  transition: opacity 0.16s ease, transform 0.16s ease, visibility 0.16s;
  pointer-events: none;
  z-index: 40;
}
.pt-tip::after {
  content: "";
  position: absolute;
  left: 16px;
  top: 100%;
  border: 6px solid transparent;
  border-top-color: #fffdf8;
}
.ch-ptag:hover .pt-tip,
.ch-ptag:focus-within .pt-tip {
  opacity: 1;
  visibility: visible;
  transform: translateY(0);
}
.pt-tip b {
  display: block;
  margin-bottom: 4px;
  font-size: 12px;
  color: #16564a;
}
.pt-tip p {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.65;
  font-weight: 400;
  color: #5c5344;
  white-space: pre-line;
}

/* 面板条目的图标：干净的清单线条，选中变对勾 */
.ch-sub.ch-prompts .sub-item .sub-ic.pt-ic {
  background: #f1ece1;
  color: #5c7a68;
}
.ch-sub.ch-prompts .sub-item .sub-ic.pt-ic.on {
  background: var(--brand-soft);
  color: var(--brand);
  font-weight: 700;
}

/* 面板悬停浮卡：teleport 到 body，fixed 定位 */
.pt-fly {
  position: fixed;
  /* 对话面板是 2200 的层，浮卡必须更高才压得住 */
  z-index: 3000;
  width: min(340px, 78vw);
  max-height: 60vh;
  overflow-y: auto;
  padding: 10px 12px;
  border: 1px solid #ecdfc9;
  border-radius: 10px;
  background: #fffdf8;
  box-shadow: 0 10px 28px rgba(35, 38, 31, 0.14);
  pointer-events: none;
}
.pt-fly b {
  display: block;
  margin-bottom: 4px;
  font-size: 12px;
  color: #16564a;
}
.pt-fly p {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.65;
  color: #5c5344;
  white-space: pre-line;
}

/* 技能产出的文件卡：生成中占位，好了直接下载 */
.ch-filecard {
  display: flex;
  align-items: center;
  gap: 10px;
  max-width: 560px;
  margin-top: 10px;
  padding: 10px 12px;
  border: 1px solid #ecdfc9;
  border-radius: 12px;
  background: #fffdf8;
}
.ch-filecard .fc-ico {
  flex: 0 0 auto;
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  background: #f0ebdf;
  font-size: 16px;
}
.ch-filecard .fc-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}
.ch-filecard .fc-body b {
  font-size: 12.5px;
  color: #3b2e24;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ch-filecard .fc-body i {
  font-style: normal;
  font-size: 10.5px;
  color: #7c8175;
}
.ch-filecard.fail {
  border-color: #f3d6d6;
  background: #fef7f7;
}
.ch-filecard .fc-dl {
  flex: 0 0 auto;
  padding: 5px 12px;
  border-radius: 8px;
  background: var(--brand);
  color: #fff;
  font-size: 12px;
  text-decoration: none;
}
.ch-filecard .fc-dl:hover {
  filter: brightness(1.06);
}
.ch-filecard .fc-spin {
  flex: 0 0 auto;
  width: 14px;
  height: 14px;
  border: 2px solid #e8dcc6;
  border-top-color: var(--brand);
  border-radius: 50%;
  animation: fcspin 0.8s linear infinite;
}
@keyframes fcspin {
  to {
    transform: rotate(360deg);
  }
}

.ch-media-err {
  margin-bottom: 8px;
  font-size: 11.5px;
  color: #16564a;
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
  color: #7c8175;
}
.thought-ico {
  color: #16564a;
  margin-right: 4px;
  font-size: 10px;
}
/* 输入区左侧的「大模型接入」牌：补住那块空地，也把「我们真的接了模型」说明白 */
.ch-model {
  position: absolute;
  left: 26px;
  bottom: 24px;
  width: 202px;
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 9px 12px 10px 11px;
  border: 1px solid color-mix(in srgb, var(--moss) 22%, var(--line));
  border-left: 3px solid var(--moss);
  border-radius: 4px 12px 12px 4px;
  background: color-mix(in srgb, #fffdf9 78%, transparent);
  box-shadow: 0 6px 18px rgba(35, 38, 31, 0.05);
}
.mm-live {
  flex: none;
  margin-top: 5px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #17604f;
  box-shadow: 0 0 0 3px rgba(23, 96, 79, 0.14);
  animation: mmpulse 2.4s ease-in-out infinite;
}
@keyframes mmpulse {
  50% {
    box-shadow: 0 0 0 6px rgba(23, 96, 79, 0.06);
    opacity: 0.6;
  }
}
.mm-tx {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.mm-tx b {
  font-family: var(--serif);
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--moss);
  line-height: 1.4;
}
.mm-tx i {
  font-style: normal;
  font-size: 9.5px;
  letter-spacing: 0.02em;
  color: var(--muted);
  line-height: 1.5;
  word-break: break-all;
}
/* 第二只模型排在主模型下面，比第一行再淡一档：是补充说明，不抢主行 */
.mm-tx i.mm-alt {
  font-size: 9px;
  color: color-mix(in srgb, var(--muted) 78%, transparent);
}
/* 窄一点的窗口（≤1280，含 1080p 屏开 125% 缩放）：
   原来这里直接 display:none，于是同一份网页，宽屏能看到"接的是哪个模型"，
   窄屏却一片空白——这正是"不同人看到的界面不一样"的来源之一。
   现在改成挪到输入框上方的一行：只留模型名，说明文字收起来，信息不丢。 */
@media (max-width: 1280px) {
  .ch-model {
    position: static;
    width: fit-content;
    max-width: 100%;
    /* 和输入框同一条左边界：输入框是 860 居中，这里按同样的缩进对上去 */
    margin: 0 0 8px max(12px, calc((100% - 860px) / 2));
    padding: 5px 10px;
    border-radius: 10px;
    border-left-width: 1px;
    align-items: center;
    gap: 7px;
    background: color-mix(in srgb, var(--moss) 6%, #fffdf9);
  }
  .ch-model .mm-live {
    margin-top: 0;
  }
  .ch-model .mm-tx {
    flex-direction: row;
    align-items: baseline;
    gap: 6px;
    flex-wrap: wrap;
  }
  .ch-model .mm-tx b {
    display: none;
  }
  .ch-model .mm-tx i {
    font-size: 10.5px;
  }
  .ch-model .mm-tx i.mm-alt {
    display: none;
  }
}
</style>
