<script setup lang="ts">
import type { Citation } from "@/types";

withDefaults(defineProps<{ citations: Citation[]; maxChars?: number; title?: string }>(), {
  maxChars: 160,
  title: "引用来源",
});

function snippet(text: string, max: number) {
  const t = (text || "").replace(/\s+/g, " ").trim();
  return t.length > max ? `${t.slice(0, max)}…` : t;
}
</script>

<template>
  <div v-if="citations?.length" class="cites">
    <div class="cites-title">{{ title }}</div>
    <div v-for="(c, i) in citations" :key="i" class="cite">
      <b>{{ c.citation }}</b><br />
      {{ snippet(c.text, maxChars) }}
    </div>
  </div>
</template>

<style scoped>
.cites {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cites-title {
  font-size: 12px;
  color: var(--muted);
  font-weight: 500;
}
</style>
