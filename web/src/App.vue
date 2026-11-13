<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import { ElMessage } from "element-plus/es/components/message/index";
import PasswordDialog from "@/components/PasswordDialog.vue";
import NoticeStack from "@/components/NoticeStack.vue";
import StarWipe from "@/components/StarWipe.vue";
import TopBar from "@/components/TopBar.vue";
import AiSheet from "@/components/portal/AiSheet.vue";
import { fetchLlmStatus, type LlmStatus } from "@/api/client";
import { useAppStore } from "@/stores/app";
import { HOME_OF, useAuthStore } from "@/stores/auth";
import { useChatStore } from "@/stores/chat";
import { useNoticeStore } from "@/stores/notices";
import type { NoticeItem, Role } from "@/types";

const app = useAppStore();
const auth = useAuthStore();
const chat = useChatStore();
const notices = useNoticeStore();
const route = useRoute();
const router = useRouter();
const pwdOpen = ref(false);

const isLogin = computed(() => route.name === "login");
const role = computed<Role>(() => auth.profile?.role ?? "student");

/**
 * 全站背景的星点：写死的确定性伪随机，刷新不跳动。
 * 只在纸面上撒一层极淡的点，不抢任何数据内容。
 */
const bgStars = (() => {
  let seed = 20261105;
  const rnd = () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 4294967296;
  };
  return Array.from({ length: 34 }, () => ({
    x: (rnd() * 100).toFixed(2),
    y: (rnd() * 100).toFixed(2),
    s: (1.6 + rnd() * 2.2).toFixed(1),
    o: (0.1 + rnd() * 0.16).toFixed(2),
    d: (rnd() * 7).toFixed(1),
  }));
})();
/** 门户首屏：整页只有画布，不出现看板 */
const isHome = computed(() => !!route.meta.home);
/** 门户是唯一的入口层，进了任何内页都给一条回程路 + 一个唤起 AI 的口子 */
const pageTitle = computed(() => (isHome.value ? "" : String(route.meta.title || "")));

function backHome() {
  void router.push(HOME_OF[role.value] || "/student");
}

/* ------------------------------------------------------------------ */
/* 返回门户：滚出视口后，自动变成一只可拖动的浮窗                        */
/* ------------------------------------------------------------------ */

const viewEl = ref<HTMLElement | null>(null);
const backBarEl = ref<HTMLElement | null>(null);
/** 原按钮是否已经被完全滚出内容区上沿 */
const backHidden = ref(false);
/** 浮窗位置（视口坐标）：默认还在左上，和原按钮同一侧，不用满屏找 */
const floatPos = ref({ x: 22, y: 74 });
/** 浮窗尺寸（与 .back-btn 一致：120×28 左右，留一点余量做边界夹取） */
const FLOAT_W = 104;
const FLOAT_H = 28;

function clampFloat(x: number, y: number) {
  const maxX = Math.max(8, window.innerWidth - FLOAT_W - 8);
  const maxY = Math.max(8, window.innerHeight - FLOAT_H - 8);
  return { x: Math.min(Math.max(8, x), maxX), y: Math.min(Math.max(8, y), maxY) };
}

/** 内容区滚动时算一次：按钮整条越过内容区上沿，就是"被完全挡住" */
function readScroll() {
  const view = viewEl.value;
  const bar = backBarEl.value;
  if (!view || !bar) {
    backHidden.value = false;
    return;
  }
  const vTop = view.getBoundingClientRect().top;
  backHidden.value = bar.getBoundingClientRect().bottom <= vTop + 1;
}

let drag: { id: number; x0: number; y0: number; ox: number; oy: number; moved: boolean } | null = null;

function onFloatDown(e: PointerEvent) {
  const el = e.currentTarget as HTMLElement;
  el.setPointerCapture(e.pointerId);
  drag = {
    id: e.pointerId,
    x0: e.clientX,
    y0: e.clientY,
    ox: floatPos.value.x,
    oy: floatPos.value.y,
    moved: false,
  };
}
function onFloatMove(e: PointerEvent) {
  if (!drag || e.pointerId !== drag.id) return;
  const dx = e.clientX - drag.x0;
  const dy = e.clientY - drag.y0;
  // 4px 以内当手抖：既不算拖动，也不会吞掉这一次点击
  if (!drag.moved && Math.hypot(dx, dy) > 4) drag.moved = true;
  if (!drag.moved) return;
  floatPos.value = clampFloat(drag.ox + dx, drag.oy + dy);
}
function onFloatUp(e: PointerEvent) {
  if (!drag || e.pointerId !== drag.id) return;
  const moved = drag.moved;
  drag = null;
  // 拖过就只是放下，没拖过才算点了"返回门户"
  if (!moved) backHome();
}

