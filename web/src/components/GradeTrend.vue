<script setup lang="ts">
import { computed, ref } from "vue";
import { useChart } from "@/composables/echarts";
import type { GradeTrend, TermScore } from "@/types";

/**
 * 学期成绩走势：五个点，前四个是学期总评（实线），本学期只有期中（虚线段）。
 * 之所以要区分线型，是因为"期中 76 分"和"总评 86 分"不是同一把尺子，
 * 直接用一条实线连过去会让所有人看起来都在暴跌。
 */
const props = withDefaults(defineProps<{ trend: GradeTrend; height?: number }>(), {
  height: 236,
});

const el = ref<HTMLElement | null>(null);
type Metric = "avg" | "rank";
const metric = ref<Metric>("avg");

const terms = computed<TermScore[]>(() => props.trend?.terms || []);
const lastIdx = computed(() => terms.value.length - 1);
const isRank = computed(() => metric.value === "rank");

const dirLabel = computed(() => props.trend?.slope?.label || "");
const dirTone = computed(() => {
  const d = props.trend?.slope?.direction;
  return d === "down" ? "bad" : d === "up" ? "good" : "flat";
});

function valueOf(t: TermScore) {
  return isRank.value ? t.rank : t.avg;
}

const option = computed(() => {
  const list = terms.value;
  if (!list.length) return {};

  const mine = list.map((t) => valueOf(t));
  const ref = list.map((t) =>
    isRank.value ? (t.rank_total ? Math.round((t.rank_total + 1) / 2) : null) : t.cohort_avg,
  );

  // 已出总评的部分画实线，本学期那个点单独一段虚线接上去
  const solid = mine.map((v, i) => (i === lastIdx.value ? null : v));
  const tail = mine.map((v, i) => (i >= lastIdx.value - 1 ? v : null));

  const lo = Math.min(...(mine.filter((v) => v != null) as number[]));
  const hi = Math.max(...(mine.filter((v) => v != null) as number[]));
  const pad = Math.max(3, (hi - lo) * 0.3);

  // 分数模式下，及格线落在可视区外就不画（否则一根线贴在顶边，容易误读）；
  // 离及格线不远的把 60 一起框进来，让学生看到自己还有多少空间。
  const showPass = !isRank.value && lo - pad <= 70;

  // 排名模式的纵轴只框住"这个人的活动范围"。如果永远画 1..40，
  // 排在后段的人整条线会贴着底边，看不出起伏 —— 绝对名次上面那句话里已经写清了。
  let yMin: number;
  let yMax: number;
  if (isRank.value) {
    const total = list[0]?.rank_total || 40;
    const gap = Math.max(3, Math.ceil((hi - lo) * 0.6));
    yMin = Math.max(1, Math.floor(lo - gap));
    yMax = Math.min(total, Math.ceil(hi + gap));
    if (yMax - yMin < 8) {
      const grow = Math.ceil((8 - (yMax - yMin)) / 2);
      yMin = Math.max(1, yMin - grow);
      yMax = Math.min(total, yMax + grow);
    }
  } else {
    yMin = Math.max(0, Math.floor(showPass ? Math.min(lo - pad, 58) : lo - pad));
    yMax = Math.min(100, Math.ceil(hi + pad));
  }

  const medianRank = list[0]?.rank_total ? Math.round((list[0].rank_total + 1) / 2) : null;
  const showMedian = isRank.value && medianRank != null && medianRank >= yMin && medianRank <= yMax;

  const legendData = isRank.value
    ? ["班级排名", ...(showMedian ? ["班级中位"] : [])]
    : ["我的均分", "班级均分"];

  return {
    grid: { left: 42, right: isRank.value ? 16 : 30, top: 30, bottom: 28 },
    legend: {
      top: 0,
      right: 0,
      itemWidth: 12,
      itemHeight: 2,
      textStyle: { fontSize: 11, color: "#8e7a66" },
      data: legendData,
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: "#ddcbb3" } },
      backgroundColor: "rgba(255,255,255,.97)",
      borderColor: "#eadfcd",
      textStyle: { color: "#111827", fontSize: 12 },
      formatter: (ps: any[]) => {
        const i = ps?.[0]?.dataIndex ?? 0;
        const t = list[i];
        if (!t) return "";
        const rows = [
          `<b>${t.label}</b> <span style="color:#c2a98d">${t.term}</span>`,
          `均分 <b>${t.avg}</b>　班级 ${t.cohort_avg ?? "-"}`,
          `GPA ${t.gpa ?? "-"}　班级 ${t.cohort_gpa ?? "-"}`,
          `班级排名 <b>${t.rank ?? "-"}</b> / ${t.rank_total ?? "-"}`,
          `学期学分 ${t.credits}${t.failed ? `　挂科 ${t.failed} 学分` : ""}`,
        ];
        if (t.status === "ongoing") {
          rows.push(`<span style="color:#b45309">${t.note}</span>`);
        }
        return rows.join("<br/>");
      },
    },
    xAxis: {
      type: "category",
      data: list.map((t) => t.label),
      boundaryGap: false,
      axisLine: { lineStyle: { color: "#eadfcd" } },
      axisTick: { show: false },
      axisLabel: {
        fontSize: 11.5,
        color: "#5d4b3a",
        // 本学期那一点打个记号，避免被当成"总评掉到 76"
        formatter: (v: string, i: number) => (i === lastIdx.value ? `${v}*` : v),
      },
    },
    yAxis: {
      type: "value",
      min: yMin,
      max: yMax,
      inverse: isRank.value, // 排名越小越好，轴要反过来
      scale: true,
      name: isRank.value ? "名次" : "分数",
      nameTextStyle: { fontSize: 10.5, color: "#c2a98d", align: "right" },
      nameGap: 10,
      axisLabel: { fontSize: 11, color: "#c2a98d" },
      splitLine: { lineStyle: { color: "#f7f0e5" } },
    },
    series: [
      {
        name: isRank.value ? "班级排名" : "我的均分",
        type: "line",
        smooth: 0.35,
        symbol: "circle",
        symbolSize: 7,
        lineStyle: { width: 2.4, color: "#b45309" },
        itemStyle: { color: "#b45309" },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(29,78,216,.16)" },
              { offset: 1, color: "rgba(29,78,216,0)" },
            ],
          },
        },
        data: solid,
        markLine: showPass
          ? {
              silent: true,
              symbol: "none",
              lineStyle: { color: "#f59e0b", type: "dashed", width: 1 },
              label: {
                formatter: "及格线 60",
                position: "insideEndTop",
                fontSize: 10,
                color: "#b45309",
              },
              data: [{ yAxis: 60 }],
            }
          : undefined,
      },
      {
        name: isRank.value ? "班级中位" : "班级均分",
        type: "line",
        smooth: 0.35,
        symbol: "none",
        lineStyle: { width: 1.4, color: "#b09b85", type: "dashed" },
        itemStyle: { color: "#b09b85" },
        data: showMedian || !isRank.value ? ref : [],
      },
      {
        name: "本学期（期中）",
        type: "line",
        smooth: 0.35,
        symbol: "emptyCircle",
        symbolSize: 8,
        lineStyle: { width: 2.4, color: "#b45309", type: "dashed" },
        itemStyle: { color: "#fff", borderColor: "#b45309", borderWidth: 2 },
        data: tail,
        tooltip: { show: false },
        silent: true,
      },
    ],
  };
});

