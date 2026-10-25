<script setup lang="ts">
import { computed, ref } from "vue";
import { useChart } from "@/composables/echarts";
import type { ClassStat } from "@/types";

const props = defineProps<{ byClass: Record<string, ClassStat> }>();

const el = ref<HTMLElement | null>(null);

const classes = computed(() => Object.keys(props.byClass || {}));
const height = computed(() => Math.max(140, classes.value.length * 46 + 12));

const option = computed(() => {
  const list = classes.value;
  const green = list.map((c) => {
    const s = props.byClass[c];
    return Math.max(0, s.total - s.red - s.yellow);
  });

  return {
    grid: { left: 76, right: 170, top: 6, bottom: 6 },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params: any[]) => {
        const name = params[0]?.name ?? "";
        const s = props.byClass[name];
        if (!s) return name;
        return `${name}<br/>在册 ${s.total} 人<br/>红色 ${s.red} · 黄色 ${s.yellow}<br/>平均风险分 ${s.avg_score}`;
      },
    },
    xAxis: { type: "value", show: false },
    yAxis: {
      type: "category",
      data: list,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { fontSize: 12, color: "#4b5563" },
    },
    series: [
      {
        name: "红色预警",
        type: "bar",
        stack: "t",
        barWidth: 14,
        itemStyle: { color: "#dc2626", borderRadius: [4, 0, 0, 4] },
        data: list.map((c) => props.byClass[c].red),
      },
      {
        name: "黄色关注",
        type: "bar",
        stack: "t",
        barWidth: 14,
        itemStyle: { color: "#d97706" },
        data: list.map((c) => props.byClass[c].yellow),
      },
      {
        name: "状态正常",
        type: "bar",
        stack: "t",
        barWidth: 14,
        itemStyle: { color: "#e5e7eb", borderRadius: [0, 4, 4, 0] },
        data: list.map((c, i) => {
          const s = props.byClass[c];
          return {
            value: green[i],
            label: {
              show: true,
              position: "right",
              distance: 8,
              fontSize: 11,
              color: "#6b7280",
              formatter: `红 ${s.red} · 黄 ${s.yellow} · 均分 ${s.avg_score}`,
            },
          };
        }),
      },
    ],
  };
});

useChart(el, option);
</script>

<template>
  <div>
    <div ref="el" :style="{ width: '100%', height: `${height}px` }"></div>
    <div class="compare-legend">
      <span><i style="background: #dc2626"></i>红色预警</span>
      <span><i style="background: #d97706"></i>黄色关注</span>
      <span><i style="background: #e5e7eb"></i>状态正常</span>
    </div>
  </div>
</template>

<style scoped>
.compare-legend {
  display: flex;
  gap: 14px;
  font-size: 11.5px;
  color: var(--muted);
  margin-top: 4px;
  flex-wrap: wrap;
}
.compare-legend i {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 2px;
  margin-right: 5px;
}
</style>
