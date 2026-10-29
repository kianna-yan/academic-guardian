<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import { ElMessage } from "element-plus/es/components/message/index";
import { ElNotification } from "element-plus/es/components/notification/index";
import PasswordDialog from "@/components/PasswordDialog.vue";
import SideBar from "@/components/SideBar.vue";
import TopBar from "@/components/TopBar.vue";
import { fetchLlmStatus, type LlmStatus } from "@/api/client";
import { useAppStore } from "@/stores/app";
import { useAuthStore } from "@/stores/auth";
import { useChatStore } from "@/stores/chat";
import { useNoticeStore } from "@/stores/notices";
import type { Role } from "@/types";

const app = useAppStore();
const auth = useAuthStore();
const chat = useChatStore();
const notices = useNoticeStore();
const route = useRoute();
const pwdOpen = ref(false);

const isLogin = computed(() => route.name === "login");
const role = computed<Role>(() => auth.profile?.role ?? "student");

// 切端 / 换账号时都重置对话面板：角色和账号任一变化都要换会话，
// 否则同角色换账号（学生 A 退出 → 学生 B 登录）会短暂看到上一人的消息
watch(
  () => `${role.value}:${auth.profile?.account ?? ""}`,
  (key) => {
    if (!isLogin.value) chat.ensure(key.split(":")[0] as Role);
  },
  { immediate: true },
);

// ---- 消息中心：登录后开始轮询，退出即停；新通知到 → 右下角弹窗 ----
let stopArrive: (() => void) | null = null;
watch(
  () => auth.profile?.account,
  (acc) => {
    if (acc && !isLogin.value) {
      notices.start();
      stopArrive?.();
      stopArrive = notices.onArrive((items) => {
        for (const n of items.slice(0, 3)) {
          ElNotification({
            title: n.title,
            message: n.text,
            type: n.kind === "appeal_new" || n.kind === "absent" ? "warning" : "info",
            duration: 6000,
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
    <SideBar />

    <main class="main">
      <TopBar @change-password="pwdOpen = true" />

      <section class="view" :class="{ 'view-chat': chat.homeMode === 'chat' }">
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

        <div v-if="app.error" class="card">
          <b>初始化失败</b>
          <p class="tiny muted">{{ app.error }}</p>
          <button class="btn" @click="app.load()">重试</button>
        </div>
        <router-view v-else />
      </section>
    </main>

    <PasswordDialog v-model="pwdOpen" />
  </div>
  </el-config-provider>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
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
  background: #fffbeb;
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
  color: #b45309;
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
  color: #b45309;
  font-weight: 600;
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
  font-size: 12.5px;
}
</style>
