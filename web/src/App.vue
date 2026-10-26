<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import PasswordDialog from "@/components/PasswordDialog.vue";
import SideBar from "@/components/SideBar.vue";
import TopBar from "@/components/TopBar.vue";
import { useAppStore } from "@/stores/app";
import { useAuthStore } from "@/stores/auth";
import { useChatStore } from "@/stores/chat";
import type { Role } from "@/types";

const app = useAppStore();
const auth = useAuthStore();
const chat = useChatStore();
const route = useRoute();
const pwdOpen = ref(false);

const isLogin = computed(() => route.name === "login");
const role = computed<Role>(() => auth.profile?.role ?? "student");

// 切端时重置对话，避免把上一个身份的上下文带进来
watch(
  () => role.value,
  (r) => {
    if (!isLogin.value) chat.ensure(r);
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
