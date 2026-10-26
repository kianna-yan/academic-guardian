<script setup lang="ts">
import { useChatStore } from "@/stores/chat";

const chat = useChatStore();

function backChat() {
  chat.homeMode = "chat";
}
</script>

<template>
  <div class="dash-nav">
    <button class="btn-back-chat" data-test="back-chat" @click="backChat">💬 回到 AI 对话</button>
    <span class="dn-hint">对话是主入口，这里只是数据看板 —— 图表旁边的「问 AI」随时带你回去接着聊</span>
  </div>
</template>
