<script setup lang="ts">
import { computed, ref } from "vue";
import { useChart } from "@/composables/echarts";
import type { Level } from "@/types";

const props = withDefaults(defineProps<{ score: number; level: Level; size?: number }>(), {
  size: 152,
});

const LEVEL_COLOR: Record<Level, string> = { red: "#dc2626", yellow: "#d97706", green: "#047857" };

const el = ref<HTMLElement | null>(null);
const color = computed(() => LEVEL_COLOR[props.level] ?? "#1d4ed8");
const value = computed(() => Math.max(0, Math.min(100, Number(props.score) || 0)));

const option = computed(() => ({
  animationDuration: 600,
  series: [
    {
      type: "pie",
      radius: ["74%", "92%"],
      startAngle: 90,
      silent: true,
      avoidLabelOverlap: false,
      label: { show: false },
      labelLine: { show: false },
      itemStyle: { borderRadius: 10 },
      data: [
        { value: value.value, itemStyle: { color: color.value } },
        { value: 100 - value.value, itemStyle: { color: "#eef0f3" } },
      ],
    },
  ],
}));

useChart(el, option);
</script>

<template>
  <div class="ring" :style="{ width: `${size}px`, height: `${size}px` }">
    <div ref="el" class="ring-canvas"></div>
    <div class="ring-center">
      <b>{{ Math.round(value) }}</b>
      <span>风险分 / 100</span>
    </div>
  </div>
</template>

<style scoped>
.ring {
  position: relative;
  flex: 0 0 auto;
}
.ring-canvas {
  position: absolute;
  inset: 0;
}
.ring-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  pointer-events: none;
}
.ring-center b {
  font-size: 30px;
  font-weight: 500;
  line-height: 1;
  color: var(--text);
  font-variant-numeric: tabular-nums;
}
.ring-center span {
  font-size: 11px;
  color: var(--muted);
}
</style>
