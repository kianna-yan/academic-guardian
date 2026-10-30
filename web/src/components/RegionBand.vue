<script setup lang="ts">
/**
 * 区域标带：把长页面切成几个"区域"，让一眼能看出这块在讲什么。
 * 不参与任何数据逻辑，纯排版，但页面上有没有它，观感差别很大。
 */
defineProps<{
  no: string;
  title: string;
  desc?: string;
  tone?: "learn" | "archive" | "risk" | "ai";
}>();
</script>

<template>
  <div class="region-band" :class="tone || 'archive'">
    <span class="rb-no">{{ no }}</span>
    <div class="rb-text">
      <b>{{ title }}</b>
      <em v-if="desc">{{ desc }}</em>
    </div>
    <div class="rb-side"><slot /></div>
  </div>
</template>

<style scoped>
.region-band {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 22px 0 10px;
  padding: 0 2px;
  scroll-margin-top: 8px;
}
.region-band:first-child {
  margin-top: 0;
}
.rb-no {
  flex: none;
  width: 26px;
  height: 26px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.5px;
  font-variant-numeric: tabular-nums;
  background: var(--brand-soft);
  color: var(--brand);
  border: 1px solid rgba(217, 119, 6, 0.18);
}
.rb-text {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
  flex: 1;
}
.rb-text b {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
}
.rb-text em {
  font-style: normal;
  font-size: 11.5px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rb-side {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
}
.region-band.learn .rb-no {
  background: #ecfdf5;
  color: #047857;
  border-color: rgba(4, 120, 87, 0.2);
}
.region-band.risk .rb-no {
  background: #fef2f2;
  color: #dc2626;
  border-color: rgba(220, 38, 38, 0.2);
}
.region-band.ai .rb-no {
  background: #eef2ff;
  color: #4338ca;
  border-color: rgba(67, 56, 202, 0.18);
}
@media (max-width: 760px) {
  .rb-text em {
    display: none;
  }
}
</style>
