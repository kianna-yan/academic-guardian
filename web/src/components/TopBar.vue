<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessageBox } from "element-plus/es/components/message-box/index";
import { useAuthStore } from "@/stores/auth";
import NoticeBell from "@/components/NoticeBell.vue";

const emit = defineEmits<{ (e: "change-password"): void }>();

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const title = computed(() => (route.meta?.title as string) || "");
const sub = computed(() => (route.meta?.sub as string) || "");
const initial = computed(() => (auth.profile?.name || "?").slice(0, 1));
const roleLabel = computed(
  () =>
    ({ student: "学生", counselor: "辅导员", admin: "教务", parent: "家长" } as Record<string, string>)[
      auth.profile?.role || ""
    ] || "",
);

async function logout() {
  try {
    await ElMessageBox.confirm("退出后需要重新输入账号密码，确定退出吗？", "退出登录", {
      confirmButtonText: "退出",
      cancelButtonText: "取消",
      type: "warning",
    });
  } catch {
    return;
  }
  auth.logout();
  router.replace("/login");
}
</script>

<template>
  <header class="topbar">
    <div class="topbar-left">
      <h1>{{ title }}</h1>
      <p>{{ sub }}</p>
    </div>

    <div class="topbar-right">
      <NoticeBell />
      <div class="who">
        <div class="avatar">{{ initial }}</div>
        <div class="who-text">
          <b>{{ auth.profile?.name || "未登录" }}</b>
          <span>
            {{ roleLabel }}端 · {{ auth.profile?.account }}
            <em v-if="auth.mustChange" class="tag-default">初始密码</em>
          </span>
        </div>
      </div>
      <button class="btn ghost" @click="emit('change-password')">修改密码</button>
      <button class="btn ghost" @click="logout">退出</button>
    </div>
  </header>
</template>

<style scoped>
.who {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 4px 10px 4px 4px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #fff;
}
.avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--brand-soft);
  color: var(--brand);
  display: grid;
  place-items: center;
  font-size: 12.5px;
  font-weight: 600;
}
.who-text {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}
.who-text b {
  font-size: 12.5px;
  color: var(--text);
}
.who-text span {
  font-size: 11px;
  color: var(--muted);
}
.tag-default {
  font-style: normal;
  margin-left: 4px;
  padding: 0 4px;
  border-radius: 4px;
  background: #fef3c7;
  color: #92400e;
  font-size: 10px;
}
.btn.ghost {
  background: transparent;
}
@media (max-width: 760px) {
  .who-text {
    display: none;
  }
  .topbar-right {
    gap: 6px;
  }
  .btn.ghost {
    padding: 0 10px;
    font-size: 12px;
  }
}
</style>
