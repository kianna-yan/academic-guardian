<script setup lang="ts">
import { computed, ref } from "vue";
import type { Citation } from "@/types";

const props = withDefaults(
  defineProps<{ citations: Citation[]; maxChars?: number; title?: string }>(),
  { maxChars: 160, title: "引用来源" },
);

const open = ref(false);

/** 收起时只露出「序号 + 出处」，一行一条，别把对话挤没了 */
const rows = computed(() => props.citations || []);

function snippet(text: string, max: number) {
  const t = (text || "").replace(/\s+/g, " ").trim();
  return t.length > max ? `${t.slice(0, max)}…` : t;
}

function shortPath(c: Citation) {
  const p = c.citation || "";
  return p.length > 34 ? `${p.slice(0, 33)}…` : p;
}
</script>

<template>
  <div v-if="rows.length" class="cites">
    <button type="button" class="cites-head" @click="open = !open">
      <span class="cites-title">{{ title }}</span>
      <span class="cites-n">{{ rows.length }}</span>
      <span class="cites-sub">{{ open ? "逐条核对原文" : "点开看原文与相关度" }}</span>
      <span class="cites-more">{{ open ? "收起" : "展开" }}</span>
    </button>

    <!-- 收起态：只有出处，一眼扫完 -->
    <div v-if="!open" class="cites-chips">
      <span v-for="(c, i) in rows" :key="i" class="chip">
        <em>[{{ i + 1 }}]</em>{{ shortPath(c) }}
        <b v-if="c.score_pct">{{ c.score_pct }}</b>
      </span>
    </div>

    <!-- 展开态：出处 + 学校 + 相关度 + 命中原因 + 原文 -->
    <div v-else class="cites-list">
      <div v-for="(c, i) in rows" :key="i" class="cite" :class="c.kind === 'data' ? 'is-data' : ''">
        <div class="cite-head">
          <span class="cite-idx">[{{ i + 1 }}]</span>
          <b class="cite-path">{{ c.citation }}</b>
          <span v-if="c.score_pct" class="cite-score">{{ c.score_pct }}</span>
        </div>
        <div v-if="c.school || c.why" class="cite-meta">
          <span v-if="c.school" class="cite-school">{{ c.school }}</span>
          <span v-if="c.why" class="cite-why">{{ c.why }}</span>
        </div>
        <div class="cite-text">{{ snippet(c.text, maxChars) }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cites {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.cites-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
  font-family: inherit;
  text-align: left;
}
.cites-title {
  font-size: 12px;
  color: var(--muted);
  font-weight: 500;
}
.cites-n {
  font-size: 10px;
  padding: 0 5px;
  border-radius: 8px;
  background: var(--brand-soft);
  color: var(--brand);
  font-variant-numeric: tabular-nums;
}
.cites-sub {
  font-size: 10px;
  color: #7c8175;
}
.cites-more {
  font-size: 10.5px;
  color: var(--brand);
}
.cites-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  padding: 2px 7px;
  border-radius: 6px;
  background: #fbf6ee;
  border: 1px solid #f0e6d6;
  font-size: 10.5px;
  color: #6b563e;
}
.chip em {
  font-style: normal;
  font-family: ui-monospace, monospace;
  color: var(--brand);
}
.chip b {
  font-weight: 500;
  color: #a08a72;
  font-variant-numeric: tabular-nums;
}
.cites-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cite {
  padding: 6px 9px;
  border-radius: 7px;
  background: #fbf6ee;
  border: 1px solid #f0e6d6;
}
.cite.is-data {
  background: #f3f7f2;
  border-color: #dde9db;
}
.cite-head {
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.cite-idx {
  flex: 0 0 auto;
  font-size: 10.5px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--brand);
}
.cite-path {
  flex: 1;
  min-width: 0;
  font-size: 11.5px;
  color: #5b4632;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cite-score {
  flex: 0 0 auto;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  color: #8a6a45;
  background: #fff;
  border: 1px solid #eddfc9;
  border-radius: 8px;
  padding: 0 5px;
}
.cite-meta {
  display: flex;
  gap: 6px;
  margin-top: 2px;
  font-size: 10px;
  color: #a08a72;
}
.cite-school {
  color: #8a6a45;
}
.cite-text {
  margin-top: 3px;
  font-size: 11.5px;
  line-height: 1.55;
  color: #7a6450;
}
</style>