useChart(el, option);
</script>

<template>
  <div class="gt">
    <div class="gt-bar">
      <span class="gt-sum">{{ trend.summary }}</span>
      <div class="gt-switch">
        <button class="gt-tab" :class="{ on: !isRank }" @click="metric = 'avg'">分数</button>
        <button class="gt-tab" :class="{ on: isRank }" @click="metric = 'rank'">班级排名</button>
      </div>
    </div>

    <div ref="el" :style="{ width: '100%', height: `${height}px` }"></div>

    <div class="gt-foot">
      <span class="gt-chip" :class="dirTone">
        {{ dirTone === "bad" ? "↓" : dirTone === "good" ? "↑" : "→" }}
        {{ dirLabel }}
        <template v-if="trend.slope.per_term">
          · 每学期 {{ trend.slope.per_term > 0 ? "+" : "" }}{{ trend.slope.per_term }} 分
        </template>
      </span>
      <span v-if="trend.now.cohort_avg !== null" class="gt-gap">
        本学期与班级均分差
        <b :class="trend.now.gap >= 0 ? 'good' : 'bad'">
          {{ trend.now.gap > 0 ? "+" : "" }}{{ trend.now.gap }}
        </b>
        分
      </span>
      <span class="gt-note">* 大三上仅为期中成绩，与学期总评口径不同，只作参考</span>
    </div>
  </div>
</template>

<style scoped>
.gt {
  min-width: 0;
}
.gt-bar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 2px;
}
.gt-sum {
  font-size: 12.5px;
  color: var(--text-2);
  line-height: 1.6;
  min-width: 0;
}
.gt-switch {
  display: inline-flex;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 2px;
  flex: none;
}
.gt-tab {
  border: 0;
  background: transparent;
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 6px;
  color: var(--text-2);
  cursor: pointer;
}
.gt-tab.on {
  background: var(--brand-soft, #fdf1de);
  color: var(--brand, #b45309);
  font-weight: 500;
}
.gt-foot {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 11.5px;
  color: var(--muted);
  margin-top: 4px;
}
.gt-chip {
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 11.5px;
}
.gt-chip.bad {
  background: var(--red-soft, #fef2f2);
  color: var(--red, #dc2626);
}
.gt-chip.good {
  background: var(--green-soft, #ecfdf5);
  color: var(--green, #047857);
}
.gt-chip.flat {
  background: var(--line);
  color: var(--text-2);
}
.gt-gap b {
  font-variant-numeric: tabular-nums;
}
.gt-gap b.good {
  color: var(--green, #047857);
}
.gt-gap b.bad {
  color: var(--red, #dc2626);
}
.gt-note {
  margin-left: auto;
}
@media (max-width: 640px) {
  .gt-note {
    margin-left: 0;
    width: 100%;
  }
}
</style>
