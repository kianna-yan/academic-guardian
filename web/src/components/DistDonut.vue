<script setup lang="ts">
import { computed, ref } from "vue";
import { useChart } from "@/composables/echarts";
import type { Level } from "@/types";

const props = defineProps<{ dist: Record<Level, number> }>();

const el = ref<HTMLElement | null>(null);

const total = computed(
  () => (props.dist?.red || 0) + (props.dist?.yellow || 0) + (props.dist?.green || 0),
);
const pct = (n: number) => (total.value ? ((n / total.value) * 100).toFixed(1) : "0.0");

const rows = computed(() => [
  { key: "red", label: "红色预警", color: "#dc2626", value: props.dist?.red || 0 },
  { key: "yellow", label: "黄色关注", color: "#d97706", value: props.dist?.yellow || 0 },
  { key: "green", label: "状态正常", color: "#047857", value: props.dist?.green || 0 },
]);

const option = computed(() => ({
  tooltip: { trigger: "item", formatter: "{b}：{c} 人（{d}%）" },
  series: [
    {
      type: "pie",
      radius: ["60%", "86%"],
      center: ["50%", "50%"],
      startAngle: 90,
      avoidLabelOverlap: false,
      label: { show: false },
      labelLine: { show: false },
      itemStyle: { borderColor: "#fff", borderWidth: 2 },
      data: rows.value.map((r) => ({
        name: r.label,
        value: r.value,
        itemStyle: { color: r.color },
      })),
    },
  ],
}));

useChart(el, option);
</script>

<template>
  <div class="donut">
    <div class="donut-canvas">
      <div ref="el" class="donut-chart"></div>
      <div class="donut-center">
        <b>{{ total }}</b>
        <span>在册学生</span>
      </div>
    </div>
    <div class="donut-legend">
      <div v-for="r in rows" :key="r.key" class="legend-row">
        <i :style="{ background: r.color }"></i>
        {{ r.label }} <b>{{ r.value }}</b> 人
        <span class="muted">（{{ pct(r.value) }}%）</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.donut {
  display: flex;
  align-items: center;
  gap: 18px;
  flex-wrap: wrap;
}
.donut-canvas {
  position: relative;
  width: 160px;
  height: 160px;
  flex: 0 0 auto;
}
.donut-chart {
  position: absolute;
  inset: 0;
}
.donut-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}
.donut-center b {
  font-size: 22px;
  font-weight: 500;
  line-height: 1.1;
}
.donut-center span {
  font-size: 11px;
  color: var(--muted);
}
.donut-legend {
  font-size: 12.5px;
  line-height: 2;
  min-width: 0;
}
.legend-row i {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 2px;
  margin-right: 7px;
}
</style>