watch(viewEl, (el, old) => {
  old?.removeEventListener("scroll", readScroll);
  el?.addEventListener("scroll", readScroll, { passive: true });
  requestAnimationFrame(readScroll);
});
// 换页、改窗口大小都要重新量：新页面滚动位置是 0，浮窗该收回去
watch(() => route.path, () => requestAnimationFrame(readScroll));
function onResize() {
  floatPos.value = clampFloat(floatPos.value.x, floatPos.value.y);
  readScroll();
}
onMounted(() => window.addEventListener("resize", onResize, { passive: true }));

/**
 * 端口开屏（星坠揭幕）。
 *
 * 只在「进入某个端」的那一刻播：点击端入口、登录后落到自己的端、从内页退回门户。
 * 端内部换看板不播——那只是同一个人在同一张桌面前挪了下位置，每次点节点都
 * 遮 1.8 秒会变成等待。
 */
const wipeSeq = ref(0);
/** 开屏进行中：这段时间到的消息先排队，幕布散尽再一起弹 */
const wiping = ref(false);
/**
 * 预备幕：路由刚开始跳转、动画还没起的那一小段，先铺一块不透明幕布。
 * 少了它，目标端口会用真实页面顶上这一帧——看起来就是"开屏时页面闪了一下"。
 */
const wipeArmed = ref(false);
/**
 * 幕布此刻是否盖着（三路来源统一到这一个开关）：
 *   a. HTML 壳里的静态首屏幕（直接打开端口地址时，比 Vue 更早）
 *   b. 路由跳转时的预备幕
 *   c. 开屏动画本身
 * 消息弹窗只在 veilUp 为 false 时才弹——盖着幕弹出去等于没弹。
 */
const veilUp = ref(document.documentElement.classList.contains("v11-veil"));
let armTimer = 0;

/** 撤掉 HTML 里的静态首屏幕（开屏动画已经接管，撤了也看不出来） */
function dropBootVeil() {
  document.documentElement.classList.remove("v11-veil");
}

function armWipe() {
  wipeArmed.value = true;
  veilUp.value = true;
  window.clearTimeout(armTimer);
  // 兜底：跳转被拦下、token 失效、后端一直不回……6 秒后自己撤幕，
  // 别把人关在绿屏里（正常进场 0.3 秒内就被真正的开屏接管了）
  armTimer = window.setTimeout(() => {
    wipeArmed.value = false;
    dropBootVeil();
    if (!wiping.value) {
      veilUp.value = false;
    }
  }, 6000);
}

/** 撤预备幕：只在"确实不该盖"的时候调，开屏起播前不要调（会闪一帧） */
function disarmWipe() {
  window.clearTimeout(armTimer);
  wipeArmed.value = false;
  if (!wiping.value) {
    dropBootVeil();
    veilUp.value = false;
  }
}

// 跳转一开始就盖幕。刷新页面时 profile 还没换回来，所以看 token：
// 有 token 就按"已登录"处理，不能等身份到手才盖——那时页面已经画出来了
router.beforeEach((to, from) => {
  if (!to.meta.home) return;
  if (to.path === from.path) return;
  if (!auth.profile && !auth.token) return;
  armWipe();
});
router.afterEach((_to, _from, failure) => {
  if (failure) disarmWipe();
});

// 首屏（刷新页面 / 直接打开端口地址）：全局守卫是在 App 挂载时才注册的，
// 这时初始导航早就跑完了，守卫根本没见过第一次跳转。所以这里按当前路由补一次——
// 只要落在端口、本地还有 token，就把幕布立在第一帧之前（HTML 那块幕更早，这里接上状态）
if (route.meta.home && (auth.token || auth.profile)) armWipe();

