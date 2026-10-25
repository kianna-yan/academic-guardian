import { onBeforeUnmount, onMounted, ref } from "vue";

/** 窄屏判断：用于按屏宽裁剪表格列等结构性调整（CSS 改不了列） */
export function useNarrow(breakpoint = 760) {
  const narrow = ref(typeof window !== "undefined" ? window.innerWidth <= breakpoint : false);
  const update = () => {
    narrow.value = window.innerWidth <= breakpoint;
  };
  onMounted(() => window.addEventListener("resize", update));
  onBeforeUnmount(() => window.removeEventListener("resize", update));
  return narrow;
}
