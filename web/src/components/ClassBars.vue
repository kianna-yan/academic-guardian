<script setup lang="ts">
import { computed, ref } from "vue";
import { useChart } from "@/composables/echarts";

/**
 * 分班对比（教师端特有）。
 * 同一门课、同一套试卷、同一个进度，班与班的差距才是老师能改的东西：
 * 差 5 分可能是生源，差 0.3 分说明讲法本身没问题。
 */
const props = withDefaults(
  defineProps<{
    classes: { class_name: string; students: number; mid_avg: number; gap: number; hw_rate: number }[];
    courseAvg?: number;
    height?: number;
  }>(),
  { courseAvg: 0, height: 208 },
);

const el = ref<HTMLElement | null>(null);

const option = computed(() => {
  // 按均分升序，横向条形从上往下是从低到高，一眼看出谁垫底
  const rows = [...(props.classes || [])].sort((a, b) => a.mid_avg - b.mid_avg);
  return {
    grid: { left: 8, right: 46, top: 22, bottom: 4, containLabel: true },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (p: any[]) => {
        const r = rows[p[0]?.dataIndex ?? 0];
        if (!r) return "";
        return `${r.class_name}（${r.students} 人）<br/>期中均分 ${r.mid_avg}<br/>与本课均分 ${r.gap > 0 ? "+" : ""}${r.gap}<br/>作业提交率 ${r.hw_rate}%`;
      },
    },
    xAxis: { type: "value", show: false, min: (v: any) => Math.max(0, v.min - 6) },
    yAxis: {
      type: "category",
      data: rows.map((r) => r.class_name),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { fontSize: 11, color: "#5d4b3a" },
    },
    series: [
      {
        type: "bar",
        barWidth: 13,
        data: rows.map((r) => ({
          value: r.mid_avg,
          itemStyle: {
            borderRadius: 5,
            // 低于本课均分的班用暖红，高于的用绿——老师只需要一眼看到落后的
            color: r.mid_avg < props.courseAvg ? "#d97706" : "#047857",
            opacity: r.mid_avg < props.courseAvg ? 0.9 : 0.75,
          },
        })),
        label: {
          show: true,
          position: "right",
          fontSize: 11,
          color: "#5d4b3a",
          formatter: (d: any) => String(d.value),
        },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: "#b45309", type: "dashed", width: 1 },
          label: { formatter: `本课 ${props.courseAvg}`, fontSize: 10, color: "#b45309", position: "end" },
          data: [{ xAxis: props.courseAvg }],
        },
      },
    ],
  };
});

useChart(el, option);
</script>

<template>
  <div ref="el" :style="{ height: `${height}px`, width: '100%' }"></div>
</template>