let lastWipePath = "";
watch(
  () => [route.path, !!auth.profile] as const,
  ([path, hasProfile]) => {
    // 初始导航还没落定时 route.name 是空的：这时候既不知道进的是哪个端，
    // 也不该撤幕（以前就是在这里把首屏静态幕提前撤了，页面于是先露一帧）
    if (!route.name) return;
    if (route.name === "login") {
      lastWipePath = "";
      disarmWipe();
      return;
    }
    if (!hasProfile) return;
    if (!route.meta.home) {
      // 进了端内部：清掉记录，下次回到端口入口重新播
      lastWipePath = "";
      disarmWipe();
      return;
    }
    // 同一路径的 query 变化（如 blocked 提示）不算重新进端
    if (path === lastWipePath) return;
    lastWipePath = path;
    // 只撤预备幕，别动 veilUp：真正的开屏马上就上，中间不能有缝
    window.clearTimeout(armTimer);
    wipeArmed.value = false;
    wipeSeq.value++;
  },
  { immediate: true },
);

function onWipeStart() {
  wiping.value = true;
  veilUp.value = true;
  // 等这一帧画完再撤静态幕：此时开屏的两块绿幕已经上屏，撤掉看不出接缝
  requestAnimationFrame(() => dropBootVeil());
}
function onWipeDone() {
  wiping.value = false;
  dropBootVeil();
  veilUp.value = false;
}


// 切端 / 换账号时都重置对话面板：角色和账号任一变化都要换会话，
// 否则同角色换账号（学生 A 退出 → 学生 B 登录）会短暂看到上一人的消息
watch(
  () => `${role.value}:${auth.profile?.account ?? ""}`,
  () => {
    if (!isLogin.value && auth.profile) chat.ensure(role.value);
  },
  { immediate: true },
);

// 登录时是「身份先到、路由后跳」，上面那个 watch 触发时还停在登录页会直接跳过，
// 于是辅导员/家长端进来看到的是学生端的问候语和建议词。这里在离开登录页时补一次。
watch(isLogin, (login) => {
  if (!login && auth.profile) chat.ensure(role.value);
});

// ---- 消息中心：登录后开始轮询，退出即停；未读的头部几条投影成右上角那一列卡片 ----

interface StackNotice {
  key: string;
  warn: boolean;
  n: NoticeItem;
}
/**
 * 右上角这一列消息卡片 = **当前未读的投影**，只在端口首页出现。
 *
 * 规则（按 2026-11-13 的反馈定）：
 * - 只在对应端口的首页出现。点进看板、对话、课表这些内页时整列隐藏——那里正在读
 *   具体的表和图，卡片只会挡路；右上角铃铛的红点照常，消息本身一条都不丢。
 * - 回到首页还在。以前是「一场登录只报到一次」，从内页退回门户就一条都不剩，用起来
 *   像消息自己消失了。现在只要没叉掉，回几次都在。
 * - 叉掉才算处理。叉掉记 id 并写进 sessionStorage：刷新页面、内页来回切都不再冒出来；
 *   但铃铛红点不动——不标已读，只是不再弹脸。
 */
const SS_DISMISS = "ag.notice.dismissed";

