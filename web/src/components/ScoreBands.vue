<script setup lang="ts">
import { computed, ref } from "vue";
import { useChart } from "@/composables/echarts";

/**
 * 成绩分布（教师端特有视角）。
 * 老师看分布而不是看均分：均分 77 分看不出是「大家都 77」还是
 * 「一半 95 一半 55」，而这两种情况的教法完全不同。
 */
const props = withDefaults(
  defineProps<{
    dist: { label: string; count: number; pct: number }[];
    avg?: number;
    passRate?: number;
    height?: number;
  }>(),
  { avg: 0, passRate: 0, height: 208 },
);

const el = ref<HTMLElement | null>(null);

// 低于 60 的柱子单独标红：这是老师唯一必须当场处理的区间
const COLOR = ["#b45309", "#d97706", "#e8a33d", "#94a3b8", "#dc2626"];

const option = computed(() => {
  const rows = props.dist || [];
  return {
    grid: { left: 8, right: 12, top: 22, bottom: 4, containLabel: true },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (p: any[]) => {
        const i = rows.findIndex((r) => r.label === p[0]?.name);
        const r = rows[i];
        return r ? `${r.label}<br/>${r.count} 人（${r.pct}%）` : "";
      },
    },
    xAxis: {
      type: "category",
      data: rows.map((r) => r.label),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#eadfcd" } },
      axisLabel: { fontSize: 11, color: "#5d4b3a", interval: 0 },
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: "#f2e9da" } },
      axisLabel: { fontSize: 11, color: "#8e7a66" },
    },
    series: [
      {
        type: "bar",
        barWidth: "46%",
        data: rows.map((r, i) => ({
          value: r.count,
          itemStyle: { color: COLOR[i] ?? "#d97706", borderRadius: [5, 5, 0, 0] },
        })),
        label: { show: true, position: "top", fontSize: 11, color: "#5d4b3a" },
      },
    ],
  };
});

useChart(el, option);
</script>

<template>
  <div class="bands">
    <div class="bands-meta">
      <span>课堂均分 <b>{{ avg }}</b></span>
      <span>及格率 <b>{{ passRate }}%</b></span>
    </div>
    <div ref="el" :style="{ height: `${height}px`, width: '100%' }"></div>
  </div>
</template>

<style scoped>
.bands-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--muted);
  margin: -2px 0 2px;
}
.bands-meta b {
  color: var(--text);
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}
</style>
