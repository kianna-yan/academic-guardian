<script setup lang="ts">
import { computed, ref } from "vue";
import { useChart } from "@/composables/echarts";

/**
 * 逐周出勤（教师端特有）。
 * 学生端只会说「我缺了 3 次」，老师要的是「第几周开始塌的」——
 * 塌在期中考前一周，和塌在第 1 周，处理方式完全不一样。
 */
const props = withDefaults(
  defineProps<{
    weekly: { week: number; absent: number; late: number; present: number; total: number }[];
    height?: number;
  }>(),
  { height: 208 },
);

const el = ref<HTMLElement | null>(null);

const option = computed(() => {
  const rows = props.weekly || [];
  return {
    grid: { left: 8, right: 12, top: 26, bottom: 4, containLabel: true },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (p: any[]) => {
        const w = rows[p[0]?.dataIndex ?? 0];
        if (!w) return "";
        return `第 ${w.week} 周（${w.total} 人次）<br/>旷课 ${w.absent}<br/>迟到 ${w.late}<br/>到课 ${w.present}`;
      },
    },
    legend: {
      top: 0,
      right: 0,
      itemWidth: 8,
      itemHeight: 8,
      textStyle: { fontSize: 11, color: "#5d4b3a" },
      data: ["旷课", "迟到"],
    },
    xAxis: {
      type: "category",
      data: rows.map((r) => `第${r.week}周`),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#eadfcd" } },
      axisLabel: { fontSize: 10.5, color: "#8e7a66" },
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: "#f2e9da" } },
      axisLabel: { fontSize: 11, color: "#8e7a66" },
    },
    series: [
      {
        name: "旷课",
        type: "bar",
        stack: "a",
        barWidth: "46%",
        itemStyle: { color: "#dc2626", borderRadius: [0, 0, 0, 0] },
        data: rows.map((r) => r.absent),
      },
      {
        name: "迟到",
        type: "bar",
        stack: "a",
        itemStyle: { color: "#e8a33d", borderRadius: [4, 4, 0, 0] },
        data: rows.map((r) => r.late),
      },
    ],
  };
});

useChart(el, option);
</script>

<template>
  <div ref="el" :style="{ height: `${height}px`, width: '100%' }"></div>
</template>
