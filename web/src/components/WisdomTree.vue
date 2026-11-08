<script setup lang="ts">
import { computed, ref } from "vue";
import type { TreeFruit } from "@/types";

/**
 * 智慧树：一棵树上看完一个学期的几门课。
 *
 * 不用图表语言（没有坐标轴、没有网格），它是一张"树"，但信息一项不少：
 * - 一颗果实 = 一门课，就是一颗苹果；
 * - **苹果颜色 = 学期作业完成度**：青（还没过半）→ 黄（过半）→ 红（全部交齐）；
 *   完成度按"施到树上的进度 ÷ 该课作业总次数"算——施到一半以上变黄，施满变红；
 *   补交挣的袋子也算数，没过半的课施完也还是青的，不骗人；
 * - **果实大小 = 学分 × 成熟度**：学分定"这门课该占多大份量"，施肥进度定"实际长到几成"；
 *   每施一袋果子当场大一圈（补交的袋子再饱满一小圈）；
 * - **树的形态 = 水（到课）**：不是整体放大——树苗先长干，再开冠，树干粗细、树高、
 *   树冠大小各按自己的曲线长；果实挂在树冠里、跟着树冠一起缩放，
 *   任何阶段苹果与树的比例都正确，不会出现苹果比树还大；
 * - 果柄上的叶片数 = 学分；
 * - 临界/风险的课挂一圈淡淡的光环，其余苹果保持干净。
 *
 * 生长是**互动**的：仓库里的水肥袋一袋袋施下去，每施一袋树当场长一点——
 * 不是进页面自动播完，是人亲手养出来的。
 */
const props = withDefaults(
  defineProps<{
    fruits: TreeFruit[];
    selected?: string | null;
    /** 全学期到课率 0–1：低于 0.92 时整棵树显出缺水 */
    waterRate?: number;
    /** 有效到课节数（迟到按 0.5 折算的累计量）——决定树能长到多高多粗 */
    waterCount?: number;
    /** 已浇水比例 0–1：0 是树苗，1 长到本学期该有的个头 */
    waterFrac?: number;
    /** 各课已施肥比例 0–1：0 是青果，1 长到该课成熟度 */
    fertFrac?: Record<string, number>;
    /** 各课额外施肥袋数（补交作业挣的）：每袋让果子再饱满一小圈 */
    fertBonus?: Record<string, number>;
    /** 各课"学期作业完成度"0–1（已施袋数 ÷ 作业总次数）：决定苹果颜色 青→黄→红 */
    ripe?: Record<string, number>;
  }>(),
  {
    selected: null,
    waterRate: 1,
    waterCount: 60,
    waterFrac: 0,
    fertFrac: () => ({}),
    fertBonus: () => ({}),
    ripe: () => ({}),
  },
);

const emit = defineEmits<{ (e: "select", code: string): void }>();

const STATUS: Record<TreeFruit["status"], { color: string; label: string }> = {
  great: { color: "#2f8f6b", label: "很稳" },
  ok: { color: "#46a06a", label: "较稳" },
  watch: { color: "#e88a1e", label: "临界" },
  risk: { color: "#d9483b", label: "有挂科风险" },
};

/* ---------------------------------------------------------------- */
/* 苹果的三段人生：青（未过半）→ 黄（过半）→ 红（全交）              */
/* ---------------------------------------------------------------- */

