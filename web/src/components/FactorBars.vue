<script setup lang="ts">
import { computed } from "vue";

export interface FactorItem {
  label: string;
  points: number;
  value?: number;
}

const props = withDefaults(
  defineProps<{
    items: FactorItem[];
    /** ratio: 用归一化后的 value 画长度；pressure: 用均摊分数画长度 */
    mode?: "ratio" | "pressure";
  }>(),
  { mode: "ratio" },
);

const rows = computed(() =>
  (props.items || []).map((f) => {
    const raw =
      props.mode === "pressure" ? Number(f.points || 0) * 3 : Number(f.value ?? 0) * 100;
    const width = Math.max(0, Math.min(100, raw));
    const tone = props.mode === "pressure" ? "" : f.points > 15 ? "hot" : f.points > 9 ? "warm" : "";
    return { ...f, width, tone };
  }),
);
</script>

<template>
  <div>
    <div v-for="f in rows" :key="f.label" class="factor">
      <div class="factor-top">
        <b>{{ f.label }}</b>
        <span class="pt">{{ Number(f.points).toFixed(1) }} 分</span>
      </div>
      <div class="bar">
        <i :class="f.tone" :style="{ width: `${f.width}%` }"></i>
      </div>
    </div>
  </div>
</template>
