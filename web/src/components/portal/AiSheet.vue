<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from "vue";
import ChatHome from "@/components/ChatHome.vue";
import { useChatStore } from "@/stores/chat";
import type { Role } from "@/types";

/**
 * AI 抽屉：从视口底部向上展开，铺满整个主区。
 * 收起后不留任何占位，端口首屏回到图形门户的样子。
 */
const props = defineProps<{ role: Role; sid: string | null }>();

const chat = useChatStore();

const LABEL: Record<Role, string> = {
  student: "学业助手",
  counselor: "辅导员助手",
  admin: "教务助手",
  parent: "家校助手",
  teacher: "教学助手",
};

const title = computed(() => LABEL[props.role] ?? LABEL.student);

function close() {
  chat.closeAi();
}

function onKey(ev: KeyboardEvent) {
  if (ev.key === "Escape") close();
}

// 抽屉开着时才监听 Esc：管理端、教务端都在一个页面里，常驻监听会误伤别的弹窗
watch(
  () => chat.aiOpen,
  (open) => {
    if (open) window.addEventListener("keydown", onKey);
    else window.removeEventListener("keydown", onKey);
  },
  { immediate: true },
);

onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <teleport to="body">
    <transition name="aisheet">
      <div v-if="chat.aiOpen" class="ai-sheet" :aria-label="title">
        <!-- 面板本体就是对话本身：头部那条换成「收起」，其余与原来一致 -->
        <ChatHome :role="role" :sid="sid" sheet @close="close" />
      </div>
    </transition>
  </teleport>
</template>

<style scoped>
.ai-sheet {
  position: fixed;
  inset: 0 0 0 var(--side-w, 232px);
  z-index: 2200;
  display: flex;
  flex-direction: column;
  padding: 14px 20px 18px;
  background: color-mix(in srgb, var(--paper) 92%, transparent);
  backdrop-filter: blur(6px);
}
.ai-sheet :deep(.chat-home) {
  box-shadow: 0 24px 60px rgba(35, 38, 31, 0.18);
}
.aisheet-enter-active,
.aisheet-leave-active {
  transition: transform 0.34s cubic-bezier(0.22, 0.8, 0.24, 1), opacity 0.26s ease;
}
.aisheet-enter-from,
.aisheet-leave-to {
  transform: translateY(102%);
  opacity: 0.4;
}

@media (max-width: 760px) {
  .ai-sheet {
    inset: 0;
    padding: 8px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .aisheet-enter-active,
  .aisheet-leave-active {
    transition-duration: 0.01ms;
  }
}
</style>