function hexToRgb(hex: string): [number, number, number] {
  const v = hex.replace("#", "");
  return [parseInt(v.slice(0, 2), 16), parseInt(v.slice(2, 4), 16), parseInt(v.slice(4, 6), 16)];
}
function mixHex(a: string, b: string, t: number): string {
  const [r1, g1, b1] = hexToRgb(a);
  const [r2, g2, b2] = hexToRgb(b);
  const f = (x: number, y: number) => Math.round(x + (y - x) * t);
  return `#${[f(r1, r2), f(g1, g2), f(b1, b2)].map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}
function smoothstep(e0: number, e1: number, x: number): number {
  const t = Math.max(0, Math.min(1, (x - e0) / (e1 - e0)));
  return t * t * (3 - 2 * t);
}

/** 青苹果 / 黄苹果 / 红苹果 的三色梯（亮 / 主 / 深） */
const APPLE_G = { l: "#b9e29c", m: "#7fc062", d: "#55a049" };
const APPLE_Y = { l: "#f7dc82", m: "#f0c23e", d: "#d9a21e" };
const APPLE_R = { l: "#f2907c", m: "#e2503f", d: "#bf3527" };

/** 按完成度混色：0.45–0.55 青→黄，0.93–1 黄→红，过渡带窄所以"变成"看得见 */
function applePalette(p: number) {
  const t1 = smoothstep(0.45, 0.55, p);
  const t2 = smoothstep(0.93, 1.0, p);
  return {
    light: mixHex(mixHex(APPLE_G.l, APPLE_Y.l, t1), APPLE_R.l, t2),
    mid: mixHex(mixHex(APPLE_G.m, APPLE_Y.m, t1), APPLE_R.m, t2),
    deep: mixHex(mixHex(APPLE_G.d, APPLE_Y.d, t1), APPLE_R.d, t2),
    stage: p >= 1 ? 2 : p >= 0.5 ? 1 : 0,
  };
}

/** 果实的挂点：沿树冠外沿排开，错开两层给标签留出落脚的空隙 */
const SLOTS = [
  { x: 288, y: 248 },
  { x: 474, y: 240 },
  { x: 206, y: 330 },
  { x: 552, y: 320 },
  { x: 382, y: 288 },
  { x: 300, y: 372 },
  { x: 462, y: 366 },
  { x: 382, y: 208 },
];

/* ---------------------------------------------------------------- */
/* 天空的星点：四角星 + 小圆点，此起彼伏地闪，补住树上方的空          */
/* ---------------------------------------------------------------- */

/**
 * 位置写死在 viewBox（78 76 620 528）坐标里：主要撒在树冠以上的天空
 * 和左右页边，树冠区只留零星几颗。周期取 3/5/6 秒（互为约数），相位用
 * 负延迟错开，才是此起彼伏地闪，而不是一片一起亮、一起灭。
 */
const SKY_SPARKS: Array<{
  x: number; y: number; s: number;
  c: string; dur: number; dl: number; op: number;
}> = [
  // —— 树冠以上的天空带 ——
  { x: 152, y: 118, s: 12, c: "#c88a6d", dur: 6, dl: -1.6, op: 0.8 },
  { x: 268, y: 96, s: 8, c: "#16564a", dur: 5, dl: -3.2, op: 0.55 },
  { x: 392, y: 84, s: 6.5, c: "#d9a21e", dur: 3, dl: -1.1, op: 0.5 },
  { x: 520, y: 108, s: 10, c: "#c88a6d", dur: 6, dl: -4.4, op: 0.72 },
  { x: 636, y: 132, s: 7, c: "#16564a", dur: 5, dl: -2.2, op: 0.52 },
  { x: 300, y: 130, s: 5, c: "#c88a6d", dur: 3, dl: -2.4, op: 0.42 },
  { x: 468, y: 158, s: 6.5, c: "#16564a", dur: 6, dl: -4.9, op: 0.48 },
  { x: 232, y: 182, s: 6, c: "#d9a21e", dur: 6, dl: -0.4, op: 0.46 },
  { x: 604, y: 172, s: 5.5, c: "#c88a6d", dur: 3, dl: -3.6, op: 0.44 },
  // —— 正中上方那片（树冠顶与天顶之间），与两侧同密度 ——
  { x: 356, y: 196, s: 6.5, c: "#c88a6d", dur: 5, dl: -2.7, op: 0.46 },
  { x: 430, y: 172, s: 8, c: "#16564a", dur: 6, dl: -1.3, op: 0.52 },
  { x: 500, y: 208, s: 6, c: "#d9a21e", dur: 3, dl: -3.9, op: 0.44 },
  { x: 330, y: 240, s: 5.5, c: "#c88a6d", dur: 6, dl: -0.7, op: 0.4 },
  { x: 396, y: 236, s: 7, c: "#16564a", dur: 5, dl: -4.1, op: 0.48 },
  { x: 466, y: 262, s: 5.5, c: "#d9a21e", dur: 3, dl: -2.1, op: 0.42 },
  { x: 528, y: 170, s: 6, c: "#c88a6d", dur: 6, dl: -5.5, op: 0.46 },
  { x: 372, y: 138, s: 5, c: "#16564a", dur: 5, dl: -1.8, op: 0.38 },
  // —— 左右页边，沿树冠外侧垂下来 ——
  { x: 108, y: 208, s: 6, c: "#d9a21e", dur: 3, dl: -0.8, op: 0.48 },
  { x: 672, y: 226, s: 9, c: "#c88a6d", dur: 6, dl: -5.1, op: 0.68 },
  { x: 196, y: 252, s: 5, c: "#16564a", dur: 5, dl: -3.8, op: 0.4 },
  { x: 588, y: 268, s: 6, c: "#d9a21e", dur: 3, dl: -1.5, op: 0.46 },
  { x: 120, y: 330, s: 7.5, c: "#c88a6d", dur: 6, dl: -2.8, op: 0.56 },
  { x: 660, y: 352, s: 5.5, c: "#16564a", dur: 5, dl: -0.6, op: 0.42 },
  { x: 86, y: 286, s: 5, c: "#d9a21e", dur: 5, dl: -1.9, op: 0.38 },
];

/** 小圆点：比星更小更淡，垫在星星之间的空隙里 */
const SKY_DOTS: Array<{
  x: number; y: number; r: number;
  c: string; dur: number; dl: number; op: number;
}> = [
  { x: 210, y: 112, r: 2.2, c: "#16564a", dur: 5, dl: -1.2, op: 0.34 },
  { x: 340, y: 150, r: 1.8, c: "#c88a6d", dur: 3, dl: -2.6, op: 0.3 },
  { x: 448, y: 92, r: 2.4, c: "#16564a", dur: 6, dl: -0.9, op: 0.32 },
  { x: 566, y: 148, r: 1.7, c: "#d9a21e", dur: 5, dl: -3.1, op: 0.34 },
  { x: 140, y: 168, r: 2, c: "#c88a6d", dur: 3, dl: -1.8, op: 0.3 },
  { x: 640, y: 196, r: 2.3, c: "#16564a", dur: 6, dl: -4.2, op: 0.3 },
  { x: 96, y: 382, r: 1.9, c: "#16564a", dur: 5, dl: -2.3, op: 0.26 },
  { x: 684, y: 300, r: 2.1, c: "#c88a6d", dur: 3, dl: -0.5, op: 0.28 },
  { x: 262, y: 320, r: 1.6, c: "#d9a21e", dur: 6, dl: -3.4, op: 0.26 },
  { x: 522, y: 340, r: 1.8, c: "#16564a", dur: 5, dl: -1.4, op: 0.24 },
  { x: 404, y: 116, r: 2, c: "#c88a6d", dur: 3, dl: -2.0, op: 0.3 },
  { x: 178, y: 420, r: 1.7, c: "#c88a6d", dur: 6, dl: -4.6, op: 0.22 },
  // —— 正中上方：与四角星交错，别让星点只长在边圈 ——
  { x: 340, y: 172, r: 1.9, c: "#d9a21e", dur: 5, dl: -2.2, op: 0.3 },
  { x: 408, y: 196, r: 2.1, c: "#16564a", dur: 3, dl: -1.1, op: 0.28 },
  { x: 474, y: 148, r: 1.7, c: "#c88a6d", dur: 6, dl: -3.3, op: 0.3 },
  { x: 512, y: 240, r: 2, c: "#16564a", dur: 5, dl: -0.9, op: 0.26 },
  { x: 350, y: 216, r: 1.6, c: "#c88a6d", dur: 3, dl: -2.8, op: 0.26 },
  { x: 440, y: 120, r: 1.8, c: "#d9a21e", dur: 6, dl: -4.4, op: 0.28 },
  { x: 560, y: 214, r: 1.7, c: "#c88a6d", dur: 5, dl: -1.6, op: 0.24 },
];

/** 四角星的定位变换：把 100×100 的星形缩放到 s 并居中放在 (x, y) */
function sparkTransform(x: number, y: number, s: number): string {
  const k = s / 100;
  return `translate(${x - 50 * k} ${y - 50 * k}) scale(${k})`;
}

/** 按视觉宽度截断课程名：中文按 2 个宽度算，英文按 1 个算 */
function truncate(name: string, maxWidth: number): string {
  let w = 0;
  let out = "";
  for (const ch of name) {
    w += /[一-龥]/.test(ch) ? 2 : 1;
    if (w > maxWidth) return `${out}…`;
    out += ch;
  }
  return out;
}

/* ---------------------------------------------------------------- */
/* 生长：树由"水"长个子，果实由"肥"长大——进度由外部施入比例驱动   */
/* ---------------------------------------------------------------- */

/**
 * 生长阶段 0–1：按"有效到课节数"线性长到本学期已上的课满量（约 85 节 = 6 门 × 14 节）。
 * 不用指数饱和曲线：那样 60% 到课和 100% 到课的树几乎一样粗，
 * 而"水浇得足不足"恰恰是这棵树必须一眼看得出来的事。
 */
const growth = computed(() => Math.min(1, Math.max(0, props.waterCount ?? 60) / 85));

/** 施水进度 0–1：树苗 → 大树 */
const g = computed(() => growth.value * Math.min(1, Math.max(0, props.waterFrac)));

/**
 * 树的三段生长各走各的曲线——不是整体等比放大：
 * 干先粗起来（0.8 次幂，前几壶水回报最明显），树高稳步长，树冠后半程追上来。
 */
const trunkW = computed(() => 0.33 + 0.67 * Math.pow(g.value, 0.8));
const trunkH = computed(() => 0.5 + 0.5 * g.value);
const crownS = computed(() => 0.42 + 0.58 * Math.pow(g.value, 1.05));
/** 额外叶簇的显影程度：水越足，树冠越茂 */
const leafFull = computed(() => 0.25 + 0.75 * g.value);
/** 幼苗的两片初生叶：树长开了就退场 */
const sproutLeaf = computed(() => Math.max(0, 1 - g.value * 1.7));
/** 缺水：到课率掉到 92% 以下，叶子发灰、叶尖下垂 */
const dry = computed(() => (props.waterRate ?? 1) < 0.92);

/** 果实基准尺寸：学分决定这门课该有多大 */
function baseOf(f: TreeFruit): number {
  return 14 + 2.2 * (f.credit || 2);
}

/** 这颗果子吃到几成肥：作业课看施肥进度，无作业课跟着水长 */
function fracOf(f: TreeFruit): number {
  const k = Math.max(0, Math.min(1, props.waterFrac));
  if (!f.hw) return k;
  return Math.max(0, Math.min(1, props.fertFrac?.[f.code] ?? 0));
}

/** 学期作业完成度（决定颜色）：已施袋数 ÷ 作业总次数 */
function ripeOf(f: TreeFruit): number {
  return Math.max(0, Math.min(1, props.ripe?.[f.code] ?? 0));
}

/** 果实下标：把分母写出来，不然作业 3 次的课和 8 次的课没法比 */
function hwLine(f: TreeFruit): string {
  if (!f.hw) return `${f.score} 分 · 按到课计`;
  return `${f.score} 分 · 作业 ${f.hw.done}/${f.hw.due}`;
}

/** 果柄上的叶片：几片叶 = 几个学分，一眼看出这门课有多重 */
function stemLeaves(credit: number, r: number) {
  const n = Math.max(1, Math.min(5, Math.round(credit)));
  const out: { x: number; y: number; rot: number; s: number }[] = [];
  for (let i = 0; i < n; i++) {
    const side = i % 2 ? 1 : -1;
    out.push({
      x: 4 + i * 1.1 * side,
      y: -r - 3 - i * 3.6,
      rot: side * (26 - i * 4),
      s: 1 - i * 0.13,
    });
  }
  return out;
}

const items = computed(() => {
  const list = props.fruits.slice(0, SLOTS.length);
  return list.map((f, i) => {
    const slot = SLOTS[f.slot ?? i] ?? SLOTS[i % SLOTS.length];
    const base = baseOf(f);
    // 青果 28% 起步，按施肥进度长到成熟度；补交挣的额外肥每袋再饱满一小圈
    const frac = fracOf(f);
    const bonus = Math.min(3, Math.max(0, props.fertBonus?.[f.code] ?? 0));
    const r = Math.round(base * (0.28 + (f.maturity - 0.28) * frac) * (1 + 0.04 * bonus) * 10) / 10;
    const pal = applePalette(ripeOf(f));
    // 标签跟着树长大才显影：树苗上挤六行小字只会糊成一团；选中的那颗始终亮着
    const lo =
      props.selected === f.code ? 1 : Math.max(0, Math.min(1, (crownS.value - 0.5) / 0.22));
    return {
      ...f,
      x: slot.x,
      y: slot.y,
      r,
      base,
      lo,
      color: pal.mid,
      light: pal.light,
      deep: pal.deep,
      stage: pal.stage,
      ring: STATUS[f.status].color,
      statusLabel: STATUS[f.status].label,
      showHalo: f.status === "watch" || f.status === "risk",
      delay: `${(i * 0.7).toFixed(1)}s`,
      label: truncate(f.name, 18),
      sub: hwLine(f),
      leaves: stemLeaves(f.credit || 2, r),
    };
  });
});

const particles = [
  { x: 214, y: 300, d: 0 },
  { x: 300, y: 150, d: 1.6 },
  { x: 470, y: 128, d: 3.1 },
  { x: 566, y: 246, d: 0.8 },
  { x: 158, y: 378, d: 2.3 },
  { x: 612, y: 352, d: 4.2 },
  { x: 402, y: 106, d: 2.8 },
];

/** 水够了才长出来的新叶簇：让"树长开了"不只是变大一圈 */
const EXTRA_LEAVES = [
  { x: 236, y: 190, r: 18 }, { x: 526, y: 196, r: 17 }, { x: 342, y: 142, r: 16 },
  { x: 424, y: 138, r: 16 }, { x: 252, y: 330, r: 16 }, { x: 508, y: 322, r: 16 },
];

/* ---------------------------------------------------------------- */
/* 施肥/浇水的落地特效 + 给仓库飞行动画提供坐标                      */
/* ---------------------------------------------------------------- */

const svgEl = ref<SVGSVGElement | null>(null);

/** SVG 里的点 → 屏幕坐标（飞行动画的落点） */
function clientOf(svgX: number, svgY: number): { x: number; y: number } {
  const svg = svgEl.value;
  if (!svg) return { x: 0, y: 0 };
  const pt = svg.createSVGPoint();
  pt.x = svgX;
  pt.y = svgY;
  const m = svg.getScreenCTM();
  if (!m) return { x: 0, y: 0 };
  const p = pt.matrixTransform(m);
  return { x: p.x, y: p.y };
}

/** 果实挂在树冠组里，整组缩放过——落点要按 crownS 换算 */
function getFruitPos(code: string): { x: number; y: number } | null {
  const it = items.value.find((i) => i.code === code);
  if (!it) return null;
  const s = crownS.value;
  return clientOf(380 + (it.x - 380) * s, 556 + (it.y - 556) * s);
}
function getTrunkPos(): { x: number; y: number } {
  return clientOf(380, 552);
}

/** 浇水落地：涟漪 + 水花四溅 */
const splashKey = ref(0);
function splashWater() {
  splashKey.value++;
}

/** 施肥落地：果子上炸开一圈光晕 */
const popKeys = ref<Record<string, number>>({});
function popFruit(code: string) {
  popKeys.value = { ...popKeys.value, [code]: (popKeys.value[code] || 0) + 1 };
}

defineExpose({ getFruitPos, getTrunkPos, splashWater, popFruit });
</script>

<template>
  <svg
    ref="svgEl"
    class="wt"
    :class="{ dry }"
    viewBox="78 76 620 528"
    role="img"
    aria-label="智慧树：每颗苹果是一门课，颜色＝作业完成度（青→黄→红），大小＝学分×施肥成熟度，树形＝到课"
  >
    <defs>
      <radialGradient id="wt-sky" cx="46%" cy="8%" r="92%">
        <stop offset="0" stop-color="#fffdf7" />
        <stop offset="52%" stop-color="#faf2e3" />
        <stop offset="100%" stop-color="#eee1c8" />
      </radialGradient>
      <radialGradient id="wt-sun" cx="50%" cy="50%" r="50%">
        <stop offset="0" stop-color="#ffe4b0" stop-opacity=".7" />
        <stop offset="58%" stop-color="#ffe9c4" stop-opacity=".24" />
        <stop offset="100%" stop-color="#ffe9c4" stop-opacity="0" />
      </radialGradient>
      <linearGradient id="wt-ground" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#ece0c8" />
        <stop offset="100%" stop-color="#d9c5a1" />
      </linearGradient>
      <linearGradient id="wt-trunk" x1="0" y1="0" x2="1" y2="0.15">
        <stop offset="0" stop-color="#7a4c28" />
        <stop offset="26%" stop-color="#a87345" />
        <stop offset="62%" stop-color="#8f5c35" />
        <stop offset="100%" stop-color="#6b4022" />
      </linearGradient>
      <!-- 树冠三层：底深、中亮、顶高光，统一墨绿偏灰的调子，贴住页面的墨绿品牌色 -->
      <radialGradient id="wt-c1" gradientUnits="userSpaceOnUse" cx="330" cy="180" r="360">
        <stop offset="0" stop-color="#6d9a6c" />
        <stop offset="55%" stop-color="#588459" />
        <stop offset="100%" stop-color="#436b48" />
      </radialGradient>
      <radialGradient id="wt-c2" gradientUnits="userSpaceOnUse" cx="316" cy="162" r="330">
        <stop offset="0" stop-color="#8fba87" />
        <stop offset="55%" stop-color="#74a272" />
        <stop offset="100%" stop-color="#5c8a5c" />
      </radialGradient>
      <radialGradient id="wt-c3" gradientUnits="userSpaceOnUse" cx="306" cy="150" r="250">
        <stop offset="0" stop-color="#b3d6a4" />
        <stop offset="62%" stop-color="#99c28e" />
        <stop offset="100%" stop-color="#82ae7b" />
      </radialGradient>
      <radialGradient id="wt-halo-watch" cx="50%" cy="50%" r="50%">
        <stop offset="0" stop-color="#e0a02c" stop-opacity=".45" />
        <stop offset="72%" stop-color="#e0a02c" stop-opacity=".24" />
        <stop offset="100%" stop-color="#e0a02c" stop-opacity="0" />
      </radialGradient>
      <radialGradient id="wt-halo-risk" cx="50%" cy="50%" r="50%">
        <stop offset="0" stop-color="#d9483b" stop-opacity=".5" />
        <stop offset="72%" stop-color="#d9483b" stop-opacity=".28" />
        <stop offset="100%" stop-color="#d9483b" stop-opacity="0" />
      </radialGradient>
      <radialGradient id="wt-shade" cx="50%" cy="50%" r="50%">
        <stop offset="0" stop-color="#31503a" stop-opacity=".28" />
        <stop offset="100%" stop-color="#31503a" stop-opacity="0" />
      </radialGradient>
      <radialGradient id="wt-shadow" cx="50%" cy="50%" r="50%">
        <stop offset="0" stop-color="#bfa87f" stop-opacity=".5" />
        <stop offset="100%" stop-color="#bfa87f" stop-opacity="0" />
      </radialGradient>

      <radialGradient v-for="f in items" :id="`wt-f-${f.code}`" :key="f.code" cx="32%" cy="24%" r="80%">
        <stop offset="0" :stop-color="f.light" />
        <stop offset="54%" :stop-color="f.color" />
        <stop offset="100%" :stop-color="f.deep" />
      </radialGradient>

      <clipPath id="wt-trunk-clip">
        <path d="M354 558 C352 508 356 458 364 412 C366 402 371 397 380 397 C389 397 394 402 396 412 C404 458 408 508 406 558 Z" />
      </clipPath>

      <!-- 天空星点用的四角星（与登录页同一星形） -->
      <path id="wt-spark-shape" d="M50 2C54 30 70 46 98 50 70 54 54 70 50 98 46 70 30 54 2 50 30 46 46 30 50 2Z" />
    </defs>

    <!-- 天光 -->
    <rect x="0" y="0" width="760" height="620" fill="url(#wt-sky)" />
    <circle cx="566" cy="132" r="150" fill="url(#wt-sun)" />

    <!-- 天空星点：四角星与小圆点此起彼伏地闪，补住树上方的空 -->
    <g class="sparks" aria-hidden="true">
      <g
        v-for="(s, i) in SKY_SPARKS"
        :key="`spark-${i}`"
        class="wt-spark"
        :style="{ '--dur': `${s.dur}s`, '--dl': `${s.dl}s`, '--op': s.op }"
      >
        <use href="#wt-spark-shape" :transform="sparkTransform(s.x, s.y, s.s)" :fill="s.c" />
      </g>
      <circle
        v-for="(d, i) in SKY_DOTS"
        :key="`sdot-${i}`"
        class="wt-spark"
        :cx="d.x"
        :cy="d.y"
        :r="d.r"
        :fill="d.c"
        :style="{ '--dur': `${d.dur}s`, '--dl': `${d.dl}s`, '--op': d.op }"
      />
    </g>

    <!-- 地面 -->
    <path d="M0 548 C 120 530 250 544 380 540 C 510 536 640 528 760 542 L760 620 L0 620 Z" fill="url(#wt-ground)" />
    <path d="M0 560 C 140 544 260 556 380 552 C 500 548 630 542 760 554" fill="none" stroke="#c4ad86" stroke-width="1.5" opacity=".65" />
    <ellipse cx="380" cy="556" rx="216" ry="22" fill="url(#wt-shadow)" />

    <!-- 草地细节 -->
    <g stroke="#9db878" stroke-width="1.6" stroke-linecap="round" fill="none" opacity=".8">
      <path d="M128 572 q 4 -13 8 -2" /><path d="M138 575 q 5 -16 11 -3" />
      <path d="M222 584 q 4 -12 8 -1" /><path d="M540 578 q 4 -13 9 -2" />
      <path d="M604 586 q 5 -13 10 -2" /><path d="M330 594 q 4 -13 8 -2" />
      <path d="M666 564 q 4 -12 9 -2" /><path d="M82 560 q 4 -11 8 -1" />
      <path d="M462 600 q 4 -12 8 -2" /><path d="M248 560 q 5 -14 10 -2" />
    </g>
    <g opacity=".9">
      <circle cx="176" cy="586" r="2.6" fill="#e9b7a0" /><circle cx="176" cy="586" r="1" fill="#d99a63" />
      <circle cx="470" cy="598" r="2.4" fill="#e4c079" /><circle cx="470" cy="598" r=".9" fill="#b98f45" />
      <circle cx="640" cy="600" r="2.2" fill="#dba8ab" /><circle cx="292" cy="606" r="2.2" fill="#dfc394" />
      <ellipse cx="600" cy="586" rx="9" ry="4" fill="#cfbf9f" opacity=".8" />
      <ellipse cx="186" cy="600" rx="7" ry="3.4" fill="#cfbf9f" opacity=".7" />
    </g>

    <!-- 树干：高矮和粗细各按自己的曲线长，围着根点 (380, 556) 生长 -->
    <g class="trunk-g" :style="{ transform: `scale(${trunkW.toFixed(4)}, ${trunkH.toFixed(4)})` }">
      <!-- 根 -->
      <g stroke="#7a4c28" stroke-width="6" stroke-linecap="round" fill="none" opacity=".85">
        <path d="M360 552 C 346 560 332 568 314 574" />
        <path d="M402 552 C 416 560 432 566 450 572" />
      </g>
      <g stroke="#9a6a3e" stroke-width="2.6" stroke-linecap="round" fill="none" opacity=".7">
        <path d="M332 568 C 322 574 316 578 308 582" />
        <path d="M434 566 C 444 572 450 576 458 580" />
      </g>

      <!-- 干身：微微收腰的锥形，根部张开 -->
      <path d="M354 558 C352 508 356 458 364 412 C366 402 371 397 380 397 C389 397 394 402 396 412 C404 458 408 508 406 558 Z"
        fill="url(#wt-trunk)" />
      <g clip-path="url(#wt-trunk-clip)" stroke="#5f381c" stroke-width="1.7" fill="none" opacity=".3" stroke-linecap="round">
        <path d="M366 552 C 362 508 366 462 372 424" />
        <path d="M382 550 C 380 506 382 462 386 422" />
        <path d="M396 548 C 396 508 394 466 392 428" />
        <path d="M358 528 C 362 502 360 478 366 454" />
        <path d="M352 556 C 360 551 370 548 378 548" />
        <path d="M392 556 C 400 551 404 549 408 549" />
      </g>
      <path d="M354 558 C352 508 356 458 364 412 C366 402 371 397 380 397 C389 397 394 402 396 412 C404 458 408 508 406 558"
        fill="none" stroke="#5a351b" stroke-width="1.4" opacity=".3" />
      <!-- 缺水时树皮发灰发暗 -->
      <path v-if="dry" d="M354 558 C352 508 356 458 364 412 C366 402 371 397 380 397 C389 397 394 402 396 412 C404 458 408 508 406 558 Z"
        fill="#8a8474" opacity=".22" />
      <path d="M354 558 C 344 557 334 561 324 567 C 338 565 348 563 356 561 Z" fill="#7a4c28" />
      <path d="M406 558 C 416 557 426 561 436 567 C 422 565 412 563 404 561 Z" fill="#7a4c28" />

      <!-- 幼苗的两片初生叶：树长开了就退场 -->
      <g :opacity="sproutLeaf">
        <path d="M366 422 C 352 412 338 411 330 418 C 341 421 354 425 366 422 Z" fill="#84b56a" />
        <path d="M394 414 C 405 401 420 399 429 406 C 418 411 405 418 394 414 Z" fill="#93c176" />
      </g>
    </g>

    <!-- 树冠组：枝、叶、果都挂在树冠里，跟着树冠一起缩放——苹果和树的比例永远正确 -->
    <g class="crown-g" :style="{ transform: `scale(${crownS.toFixed(4)})` }">
      <g class="crown">
        <!-- 枝 -->
        <g stroke="#7a4c28" stroke-linecap="round" fill="none">
          <path d="M370 414 C 352 388 332 360 312 338" stroke-width="12" />
          <path d="M392 414 C 412 388 434 360 456 338" stroke-width="12" />
          <path d="M380 408 C 380 384 378 356 378 334" stroke-width="9" />
        </g>
        <g stroke="#9a6a3e" stroke-linecap="round" fill="none" opacity=".5">
          <path d="M370 414 C 352 388 332 360 312 338" stroke-width="4" />
          <path d="M392 414 C 412 388 434 360 456 338" stroke-width="4" />
        </g>

        <!-- 树冠：圆团叠出来的蓬松轮廓，三层明暗做出受光面 -->
        <g class="canopy">
          <!-- 底层：深绿定轮廓 -->
          <g fill="url(#wt-c1)">
            <circle cx="272" cy="298" r="80" />
            <circle cx="490" cy="292" r="78" />
            <circle cx="380" cy="206" r="94" />
            <circle cx="302" cy="228" r="70" />
            <circle cx="460" cy="224" r="70" />
            <circle cx="380" cy="318" r="74" />
            <circle cx="214" cy="264" r="58" />
            <circle cx="546" cy="258" r="58" />
          </g>
          <!-- 中层：偏左上受光 -->
          <g fill="url(#wt-c2)">
            <circle cx="300" cy="266" r="66" />
            <circle cx="462" cy="258" r="64" />
            <circle cx="378" cy="188" r="72" />
            <circle cx="234" cy="252" r="46" />
            <circle cx="528" cy="246" r="46" />
            <circle cx="366" cy="300" r="52" />
            <circle cx="312" cy="322" r="48" />
            <circle cx="448" cy="312" r="48" />
          </g>
          <!-- 水够才长出来的新叶簇 -->
          <g fill="url(#wt-c2)" :opacity="leafFull * 0.85">
            <circle v-for="(e, i) in EXTRA_LEAVES" :key="'e' + i" :cx="e.x" :cy="e.y" :r="e.r" />
          </g>
          <!-- 高光层：树顶受光的那几团 -->
          <g fill="url(#wt-c3)" opacity=".88">
            <circle cx="312" cy="212" r="52" />
            <circle cx="408" cy="198" r="46" />
            <circle cx="256" cy="244" r="38" />
            <circle cx="372" cy="262" r="40" />
          </g>
          <ellipse cx="380" cy="332" rx="168" ry="58" fill="url(#wt-shade)" />
          <g fill="#d9eeba" opacity=".38">
            <circle cx="288" cy="176" r="7" /><circle cx="356" cy="156" r="6" />
            <circle cx="430" cy="172" r="7" /><circle cx="478" cy="222" r="6" />
            <circle cx="222" cy="238" r="6" /><circle cx="534" cy="230" r="5" />
          </g>
        </g>

        <!-- 苹果 -->
        <g class="fruits">
          <g
            v-for="f in items"
            :key="f.code"
            class="fruit"
            :class="[f.status, { dim: selected && selected !== f.code, sel: selected === f.code }]"
            :transform="`translate(${f.x},${f.y})`"
            tabindex="0"
            role="button"
            :aria-label="`${f.name}，${f.score} 分，${f.statusLabel}，${f.sub}`"
            @click="emit('select', f.code)"
            @keydown.enter.prevent="emit('select', f.code)"
            @keydown.space.prevent="emit('select', f.code)"
          >
            <g class="float" :style="{ animationDelay: f.delay }">
              <g class="zoom">
                <!-- 临界/风险才亮光环，平时让苹果保持干净 -->
                <circle v-if="f.showHalo" class="halo" :r="f.r + 15" :fill="`url(#wt-halo-${f.status})`" />
                <circle v-if="selected === f.code" class="pick-ring" :r="f.r + 16" :stroke="f.color" />
                <!-- 苹果本体：尺寸＝学分×成熟度，颜色＝作业完成度 -->
                <circle :r="f.r" :fill="`url(#wt-f-${f.code})`" class="body" />
                <ellipse :cx="-f.r * 0.34" :cy="-f.r * 0.42" :rx="f.r * 0.36" :ry="f.r * 0.22" fill="#fff" opacity=".52" />
                <circle :r="f.r" fill="none" stroke="#fffdf7" stroke-width="1" opacity=".35" />
                <circle :r="f.r" fill="none" :stroke="f.deep" stroke-width=".9" opacity=".3" />
                <!-- 施肥落地的光晕 -->
                <circle
                  v-if="popKeys[f.code]"
                  :key="'pop-' + f.code + '-' + popKeys[f.code]"
                  class="pop-ring"
                  :r="f.r + 5"
                  :stroke="f.color"
                  fill="none"
                  stroke-width="2.6"
                />
                <!-- 果柄 -->
                <path :d="`M0 ${-f.r + 1} C 1 ${-f.r - 5} 3 ${-f.r - 8} 6 ${-f.r - 11}`"
                  stroke="#7a5533" stroke-width="2.6" fill="none" stroke-linecap="round" />
                <!-- 果柄上的叶片：几片叶 = 几个学分 -->
                <g class="stem-leaves">
                  <ellipse
                    v-for="(lf, li) in f.leaves"
                    :key="li"
                    :cx="lf.x"
                    :cy="lf.y"
                    :rx="4.4 * lf.s"
                    :ry="2.1 * lf.s"
                    :transform="`rotate(${lf.rot} ${lf.x} ${lf.y})`"
                    fill="#6f9a5f"
                    :opacity="0.78 + 0.22 * lf.s"
                  />
                </g>
                <path :d="`M6 ${-f.r - 10} C 14 ${-f.r - 16} 24 ${-f.r - 14} 26 ${-f.r - 8} C 20 ${-f.r - 4} 11 ${-f.r - 5} 6 ${-f.r - 10} Z`"
                  fill="#6f9a5f" />
              </g>
            </g>
            <text class="f-name" :y="f.r + 21" text-anchor="middle" :opacity="f.lo">{{ f.label }}</text>
            <text class="f-sub" :y="f.r + 37" text-anchor="middle" :opacity="f.lo">
              <tspan :fill="f.ring">{{ f.sub }}</tspan>
            </text>
          </g>
        </g>
      </g>
    </g>

    <!-- 浇水落地：涟漪 + 水花（在树外，不跟树一起缩放） -->
    <g v-if="splashKey" :key="'sp-' + splashKey" class="splash">
      <ellipse class="sp-ring" cx="380" cy="552" rx="30" ry="8" fill="none" stroke="#7fb6e0" stroke-width="2.6" />
      <ellipse class="sp-ring sp-ring2" cx="380" cy="552" rx="30" ry="8" fill="none" stroke="#a8d4f2" stroke-width="2" />
      <circle class="sp-drop d1" cx="356" cy="536" r="3.4" fill="#8fc4ea" />
      <circle class="sp-drop d2" cx="404" cy="532" r="3" fill="#8fc4ea" />
      <circle class="sp-drop d3" cx="380" cy="522" r="3.8" fill="#a8d4f2" />
      <circle class="sp-drop d4" cx="344" cy="546" r="2.6" fill="#8fc4ea" />
      <circle class="sp-drop d5" cx="416" cy="544" r="2.8" fill="#8fc4ea" />
    </g>

    <!-- 光尘：一点活气，不影响读数 -->
    <g class="dust">
      <circle v-for="(p, i) in particles" :key="i" :cx="p.x" :cy="p.y" r="2.6" fill="#f3d69c"
        :style="{ animationDelay: `${p.d}s` }" />
    </g>
  </svg>
</template>

<style scoped>
.wt {
  display: block;
  width: 100%;
  height: auto;
}
/* 树干和树冠各长各的：水一袋袋施下去是分阶段长出来的，不是整体放大 */
.trunk-g {
  transform-box: view-box;
  transform-origin: 380px 556px;
  transition: transform 0.7s cubic-bezier(0.32, 1.16, 0.4, 1);
}
.crown-g {
  transform-box: view-box;
  transform-origin: 380px 556px;
  transition: transform 0.7s cubic-bezier(0.32, 1.16, 0.4, 1);
}
.crown {
  transform-box: view-box;
  transform-origin: 380px 556px;
  animation: wt-sway 10s ease-in-out infinite alternate;
}
/* 鼠标一进画面就停下摆动：果子在动的时候，人是点不准的 */
.wt:hover .crown {
  animation-play-state: paused;
}
.fruit {
  cursor: pointer;
  outline: none;
}
.float {
  transform-box: fill-box;
  transform-origin: center;
  animation: wt-bob 7s ease-in-out infinite alternate;
}
.fruit:hover .float,
.fruit:focus-visible .float {
  animation-play-state: paused;
}
.zoom {
  transform-box: fill-box;
  transform-origin: center;
  transition: transform 0.24s cubic-bezier(0.3, 0.9, 0.3, 1);
}
.fruit:hover .zoom,
.fruit:focus-visible .zoom {
  transform: scale(1.1);
}
/* 果实长大：几何属性过渡，一袋肥落下去是眼看着鼓起来的 */
.fruit .body,
.fruit .halo,
.fruit .zoom > circle,
.fruit .zoom > ellipse {
  transition:
    r 0.55s cubic-bezier(0.32, 1.28, 0.42, 1),
    cx 0.55s cubic-bezier(0.32, 1.28, 0.42, 1),
    cy 0.55s cubic-bezier(0.32, 1.28, 0.42, 1),
    rx 0.55s cubic-bezier(0.32, 1.28, 0.42, 1),
    ry 0.55s cubic-bezier(0.32, 1.28, 0.42, 1),
    fill 0.55s ease;
}
.fruit .halo {
  transform-box: fill-box;
  transform-origin: center;
  animation: wt-pulse 3.8s ease-in-out infinite;
}
.fruit.risk .halo {
  animation-duration: 2.2s;
}
.pop-ring {
  transform-box: fill-box;
  transform-origin: center;
  animation: wt-pop-out 0.62s ease-out forwards;
  pointer-events: none;
}
.pick-ring {
  fill: none;
  stroke-width: 2;
  stroke-dasharray: 5 5;
  opacity: 0.85;
  transform-box: fill-box;
  transform-origin: center;
  animation: wt-spin 9s linear infinite;
}
.fruit.dim {
  opacity: 0.45;
}
.f-name {
  font-size: 13px;
  font-weight: 600;
  fill: #3d3227;
  paint-order: stroke;
  stroke: rgba(253, 248, 240, 0.94);
  stroke-width: 3.6px;
  stroke-linejoin: round;
  pointer-events: none;
  transition: opacity 0.5s ease;
}
.f-sub {
  font-size: 11px;
  fill: #7a6a58;
  paint-order: stroke;
  stroke: rgba(253, 248, 240, 0.94);
  stroke-width: 3.2px;
  stroke-linejoin: round;
  pointer-events: none;
  transition: opacity 0.5s ease;
}
.dust circle {
  opacity: 0.6;
  animation: wt-drift 12s ease-in-out infinite;
}

/* 浇水落地：涟漪扩开，水珠溅起又落下 */
.splash .sp-ring {
  transform-box: fill-box;
  transform-origin: center;
  animation: wt-ring 0.75s ease-out forwards;
}
.splash .sp-ring2 {
  animation-delay: 0.12s;
}
.splash .sp-drop {
  transform-box: fill-box;
  transform-origin: center;
  animation: wt-spit 0.7s ease-out forwards;
}
.splash .d2 {
  animation-delay: 0.05s;
}
.splash .d3 {
  animation-delay: 0.02s;
}
.splash .d4 {
  animation-delay: 0.09s;
}
.splash .d5 {
  animation-delay: 0.07s;
}

/* 缺水：叶色发灰、叶尖下垂，但不暗示"树快死了" */
.wt.dry .canopy {
  filter: saturate(0.82) brightness(0.985);
}
.wt.dry .stem-leaves ellipse {
  transform-box: fill-box;
  transform-origin: center top;
  animation: wt-wilt 2.6s ease-in-out infinite alternate;
}

/* 天空星点：四角星与小圆点此起彼伏地闪，只动透明度和一点点缩放 */
.wt-spark {
  opacity: var(--op);
  transform-box: fill-box;
  transform-origin: center;
  animation: wt-spark-twinkle var(--dur) ease-in-out infinite;
  animation-delay: var(--dl);
}
@keyframes wt-spark-twinkle {
  0%,
  100% {
    opacity: calc(var(--op) * 0.22);
    transform: scale(0.88);
  }
  50% {
    opacity: var(--op);
    transform: scale(1);
  }
}

@keyframes wt-sway {
  from {
    transform: rotate(-0.6deg);
  }
  to {
    transform: rotate(0.6deg);
  }
}
@keyframes wt-bob {
  from {
    transform: translateY(-2.4px);
  }
  to {
    transform: translateY(2.4px);
  }
}
@keyframes wt-pulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 0.75;
  }
  50% {
    transform: scale(1.14);
    opacity: 1;
  }
}
@keyframes wt-spin {
  to {
    transform: rotate(360deg);
  }
}
@keyframes wt-drift {
  0%,
  100% {
    transform: translateY(0);
    opacity: 0.2;
  }
  50% {
    transform: translateY(-16px);
    opacity: 0.7;
  }
}
@keyframes wt-wilt {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(11deg);
  }
}
@keyframes wt-pop-out {
  0% {
    transform: scale(0.65);
    opacity: 0.95;
  }
  100% {
    transform: scale(1.65);
    opacity: 0;
  }
}
@keyframes wt-ring {
  0% {
    transform: scale(0.25);
    opacity: 0.95;
  }
  100% {
    transform: scale(1.9);
    opacity: 0;
  }
}
@keyframes wt-spit {
  0% {
    transform: translateY(6px) scale(0.5);
    opacity: 1;
  }
  55% {
    transform: translateY(-16px) scale(1.05);
    opacity: 1;
  }
  100% {
    transform: translateY(-4px) scale(0.7);
    opacity: 0;
  }
}
/* 窄屏上六颗果实的标签一定会打架：只留选中那一颗的标签，其余看下方详情 */
@media (max-width: 760px) {
  .f-name {
    font-size: 17px;
    stroke-width: 4.4px;
  }
  .f-sub {
    font-size: 14px;
    stroke-width: 3.8px;
  }
  .fruit .f-name,
  .fruit .f-sub {
    display: none;
  }
  .fruit.sel .f-name,
  .fruit.sel .f-sub {
    display: block;
  }
}
@media (prefers-reduced-motion: reduce) {
  .crown,
  .float,
  .fruit .halo,
  .pick-ring,
  .dust circle,
  .wt-spark,
  .wt.dry .stem-leaves ellipse {
    animation: none !important;
  }
  .wt-spark {
    opacity: calc(var(--op) * 0.55);
    transform: none;
  }
  .trunk-g,
  .crown-g,
  .fruit .body,
  .fruit .halo,
  .fruit .zoom > circle,
  .fruit .zoom > ellipse {
    transition: none !important;
  }
}
</style>