function ssReadIds(k: string): string[] {
  try {
    const v = JSON.parse(sessionStorage.getItem(k) || "[]");
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}
function ssWrite(k: string, v: string) {
  try {
    sessionStorage.setItem(k, v);
  } catch {
    /* 隐私模式禁写：退回纯内存，行为不变，只是刷新后叉掉的记账丢了 */
  }
}

/** 叉掉的 id：用 reactive Set，has() 才会被上面的 computed 追到 */
const dismissedKeys = reactive(new Set<string>(ssReadIds(SS_DISMISS)));

/** 窄屏不弹：顶部导航只有 40px 高，卡片一盖就把五个入口挡住；窄屏本来也靠铃铛红点 */
const narrow = ref(false);
function syncNarrow() {
  narrow.value = window.innerWidth <= 760;
}
syncNarrow();
window.addEventListener("resize", syncNarrow);
onUnmounted(() => window.removeEventListener("resize", syncNarrow));

const noticeStack = computed<StackNotice[]>(() => {
  // 不在端口首屏就不出：内页（看板/课表/对话整页）正在读具体内容，卡片只会挡路。
  // AI 抽屉也算"进了别的窗口"——它是盖在首屏上的一层，卡片会浮在对话正文上面，
  // 所以打开抽屉时同样收起来，关掉抽屉回到底层首屏再自己长回来。
  if (!isHome.value || narrow.value || chat.aiOpen) return [];
  return notices.unread
    .filter((n) => !dismissedKeys.has(n.id))
    .slice(0, 3)                       // 最多三条：再多只是噪音，剩下的都在铃铛里
    .map((n) => ({
      key: n.id,
      // 旷课与新异议用橙色感叹号，其余用灰色 i —— 与消息中心的 kind 映射一致
      warn: n.kind === "absent" || n.kind === "appeal_new",
      n,
    }));
});

/**
 * 叉掉：这条不再弹脸，并记进本标签页的「别再来」名单。
 * 不标已读——铃铛红点照旧，消息本身仍在消息中心里，只是不再挡在页面上。
 */
function dismissNotice(key: string) {
  dismissedKeys.add(key);
  ssWrite(SS_DISMISS, JSON.stringify([...dismissedKeys]));
}

/**
 * 是否真的登录过。profile 是异步 hydrate 的——页面刷新时这个 watch 会先以
 * `undefined` 触发一次，如果那时就当"退出登录"去清 sessionStorage 里的叉掉记号，
 * 刷新后叉掉的提醒又会冒回来。只有"登录过之后又掉成空"才算退出。
 */
let hadProfile = false;
watch(
  () => auth.profile?.account,
  (acc) => {
    if (acc && !isLogin.value) {
      hadProfile = true;
      // 拉一次 + 每 25 秒轮询就够了：卡片本身就是 unread 的投影，
      // 数据一变自己就跟着变，不需要再订阅「新通知到达」手工入栈。
      notices.start();
    } else {
      notices.stop();
      // 退出登录：上一个人的提醒不该留给下一个人看，叉掉的记号也一并清掉，
      // 下一个人登录时看到的应当是他自己的未读。
      dismissedKeys.clear();
      // 只有"登录过再退出"才动 sessionStorage：启动时的空 profile 不清，
      // 否则刷新就等于重新登录，叉掉的记录又回来了
      if (!hadProfile) return;
      hadProfile = false;
      try {
        sessionStorage.removeItem(SS_DISMISS);
      } catch {
        /* 隐私模式禁写，忽略 */
      }
    }
  },
  { immediate: true },
);

// 越权跳回自己端时给一句说明，而不是默默改写地址
watch(
  () => route.query.blocked,
  (v) => {
    if (typeof v === "string" && v) {
      ElMessage.warning("当前账号没有该端权限，已回到你的工作台");
    }
  },
  { immediate: true },
);

/**
 * 每次进入新的页面/端口都主动拉一次消息与待办。
 * 轮询是 25 秒一轮，切页时刚好错开就会看到旧数据（例如别处刚发来的家校消息
 * 在侧栏没有红点）。
 *
 * 弹窗不用在这里管：卡片是 `isHome` + unread 的投影，换页时自己就出现/收起，
 * 不会出现「同一批消息弹两遍」。
 */
watch(
  () => route.path,
  () => {
    if (!isLogin.value && auth.profile) void notices.refresh(true);
  },
);

/** 页内锚点与 AI 抽屉开合不换页，只补一次静默刷新，不打扰人 */
watch(
  () => `${route.hash}|${chat.aiOpen}`,
  () => {
    if (!isLogin.value && auth.profile) void notices.refresh(true);
  },
);

// ---- 大模型健康状态：掉线时顶部挂黄条，别让用户以为只是「今天变笨了」 ----
// 后端失败会静默回落规则引擎（页面不报错，只是措辞变生硬），所以这里要主动问。
const llmOff = ref<LlmStatus | null>(null);
const llmChecking = ref(false);
let llmTimer: ReturnType<typeof setInterval> | null = null;

async function pollLlm(probe = false) {
  if (isLogin.value || !auth.profile) return;
  try {
    const s = await fetchLlmStatus(probe);
    llmOff.value = s.ok ? null : s;
  } catch {
    // 查状态本身失败就当正常，别为了一条提示再弹一次错
  }
}

async function recheckLlm() {
  llmChecking.value = true;
  try {
    await pollLlm(true);
  } finally {
    llmChecking.value = false;
  }
}

watch(
  () => auth.profile?.account,
  (acc) => {
    if (llmTimer) {
      clearInterval(llmTimer);
      llmTimer = null;
    }
    if (acc && !isLogin.value) {
      pollLlm();
      llmTimer = setInterval(() => pollLlm(), 45000);
    } else {
      llmOff.value = null;
    }
  },
  { immediate: true },
);

// 每次回答结束立刻复查一次：掉线通常就发生在这一刻，等轮询太慢
watch(
  () => {
    const list = chat.messages;
    const last = list[list.length - 1];
    return last && "pending" in last ? !!last.pending : false;
  },
  (pending, was) => {
    if (was && !pending) pollLlm();
  },
);

onUnmounted(() => {
  if (llmTimer) clearInterval(llmTimer);
  window.removeEventListener("resize", onResize);
  viewEl.value?.removeEventListener("scroll", readScroll);
});
</script>

<template>
  <el-config-provider :locale="zhCn">
  <div v-if="isLogin" class="auth-page">
    <router-view />
  </div>

  <div v-else class="app">
    <!-- 全站背景：纸面上撒一层极淡的星点，滚动不动，也不吃鼠标事件 -->
    <div class="app-stars" aria-hidden="true">
      <i
        v-for="(s, i) in bgStars"
        :key="`bg-${i}`"
        :style="{
          left: `${s.x}%`,
          top: `${s.y}%`,
          width: `${s.s}px`,
          height: `${s.s}px`,
          opacity: s.o,
          animationDelay: `${s.d}s`,
        }"
      ></i>
    </div>
    <main class="main" :class="{ 'main-home': isHome }">
      <TopBar @change-password="pwdOpen = true" />

      <section ref="viewEl" class="view" :class="{ 'view-home': isHome }">
        <!-- 大模型掉线：显式说明一句，否则回答变生硬会被当成系统坏了 -->
        <div v-if="llmOff" class="llm-banner">
          <span class="llm-dot" aria-hidden="true"></span>
          <span class="llm-text">
            <b>离线模式</b>
            <template v-if="llmOff.enabled">
              ：大模型暂时不可用（{{ llmOff.reason }}），回答已改由规则引擎生成。
            </template>
            <template v-else>：未配置大模型，回答由规则引擎生成。</template>
            数据与查询不受影响。
          </span>
          <button class="link" :disabled="llmChecking" @click="recheckLlm">
            {{ llmChecking ? "检测中…" : "重试连接" }}
          </button>
        </div>

        <!-- 初始密码提醒：不挡操作，但一直可见 -->
        <div v-if="auth.mustChange" class="pwd-banner">
          <span>你仍在使用初始密码，账号信息只做了演示级保护</span>
          <button class="link" @click="pwdOpen = true">立即修改</button>
        </div>

        <!-- 内页：门户在上一层，给一条明确的回程路，并把 AI 抽屉的入口一起带过来 -->
        <div v-if="pageTitle" ref="backBarEl" class="back-bar">
          <button class="back-btn" data-test="back-home" @click="backHome">
            <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true">
              <path
                d="M14.5 6 8.5 12l6 6"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            返回门户
          </button>
          <span class="back-sep" aria-hidden="true"></span>
          <span class="back-title">{{ pageTitle }}</span>
          <button class="back-ai" data-test="back-ai" @click="chat.openAi()">问 AI</button>
        </div>

        <!-- 原按钮被滚出视口后，顶上这只浮窗：同样大小、同样长相，可以拖到任意位置。
             拖过就只是放下，没拖过（4px 内）才算点了回门户。 -->
        <Teleport to="body">
          <button
            v-if="pageTitle && backHidden"
            class="back-float"
            :style="{ left: `${floatPos.x}px`, top: `${floatPos.y}px` }"
            data-test="back-home-float"
            title="按住可以拖到任意位置，点一下回门户"
            @pointerdown="onFloatDown"
            @pointermove="onFloatMove"
            @pointerup="onFloatUp"
            @pointercancel="onFloatUp"
          >
            <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true">
              <path
                d="M14.5 6 8.5 12l6 6"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            返回门户
          </button>
        </Teleport>

        <div v-if="app.error" class="card">
          <b>初始化失败</b>
          <p class="tiny muted">{{ app.error }}</p>
          <button class="btn" @click="app.load()">重试</button>
        </div>
        <router-view v-else />
      </section>
    </main>

    <!-- AI 抽屉挂在应用层：不管当前在门户还是内页，唤起它都能铺满整个窗口 -->
    <AiSheet v-if="auth.profile" :role="role" :sid="auth.profile?.sid || null" />

    <!-- 进端口报到的消息：右上角一列折叠卡片，悬停展开。只在端口首屏出现 -->
    <NoticeStack v-if="isHome" :items="noticeStack" @close="dismissNotice" />

    <PasswordDialog v-model="pwdOpen" />
  </div>

  <!-- 端口开屏：挂在应用层、Teleport 到 body，盖住导航栏与抽屉，开场统一由它接管 -->
  <StarWipe :seq="wipeSeq" :armed="wipeArmed" @start="onWipeStart" @done="onWipeDone" />
  </el-config-provider>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
}
/* 全站背景星点：只在纸面上浮一层，不影响任何可读性 */
.app-stars {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}
.app-stars i {
  position: absolute;
  border-radius: 50%;
  background: #16564a;
  transform: translate(-50%, -50%);
  animation: bgstar 6.4s ease-in-out infinite;
}
@keyframes bgstar {
  0%,
  100% {
    opacity: 0.08;
  }
  50% {
    opacity: 0.34;
  }
}
@media (prefers-reduced-motion: reduce) {
  .app-stars i {
    animation: none;
  }
}
/* 版块页的回程条：不抢标题的层级，只是告诉人「你现在在里面，门在那边」 */
.back-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 10px;
}
.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 28px;
  padding: 0 10px 0 7px;
  border: 1px solid var(--line-strong);
  border-radius: 999px;
  background: var(--card);
  color: var(--moss);
  font-size: 12px;
  font-weight: 600;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.back-btn:hover {
  background: var(--moss);
  border-color: var(--moss);
  color: #f6f2e8;
}
/* 滚出视口后的浮窗：高度/内边距/字号/圆角与原按钮逐项对齐，
   只多了固定定位、投影和抓手光标——否则会像换了一个按钮 */
