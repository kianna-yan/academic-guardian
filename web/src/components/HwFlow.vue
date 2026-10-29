<script setup lang="ts">
import { computed, ref } from "vue";
import { useChart } from "@/composables/echarts";

/**
 * 逐次作业（教师端特有）。
 * 提交率只看总账会骗人：6 次作业总提交率 91%，可能是每次都差 20 人，
 * 也可能是前五次满员、最后一次塌了一半。要分开看。
 */
const props = withDefaults(
  defineProps<{
    items: { title: string; due: string; submitted: number; late: number; missing: number; rate: number }[];
    height?: number;
  }>(),
  { height: 208 },
);

const el = ref<HTMLElement | null>(null);

const short = (t: string) => (t.length > 8 ? `${t.slice(0, 8)}…` : t);

const option = computed(() => {
  const rows = props.items || [];
  return {
    grid: { left: 8, right: 8, top: 26, bottom: 4, containLabel: true },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (p: any[]) => {
        const i = p[0]?.dataIndex ?? 0;
        const r = rows[i];
        if (!r) return "";
        return `${r.title}<br/>截止 ${r.due}<br/>按时交 ${r.submitted - r.late} · 迟交 ${r.late} · 未交 ${r.missing}<br/>提交率 ${r.rate}%`;
      },
    },
    legend: {
      top: 0,
      right: 0,
      itemWidth: 8,
      itemHeight: 8,
      textStyle: { fontSize: 11, color: "#5d4b3a" },
      data: ["按时交", "迟交", "未交"],
    },
    xAxis: {
      type: "category",
      data: rows.map((r) => short(r.title)),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#eadfcd" } },
      axisLabel: { fontSize: 10, color: "#8e7a66", interval: 0 },
    },
    yAxis: [
      {
        type: "value",
        name: "人数",
        nameTextStyle: { fontSize: 10, color: "#8e7a66" },
        splitLine: { lineStyle: { color: "#f2e9da" } },
        axisLabel: { fontSize: 11, color: "#8e7a66" },
      },
      { type: "value", show: false, max: 100 },
    ],
    series: [
      {
        name: "按时交",
        type: "bar",
        stack: "a",
        barWidth: "42%",
        itemStyle: { color: "#047857" },
        data: rows.map((r) => r.submitted - r.late),
      },
      {
        name: "迟交",
        type: "bar",
        stack: "a",
        itemStyle: { color: "#e8a33d" },
        data: rows.map((r) => r.late),
      },
      {
        name: "未交",
        type: "bar",
        stack: "a",
        itemStyle: { color: "#dc2626", borderRadius: [4, 4, 0, 0] },
        data: rows.map((r) => r.missing),
      },
      {
        name: "提交率",
        type: "line",
        yAxisIndex: 1,
        smooth: 0.3,
        symbolSize: 5,
        lineStyle: { color: "#b45309", width: 1.6, type: "dashed" },
        itemStyle: { color: "#b45309" },
        data: rows.map((r) => r.rate),
      },
    ],
  };
});

useChart(el, option);
</script>

<template>
  <div ref="el" :style="{ height: `${height}px`, width: '100%' }"></div>
</template>
