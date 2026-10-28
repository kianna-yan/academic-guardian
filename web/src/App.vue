<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import { ElMessage } from "element-plus/es/components/message/index";
import { ElNotification } from "element-plus/es/components/notification/index";
import PasswordDialog from "@/components/PasswordDialog.vue";
import SideBar from "@/components/SideBar.vue";
import TopBar from "@/components/TopBar.vue";
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