.back-float {
  position: fixed;
  z-index: 60;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 28px;
  padding: 0 10px 0 7px;
  border: 1px solid var(--line-strong);
  border-radius: 999px;
  background: var(--card);
  color: var(--moss);
  font-size: 12px;
  font-weight: 600;
  box-shadow: 0 6px 18px rgba(35, 38, 31, 0.14);
  cursor: grab;
  /* 触屏上按住拖动时不要顺带把页面滚起来 */
  touch-action: none;
  user-select: none;
  animation: back-float-in 160ms ease-out both;
}
.back-float:hover {
  background: var(--moss);
  border-color: var(--moss);
  color: #f6f2e8;
}
.back-float:active {
  cursor: grabbing;
}
@keyframes back-float-in {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
@media (prefers-reduced-motion: reduce) {
  .back-float {
    animation: none;
  }
}
.back-sep {
  width: 18px;
  height: 1px;
  background: var(--line-strong);
}
.back-title {
  font-family: var(--serif);
  font-size: 12.5px;
  color: var(--muted);
  letter-spacing: 0.02em;
}
/* 侧栏撤掉以后，内页也要有一条随时能唤起 AI 的路，否则只能退回门户。
   刻意贴左边：右上角是消息弹窗的地盘，按钮放那儿会被通知盖住点不到 */
.back-ai {
  margin-left: 4px;
  height: 28px;
  padding: 0 12px;
  border: 1px solid rgba(180, 85, 45, 0.42);
  border-radius: 999px;
  background: var(--clay-soft);
  color: var(--clay);
  font-size: 12px;
  font-weight: 600;
  transition: background 0.15s, color 0.15s;
}
.back-ai:hover {
  background: var(--clay);
  color: #fdf3ee;
}
.pwd-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin: 0 0 12px;
  padding: 9px 12px;
  border: 1px solid #fde68a;
  background: #f9efdf;
  color: #92400e;
  border-radius: 9px;
  font-size: 12.5px;
}
.llm-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 12px;
  padding: 9px 12px;
  border: 1px solid #fcd34d;
  background: #fef3c7;
  color: #92400e;
  border-radius: 9px;
  font-size: 12.5px;
  line-height: 1.55;
}
.llm-dot {
  flex: none;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #f59e0b;
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.18);
}
.llm-text {
  flex: 1;
  min-width: 0;
}
.llm-text b {
  font-weight: 700;
}
.llm-banner .link {
  flex: none;
  border: 0;
  background: transparent;
  color: #16564a;
  font-weight: 600;
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
  font-size: 12.5px;
}
.llm-banner .link:disabled {
  opacity: 0.55;
  cursor: default;
  text-decoration: none;
}
.pwd-banner .link {
  border: 0;
  background: transparent;
  color: #16564a;
  font-weight: 600;
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
  font-size: 12.5px;
}
</style>
