<script setup lang="ts">
import { computed, ref } from "vue";
import { useChart } from "@/composables/echarts";
import type { CourseTrend } from "@/types";

/**
 * 本学期每门课的测评走势：4 次随堂测 + 期中，5 个点一条线。
 * 六门课画在一张图上，是因为学生最想问的是"哪门在掉、哪门在涨"，
 * 分开画就得点四五六次才能比出来。
 */
const props = withDefaults(
  defineProps<{ courses: CourseTrend[]; height?: number; worst?: string }>(),
  { height: 268 },
);

const el = ref<HTMLElement | null>(null);

const PALETTE = ["#b45309", "#d97706", "#a16207", "#7c2d12", "#ea580c", "#65a30d"];

const axisLabels = computed(() => {
  const first = props.courses[0];
  return (first?.points || []).map((p) => p.short);
});

const option = computed(() => {
  const list = props.courses || [];
  if (!list.length) return {};

  const series = list.map((c, i) => {
    const hot = c.code === props.worst;
    return {
      name: c.name,
      type: "line",
      smooth: 0.3,
      symbol: "circle",
      symbolSize: hot ? 7 : 5,
      lineStyle: {
        width: hot ? 3 : 1.8,
        color: PALETTE[i % PALETTE.length],
        opacity: hot ? 1 : 0.75,
      },
      itemStyle: { color: PALETTE[i % PALETTE.length] },
      emphasis: { focus: "series", lineStyle: { width: 3 } },
      data: c.points.map((p) => p.score),
      z: hot ? 5 : 2,
      // 及格线挂在第一条线上，不额外造一条空 series（否则 legend 会多出一项）
      markLine:
        i === 0
          ? {
              silent: true,
              symbol: "none",
              lineStyle: { color: "#f59e0b", type: "dashed", width: 1 },
              label: { formatter: "60", position: "insideEndTop", fontSize: 10, color: "#b45309" },
              data: [{ yAxis: 60 }],
            }
          : undefined,
    };
  });

  return {
    grid: { left: 38, right: 16, top: 44, bottom: 20 },
    legend: {
      top: 0,
      left: 0,
      itemWidth: 10,
      itemHeight: 2,
      itemGap: 10,
      textStyle: { fontSize: 11, color: "#5d4b3a" },
      // 只把课程写进 legend；不写 data 的话 ECharts 会把所有 series 名都列出来
      data: list.map((c) => c.name),
      type: "scroll",
      pageIconSize: 9,
      pageTextStyle: { fontSize: 10 },
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(255,255,255,.97)",
      borderColor: "#eadfcd",
      textStyle: { color: "#111827", fontSize: 12 },
      formatter: (ps: any[]) => {
        const rows = [`<b>${ps?.[0]?.axisValue ?? ""}</b>`];
        // 分高的排前面，一眼看到谁在拖后腿
        [...ps]
          .sort((a, b) => (b.value ?? 0) - (a.value ?? 0))
          .forEach((p) => {
            rows.push(`${p.marker}${p.seriesName} <b>${p.value}</b>`);
          });
        return rows.join("<br/>");
      },
    },
    xAxis: {
      type: "category",
      data: axisLabels.value,
      boundaryGap: false,
      axisLine: { lineStyle: { color: "#eadfcd" } },
      axisTick: { show: false },
      axisLabel: { fontSize: 11.5, color: "#5d4b3a" },
    },
    yAxis: {
      type: "value",
      min: (v: any) => Math.max(0, Math.floor(v.min - 6)),
      max: 100,
      axisLabel: { fontSize: 11, color: "#c2a98d" },
      splitLine: { lineStyle: { color: "#f7f0e5" } },
    },
    series,
  };
});

useChart(el, option);
</script>

<template>
  <div ref="el" :style="{ width: '100%', height: `${height}px` }"></div>
</template>
