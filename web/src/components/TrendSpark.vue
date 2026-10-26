<script setup lang="ts">
import { computed } from "vue";

/**
 * 名单里的迷你走势线。
 *
 * 刻意不用 ECharts：一页 240 行就是 240 个 canvas 实例，滚动会直接卡死。
 * 这里只算一条 polyline，DOM 是纯 SVG，几百行也不掉帧。
 *
 * 纵向缩放有个坑：如果按"本行最大最小值"拉伸，一个只波动 2 分的学生
 * 也会画出剧烈起伏，看上去比真掉 10 分的人还惨。所以给定了最小值域
 * MIN_SPAN —— 波动小于它的曲线就该是平的。
 */
const props = withDefaults(
  defineProps<{
    points: number[];
    width?: number;
    height?: number;
    /** 外部给的方向（后端按最小二乘算），不给就按首尾差自己判 */
    direction?: "up" | "down" | "flat";
  }>(),
  { width: 84, height: 24 },
);

const PAD_X = 3;
const PAD_Y = 3;
const MIN_SPAN = 8;

const dir = computed(() => {
  if (props.direction) return props.direction;
  const p = props.points || [];
  if (p.length < 2) return "flat";
  const d = p[p.length - 1] - p[0];
  return d > 3 ? "up" : d < -3 ? "down" : "flat";
});

const color = computed(
  () => ({ up: "var(--green, #047857)", down: "var(--red, #dc2626)", flat: "#b09b85" })[dir.value],
);

const geom = computed(() => {
  const p = (props.points || []).filter((v) => typeof v === "number" && !Number.isNaN(v));
  if (p.length < 2) return null;

  const lo0 = Math.min(...p);
  const hi0 = Math.max(...p);
  const mid = (lo0 + hi0) / 2;
  const span = Math.max(hi0 - lo0, MIN_SPAN);
  const lo = mid - span / 2;
  const hi = mid + span / 2;

  const w = props.width;
  const h = props.height;
  const step = (w - PAD_X * 2) / (p.length - 1);
  const coords = p.map((v, i) => {
    const x = PAD_X + i * step;
    const y = PAD_Y + (1 - (v - lo) / span) * (h - PAD_Y * 2);
    return [Math.round(x * 10) / 10, Math.round(y * 10) / 10];
  });
  const d = coords.map((c, i) => `${i === 0 ? "M" : "L"}${c[0]},${c[1]}`).join(" ");
  const area = `${d} L${coords[coords.length - 1][0]},${h - 1} L${coords[0][0]},${h - 1} Z`;
  return { coords, d, area, w, h };
});
</script>

<template>
  <svg
    v-if="geom"
    class="spark"
    :width="width"
    :height="height"
    :viewBox="`0 0 ${width} ${height}`"
    role="img"
    aria-label="成绩走势"
  >
    <path v-if="width >= 70" :d="geom.area" :fill="color" opacity="0.12" />
    <path
      :d="geom.d"
      fill="none"
      :stroke="color"
      stroke-width="1.7"
      stroke-linejoin="round"
      stroke-linecap="round"
    />
    <circle
      :cx="geom.coords[geom.coords.length - 1][0]"
      :cy="geom.coords[geom.coords.length - 1][1]"
      r="2.4"
      :fill="color"
    />
  </svg>
  <span v-else class="spark-empty">—</span>
</template>

<style scoped>
.spark {
  display: block;
  overflow: visible;
}
.spark-empty {
  color: var(--muted);
  font-size: 12px;
}
</style>
