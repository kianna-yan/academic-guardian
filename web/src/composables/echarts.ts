import * as echarts from "echarts/core";
import { BarChart, LineChart, PieChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { onBeforeUnmount, onMounted, ref, watch, type Ref } from "vue";

echarts.use([
  PieChart,
  BarChart,
  LineChart,
  TooltipComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  CanvasRenderer,
]);

/**
 * 轻量 ECharts 封装：按需注册图表类型，自动跟随容器尺寸变化。
 * 容器可能因为 v-if / 骨架屏而晚于组件挂载才拿到尺寸，所以 ResizeObserver 里补一次 init。
 */
export function useChart(target: Ref<HTMLElement | null>, option: Ref<any>) {
  let inst: echarts.ECharts | null = null;
  let ro: ResizeObserver | null = null;

  function render() {
    if (!target.value) return;
    if (!inst) inst = echarts.init(target.value, undefined, { renderer: "canvas" });
    inst.setOption(option.value, true);
  }

  onMounted(() => {
    render();
    if (target.value) {
      ro = new ResizeObserver(() => {
        if (!inst) render();
        else inst.resize();
      });
      ro.observe(target.value);
    }
  });

  watch(option, render, { deep: true });

  onBeforeUnmount(() => {
    ro?.disconnect();
    ro = null;
    inst?.dispose();
    inst = null;
  });

  return { render };
}
