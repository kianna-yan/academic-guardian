<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import { ElMessage } from "element-plus/es/components/message/index";
import { ElNotification } from "element-plus/es/components/notification/index";
import PasswordDialog from "@/components/PasswordDialog.vue";
import StarWipe from "@/components/StarWipe.vue";
import TopBar from "@/components/TopBar.vue";
import AiSheet from "@/components/portal/AiSheet.vue";
import { fetchLlmStatus, type LlmStatus } from "@/api/client";
import { useAppStore } from "@/stores/app";
import { HOME_OF, useAuthStore } from "@/stores/auth";
import { useChatStore } from "@/stores/chat";
import { useNoticeStore } from "@/stores/notices";
import type { Role } from "@/types";

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

/**
 * 端口开屏（星坠揭幕）。
 *
 * 只在「进入某个端」的那一刻播：点击端入口、登录后落到自己的端、从内页退回门户。
 * 端内部换看板不播——那只是同一个人在同一张桌面前挪了下位置，每次点节点都
 * 遮 1.8 秒会变成等待。
 */
const wipeSeq = ref(0);
let lastWipePath = "";
watch(
  () => [route.path, !!auth.profile] as const,
  ([path, hasProfile]) => {
    if (route.name === "login") {
      lastWipePath = "";
      return;
    }
    if (!hasProfile) return;
    if (!route.meta.home) {
      // 进了端内部：清掉记录，下次回到端口入口重新播
      lastWipePath = "";
      return;
    }
    // 同一路径的 query 变化（如 blocked 提示）不算重新进端
    if (path === lastWipePath) return;
    lastWipePath = path;
    wipeSeq.value++;
  },
  { immediate: true },
);


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

// ---- 消息中心：登录后开始轮询，退出即停；新通知到 → 右下角弹窗 ----
let stopArrive: (() => void) | null = null;
watch(
  () => auth.profile?.account,
  (acc) => {
    if (acc && !isLogin.value) {
      notices.start();
      stopArrive?.();
      stopArrive = notices.onArrive((items) => {
        // 手机端不弹右下角通知：顶部导航只有 40px 高，弹窗一盖就把入口挡住了，
        // 消息本来就靠右上角铃铛上的红点提示，不必再抢一次注意力。
        if (window.innerWidth <= 760) return;
        for (const n of items.slice(0, 3)) {
          ElNotification({
            title: n.title,
            message: n.text,
            type: n.kind === "appeal_new" || n.kind === "absent" ? "warning" : "info",
            // 永久停留，直到使用者主动叉掉——重要消息不会被一闪而过错过
            duration: 0,
            showClose: true,
          });
        }
      });
    } else {
      notices.stop();
      stopArrive?.();
      stopArrive = null;
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
 * 在侧栏没有红点）。这里按「路径 + 锚点 + 对话/看板模式」变化补一次静默刷新。
 */
watch(
  () => `${route.path}|${route.hash}|${chat.aiOpen}`,
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

      <section class="view" :class="{ 'view-home': isHome }">
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
        <div v-if="pageTitle" class="back-bar">
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

    <PasswordDialog v-model="pwdOpen" />
  </div>

  <!-- 端口开屏：挂在应用层、Teleport 到 body，盖住导航栏与抽屉，开场统一由它接管 -->
  <StarWipe :seq="wipeSeq" />
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
