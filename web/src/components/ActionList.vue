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
        <div class="action-head">
          <span v-if="a.tag" class="action-tag">{{ a.tag }}</span>
          <b>{{ a.title }}</b>
        </div>
        <p>{{ a.detail }}</p>
        <ul v-if="a.steps && a.steps.length" class="action-steps">
          <li v-for="s in a.steps" :key="s">{{ s }}</li>
        </ul>
        <div class="action-meta">
          <span v-if="showPriority" class="tag" :class="{ high: a.priority === 'high' }">
            {{ a.priority === "high" ? "优先" : a.priority === "low" ? "常规" : "常规" }}
          </span>
          <span>{{ a.owner }}</span>
          <span>{{ a.deadline }}</span>
        </div>
      </div>
    </div>
    <div v-if="!actions.length" class="empty">当前没有需要执行的干预项</div>
  </div>
</template>

<style scoped>
.action-head {
  display: flex;
  align-items: baseline;
  gap: 7px;
  flex-wrap: wrap;
}
.action-tag {
  flex: none;
  font-size: 10.5px;
  line-height: 1.5;
  padding: 1px 6px;
  border-radius: 5px;
  color: var(--brand);
  background: color-mix(in srgb, var(--brand) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--brand) 26%, transparent);
  white-space: nowrap;
}
.action-steps {
  margin: 6px 0 0;
  padding-left: 16px;
  font-size: 12px;
  color: var(--text-2);
}
.action-steps li {
  margin: 3px 0;
  line-height: 1.6;
}
</style>
