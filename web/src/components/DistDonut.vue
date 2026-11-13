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
  { key: "red", label: "红色预警", color: "#b3261e", value: props.dist?.red || 0 },
  { key: "yellow", label: "黄色关注", color: "#a9681f", value: props.dist?.yellow || 0 },
  { key: "green", label: "状态正常", color: "#17604f", value: props.dist?.green || 0 },
]);

const option = computed(() => ({
  tooltip: { trigger: "item", formatter: "{b}：{c} 人（{d}%）" },
  series: [
    {
      type: "pie",
      radius: ["66%", "88%"],
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
  /* 整组（环 + 图例）居中：以前靠左贴边，160 的环配 12.5px 图例，右边和下面
     各留一大块空白，卡片看着是「半张空的」。现在环放大到 226，整组往中间挪。 */
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 24px;
  flex-wrap: wrap;
  /* 与右栏「最普遍的风险因素」六条等高，两张卡底边齐平、中间不留空带。
     环从 260 收到 216 是等比缩：半径、图例字号、留白一起退 17%，
     不是只把圈改小而字号不动。 */
  min-height: 232px;
}
.donut-canvas {
  position: relative;
  width: 216px;
  height: 216px;
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
  font-size: 32px;
  font-weight: 500;
  line-height: 1.05;
  font-variant-numeric: tabular-nums;
}
.donut-center span {
  margin-top: 2px;
  font-size: 12px;
  color: var(--muted);
}
.donut-legend {
  font-size: 13px;
  line-height: 2.1;
  min-width: 0;
}
.donut-legend .legend-row {
  white-space: nowrap;
}
.legend-row i {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 2px;
  margin-right: 7px;
  vertical-align: 1px;
}
.legend-row b {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.legend-row .muted {
  color: var(--muted);
}

/* 两栏在窄屏会堆成一列：环没必要还占 226，跟着收小，别把页面拉得很长 */
@media (max-width: 900px) {
  .donut {
    min-height: 0;
    gap: 18px;
  }
  .donut-canvas {
    width: 180px;
    height: 180px;
  }
  .donut-center b {
    font-size: 28px;
  }
  .donut-legend {
    font-size: 12.5px;
    line-height: 2;
  }
}
</style>
