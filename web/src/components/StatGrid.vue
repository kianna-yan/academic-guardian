<script setup lang="ts">
import { computed } from "vue";

export interface StatItem {
  value: string | number;
  label: string;
  tone?: "red" | "amber" | "";
}

// cols 默认 4，与全局 .stats 一致（学生 / 辅导员 / 教务 / 家长四端都是 4 项）。
// 教师端有 6 项指标，传 6 时切成自适应列：窄屏自动折行，宽屏一行排开，
// 不会像固定 4 列那样排出「4 + 2」把右侧空掉半行。
const props = withDefaults(defineProps<{ items: StatItem[]; cols?: number }>(), {
  cols: 4,
});

const style = computed(() => {
  if (props.cols === 4) return {};
  const min = props.cols >= 6 ? 150 : 180;
  return { gridTemplateColumns: `repeat(auto-fit, minmax(${min}px, 1fr))` };
});
</script>

<template>
  <div class="stats" :style="style">
    <div v-for="s in items" :key="s.label" class="stat" :class="s.tone">
      <b>{{ s.value }}</b>
      <span>{{ s.label }}</span>
    </div>
  </div>
</template>
