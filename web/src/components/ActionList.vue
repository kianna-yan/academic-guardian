<script setup lang="ts">
import type { Action } from "@/types";

withDefaults(defineProps<{ actions: Action[]; limit?: number; showPriority?: boolean }>(), {
  limit: 99,
  showPriority: true,
});
</script>

<template>
  <div>
    <div v-for="(a, i) in actions.slice(0, limit)" :key="a.title" class="action-item">
      <div class="action-no">{{ i + 1 }}</div>
      <div class="action-body">
        <b>{{ a.title }}</b>
        <p>{{ a.detail }}</p>
        <div class="action-meta">
          <span v-if="showPriority" class="tag" :class="{ high: a.priority === 'high' }">
            {{ a.priority === "high" ? "优先" : "常规" }}
          </span>
          <span>{{ a.owner }}</span>
          <span>{{ a.deadline }}</span>
        </div>
      </div>
    </div>
    <div v-if="!actions.length" class="empty">当前没有需要执行的干预项</div>
  </div>
</template>
