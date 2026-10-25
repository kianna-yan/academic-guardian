<script setup lang="ts">
import { computed, watch } from "vue";
import { useRoute } from "vue-router";
import ChatPanel from "@/components/ChatPanel.vue";
import SideBar from "@/components/SideBar.vue";
import TopBar from "@/components/TopBar.vue";
import { useAppStore } from "@/stores/app";
import { useChatStore } from "@/stores/chat";
import type { Role } from "@/types";

const app = useAppStore();
const chat = useChatStore();
const route = useRoute();

const role = computed<Role>(() => ((route.name as Role) || "student") as Role);

/** 学生端与家长端各自固定一个演示学号，辅导员端和教务端是全局视图 */
const sid = computed(() => {
  if (role.value === "student") return app.meta?.demo?.student ?? null;
  if (role.value === "parent") return app.meta?.demo?.parent ?? null;
  return null;
});

// 切端时重置对话，避免把学生端的上下文带进家长端
watch(role, (r) => chat.ensure(r), { immediate: true });
</script>

<template>
  <div class="app" :class="{ 'chat-collapsed': !chat.open }">
    <SideBar />

    <main class="main">
      <TopBar>
        <div id="top-actions"></div>
      </TopBar>

      <section class="view">
        <div v-if="app.error" class="card">
          <b>初始化失败</b>
          <p class="tiny muted">{{ app.error }}</p>
          <button class="btn" @click="app.load()">重试</button>
        </div>
        <router-view v-else />
      </section>
    </main>

    <ChatPanel v-if="chat.open" :role="role" :sid="sid" @close="chat.open = false" />
    <button v-if="!chat.open" class="chat-fab show" @click="chat.open = true">问 AI</button>
  </div>
</template>
