<script setup lang="ts">
/**
 * 端口开屏：星坠 · 揭幕
 *
 * 序列（约 2.8s，无进度条，纯仪式感）：
 *   1. 0–260ms   整屏染成墨绿（--moss），页面沉到幕布后面
 *   2. 120ms     右上角亮起一颗四角星（与登录页同款实心星）
 *   3. 320ms     星星沿一条下坠的弧线掠向左下，身后拖出奶白痕迹
 *   4. 1380ms    星星抵达左下角，这颗星就是切口
 *   5. 1440ms→   **不是把幕布推开，而是让幕布从切口开始向两侧以渐变褪去**：
 *                擦除带是一条贴着弧线生长的渐变蒙版——透明区 =
 *                "到弧线的距离 ≤ r"的区域，r 匀速变大，边缘是十层灰阶
 *                叠出的连续渐变（越远离切口越透）；切口全长同时开始化、
 *                两块幕布按各自到最远角的距离缩放，同时化尽、同时结束
 *   6. 2800ms    幕布散尽，露出当前端口的真实内容
 *
 * 几何全部由视口算：轨迹是一条二次贝塞尔弧（控制点朝左上鼓出：从右上角平着掠过天顶，
 * 越往左下越陡，像流星被重力拽下去），切口就是这条弧本身，
 * 所以任何分辨率下星星、奶白痕迹、幕布裂口三者严格重合。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps<{ seq: number }>();

/** 时间线（ms）：调这里就能整体调快慢，几何不用动 */
const T = {
  starIn: 120, // 星星亮起
  flyStart: 320, // 起飞（= starIn + 200，留一次呼吸）
  flyDur: 1000, // 星星沿弧线飞完一趟
  landPad: 60, // 落定后几乎不停，立刻开始化幕（停久了像卡住）
  openDur: 1300, // 幕布从切口化开、散尽
  tailPad: 90, // 收尾余量
};
const openAt = T.flyStart + T.flyDur + T.landPad;

/** 两块幕布接缝的重叠量（px）：足够盖住抗锯齿漏出的那一条底色 */
const SEAM = 1.2;

const active = ref(false);
const starIn = ref(false);
const open = ref(false);
const reduce = ref(false);

/**
 * 弧线几何（px）：S 右上角 → E 左下角，控制点 C 朝左上鼓出。
 * 同时给出两块幕布的裁剪路径——以这条弧为界，合起来严丝合缝。
 * dA / dB 是两块幕布各自离弧线最远点的距离（外角到弧的最近距离），
 * 化幕时两块分别按这个距离缩放擦除半径，才能同时化尽。
 */
const geo = ref({
  w: 0,
  h: 0,
  sx: 0,
  sy: 0,
  cx: 0,
  cy: 0,
  ex: 0,
  ey: 0,
  d: "",
  pa: "",
  pb: "",
  len: 0,
  dA: 1,
  dB: 1,
});
/** 星星当前位置 / 弧线已画出的长度 */
const star = ref({ x: 0, y: 0 });
const drawn = ref(0);
/** 化幕进度 0→1：擦除半径 = 各自最大距离 × p，两块同步走完 */
const meltP = ref(0);

/** 渐变软边总宽（px）：擦除前沿到全透的距离，越大越像雾化褪去 */
const FEATHER = 260;
/** 软边灰阶层数：叠出渐变的骨架，台阶由高斯模糊抹平 */
const STEPS = 8;
/** 黑芯越过比例：擦除前沿在进度 82% 时抵达各块最远角，
 *  剩下的时间让渐变软边扫过角落，保证收尾干净、不残留绿色 */
const OVER = 0.82;

/* 擦除前沿半径（px）：两边共用同一个进度 p，各按 dA/dB 缩放——
   同时开始、同时抵达各自的角、同时结束 */
const rA = computed(() => (geo.value.dA * meltP.value) / OVER);
const rB = computed(() => (geo.value.dB * meltP.value) / OVER);

/**
 * 软边的灰阶环：从最宽最浅画到最窄最深，最后压一层黑芯。
 * 每层提供一档透明度，叠起来就是「越远离擦除前沿越透」的线性渐变；
 * 软边宽度随前沿半径一起从 0 长出来（前期 edge 偏脆、越化越柔），
 * 进度为 0 时所有环宽度都是 0——幕布是完完整整的纯绿，不会有凭空的光晕。
 */
function rings(r: number): { w: number; c: string }[] {
  const list: { w: number; c: string }[] = [];
  const feather = FEATHER * Math.min(1, r / FEATHER);
  for (let i = STEPS; i >= 1; i--) {
    const g = Math.round((255 * i) / STEPS);
    list.push({
      w: 2 * r + (2 * feather * i) / STEPS,
      c: `rgb(${g}, ${g}, ${g})`,
    });
  }
  list.push({ w: 2 * r, c: "#000" });
  return list;
}
const ringsA = computed(() => rings(rA.value));
const ringsB = computed(() => rings(rB.value));

let timers: number[] = [];
let raf = 0;
let meltRaf = 0;
const at = (ms: number, fn: () => void) => {
  timers.push(window.setTimeout(fn, ms));
};
const clear = () => {
  timers.forEach((t) => window.clearTimeout(t));
  timers = [];
  if (raf) {
    cancelAnimationFrame(raf);
    raf = 0;
  }
  if (meltRaf) {
    cancelAnimationFrame(meltRaf);
    meltRaf = 0;
  }
};

function measure() {
  const w = Math.max(1, window.innerWidth);
  const h = Math.max(1, window.innerHeight);
  const sx = w;
  const sy = 0;
  const ex = 0;
  const ey = h;

  // 对角线的法向单位向量 (h, w)/斜边，原本指向右下；这里取反（朝左上），
  // 弧就往上鼓：右上角几乎平着掠过，落到左下角前越来越陡，是流星下坠的走势
  const diag = Math.hypot(w, h);
  const nx = h / diag;
  const ny = w / diag;
  const k = 0.17 * diag;
  const cx = (sx + ex) / 2 - nx * k;
  const cy = (sy + ey) / 2 - ny * k;

  // 弧长 + 两块幕布离弧的最远距离：采样累加/取最小距离
  // dA = 左上外角 (0,0) 到弧的最近距离，dB = 右下外角 (w,h) 到弧的最近距离。
  // 化幕时 A/B 分别按 dA/dB 铺满擦除半径，两块才能同时化尽（弧不居中，两边距离不同）
  let len = 0;
  let dA = Infinity;
  let dB = Infinity;
  let px = sx;
  let py = sy;
  for (let i = 0; i <= 64; i++) {
    const t = i / 64;
    const mt = 1 - t;
    const x = mt * mt * sx + 2 * mt * t * cx + t * t * ex;
    const y = mt * mt * sy + 2 * mt * t * cy + t * t * ey;
    if (i > 0) len += Math.hypot(x - px, y - py);
    dA = Math.min(dA, Math.hypot(x, y));
    dB = Math.min(dB, Math.hypot(x - w, y - h));
    px = x;
    py = y;
  }

  geo.value = {
    w,
    h,
    sx,
    sy,
    cx,
    cy,
    ex,
    ey,
    d: `M${sx} ${sy}Q${cx} ${cy} ${ex} ${ey}`,
    // 左上那块：顶边 + 弧 + 左边闭合
    pa: `path('M0 0L${sx} ${sy}Q${cx} ${cy} ${ex} ${ey}Z')`,
    // 右下那块：弧 + 底边 + 右边闭合。弧本身往左上多压 1.2px，
    // 两块严丝合缝时浏览器抗锯齿会在接缝漏一条极细的底色线，压这一点就盖住了
    pb: `path('M${sx - nx * SEAM} ${sy - ny * SEAM}Q${cx - nx * SEAM} ${cy - ny * SEAM} ${ex - nx * SEAM} ${ey - ny * SEAM}L${w} ${h}Z')`,
    len,
    dA: Math.round(dA),
    dB: Math.round(dB),
  };
  star.value = { x: sx, y: sy };
  drawn.value = 0;
  meltP.value = 0;
}

/** 弧上一点（t ∈ [0,1]） */
function pointAt(t: number) {
  const g = geo.value;
  const mt = 1 - t;
  return {
    x: mt * mt * g.sx + 2 * mt * t * g.cx + t * t * g.ex,
    y: mt * mt * g.sy + 2 * mt * t * g.cy + t * t * g.ey,
  };
}

function startFly() {
  const t0 = performance.now();
  const loop = () => {
    const p = Math.min(1, (performance.now() - t0) / T.flyDur);
    // easeInOutSine：起步轻、落点稳
    const e = 0.5 - Math.cos(Math.PI * p) / 2;
    star.value = pointAt(e);
    drawn.value = geo.value.len * e;
    raf = p < 1 ? requestAnimationFrame(loop) : 0;
  };
  raf = requestAnimationFrame(loop);
}

/**
 * 化幕：只推进擦除半径，不给幕布加位移。
 * 半径严格线性增长（匀速退潮）：擦除区面积 ∝ 弧长×半径，天然接近匀速，
 * 不需要也不会出现"先僵一下再猛化"的节奏；两块幕布共用同一个 p，
 * 半径各按 dA/dB 缩放，起点终点都严格对齐。
 */
function startMelt() {
  const t0 = performance.now();
  const loop = () => {
    const p = Math.min(1, (performance.now() - t0) / T.openDur);
    meltP.value = p;
    meltRaf = p < 1 ? requestAnimationFrame(loop) : 0;
  };
  meltRaf = requestAnimationFrame(loop);
}

function play() {
  clear();
  measure();
  open.value = false;
  starIn.value = false;
  active.value = true;

  if (reduce.value) {
    // 系统开了"减少动态效果"：只做一次 220ms 的淡出，不划星不裂幕
    at(240, () => (active.value = false));
    return;
  }

  at(T.starIn, () => (starIn.value = true));
  at(T.flyStart, () => startFly());
  at(openAt, () => {
    open.value = true;
    starIn.value = false;
    startMelt();
  });
  at(openAt + T.openDur + T.tailPad, () => {
    active.value = false;
    measure();
  });
}

watch(
  () => props.seq,
  () => play(),
);

onMounted(() => {
  reduce.value = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  measure();
  // 进端口时身份可能先于组件挂载就绪（seq 已是 1），那时 watch 收不到变化，
  // 这里补一次，避免"刷新页面不播、点进来才播"的时有时无
  if (props.seq > 0) play();
  window.addEventListener("resize", measure, { passive: true });
});

onBeforeUnmount(() => {
  clear();
  window.removeEventListener("resize", measure);
});
</script>

<template>
  <Teleport to="body">
    <!-- 化幕蒙版的定义：白色矩形 = 可见，沿弧线的一组灰阶描边 = 渐变擦除。
         灰阶层叠出渐变骨架，高斯模糊把台阶融成连续过渡；
         擦除区 = 「到弧线的距离 ≤ r」的渐变带，波前永远贴着弧线的形状 -->
    <svg v-if="active" class="sw-defs" width="0" height="0" aria-hidden="true">
      <defs>
        <filter id="swSoft" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="14" />
        </filter>
        <mask id="swmA" maskUnits="userSpaceOnUse" x="0" y="0" :width="geo.w" :height="geo.h">
          <rect x="0" y="0" :width="geo.w" :height="geo.h" fill="#fff" />
          <g filter="url(#swSoft)">
            <path
              v-for="(r, i) in ringsA"
              :key="i"
              :d="geo.d"
              fill="none"
              :stroke="r.c"
              :stroke-width="r.w"
              stroke-linecap="round"
            />
          </g>
        </mask>
        <mask id="swmB" maskUnits="userSpaceOnUse" x="0" y="0" :width="geo.w" :height="geo.h">
          <rect x="0" y="0" :width="geo.w" :height="geo.h" fill="#fff" />
          <g filter="url(#swSoft)">
            <path
              v-for="(r, i) in ringsB"
              :key="i"
              :d="geo.d"
              fill="none"
              :stroke="r.c"
              :stroke-width="r.w"
              stroke-linecap="round"
            />
          </g>
        </mask>
      </defs>
    </svg>

    <div
      v-if="active"
      class="sw"
      :class="{ 'sw-open': open }"
      aria-hidden="true"
    >
      <!-- 两块绿幕：以那条弧为界，合起来严丝合缝。
           化开时不动位置，各蒙一片贴着弧线生长的 SVG 擦除蒙版 -->
      <div
        class="sw-pane sw-pane-a"
        :style="{
          clipPath: geo.pa,
          webkitClipPath: geo.pa,
          maskImage: 'url(#swmA)',
          WebkitMaskImage: 'url(#swmA)',
        } as any"
      ></div>
      <div
        class="sw-pane sw-pane-b"
        :style="{
          clipPath: geo.pb,
          webkitClipPath: geo.pb,
          maskImage: 'url(#swmB)',
          WebkitMaskImage: 'url(#swmB)',
        } as any"
      ></div>

      <!-- 奶白痕迹：沿同一条弧画出来，长度由星星的进度驱动，尾端渐隐、头部实心 -->
      <svg class="sw-arc" :width="geo.w" :height="geo.h" :viewBox="`0 0 ${geo.w} ${geo.h}`">
        <defs>
          <linearGradient
            id="swTrail"
            gradientUnits="userSpaceOnUse"
            :x1="geo.sx"
            :y1="geo.sy"
            :x2="geo.ex"
            :y2="geo.ey"
          >
            <stop offset="0" stop-color="#f6f2e8" stop-opacity="0" />
            <stop offset="0.42" stop-color="#f6f2e8" stop-opacity="0.46" />
            <stop offset="1" stop-color="#f6f2e8" stop-opacity="1" />
          </linearGradient>
        </defs>
        <path
          class="sw-arc-line"
          :d="geo.d"
          :style="{ strokeDasharray: geo.len, strokeDashoffset: geo.len - drawn }"
        />
      </svg>

      <!-- 星：外层只管位移，内层只管大小与显隐，互不抢 transform -->
      <div class="sw-fly" :style="{ transform: `translate3d(${star.x}px, ${star.y}px, 0)` }">
        <div class="sw-star" :class="{ 'is-in': starIn }">
          <svg viewBox="0 0 100 100">
            <path d="M50 2C54 30 70 46 98 50 70 54 54 70 50 98 46 70 30 54 2 50 30 46 46 30 50 2Z" />
          </svg>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.sw {
  position: fixed;
  inset: 0;
  z-index: 10000;
  overflow: hidden;
  /* 动画期间挡住点击：幕布还没开，底下的按钮不该被误触 */
  pointer-events: auto;
}
.sw-open {
  pointer-events: none;
}
/* 蒙版定义容器：0×0 但不能 display:none，否则部分浏览器不解析引用 */
.sw-defs {
  position: fixed;
  left: 0;
  top: 0;
  pointer-events: none;
}

/* ---- 幕布 ---- */
.sw-pane {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(72% 58% at 74% 16%, #1d6a5b 0%, rgba(29, 106, 91, 0) 62%),
    linear-gradient(158deg, #1a6154 0%, #16564a 46%, #0e3d35 100%);
  animation: sw-veil 260ms ease-out both;
  will-change: opacity;
}
@keyframes sw-veil {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}
/* 化幕不看 CSS 关键帧：擦除半径由脚本逐帧推进（见 coreA / coreB）。
   这条淡出只是兜底——万一 SVG 蒙版没生效，幕布也不会永远卡在屏幕上；
   正常播放时它落在蒙版已化得差不多的时候，看不出它在参与 */
.sw.sw-open .sw-pane {
  animation: sw-veil 260ms ease-out both, sw-lift 420ms ease-in 880ms both;
}
@keyframes sw-lift {
  0% {
    opacity: 1;
  }
  100% {
    opacity: 0;
  }
}

/* ---- 奶白痕迹（弧线） ---- */
.sw-arc {
  position: absolute;
  left: 0;
  top: 0;
  overflow: visible;
  pointer-events: none;
}
.sw-arc-line {
  fill: none;
  stroke: url(#swTrail);
  stroke-width: 2.6;
  stroke-linecap: round;
  filter: drop-shadow(0 0 5px rgba(246, 242, 232, 0.85)) drop-shadow(0 0 14px rgba(246, 242, 232, 0.42));
}
/* 揭幕时光刃"燃尽"：先亮住，再快速收掉，不是硬切 */
.sw.sw-open .sw-arc {
  animation: sw-blade 620ms ease-out both;
}
@keyframes sw-blade {
  0%,
  34% {
    opacity: 1;
  }
  100% {
    opacity: 0;
  }
}

/* ---- 星 ---- */
.sw-fly {
  position: absolute;
  left: 0;
  top: 0;
  width: 0;
  height: 0;
  will-change: transform;
}
.sw-star {
  position: absolute;
  left: -21px;
  top: -21px;
  width: 42px;
  height: 42px;
  color: #f6f2e8;
  opacity: 0;
  transform: scale(0.2);
  transition: transform 280ms cubic-bezier(0.22, 1.5, 0.4, 1), opacity 180ms ease-out;
  filter: drop-shadow(0 0 6px rgba(246, 242, 232, 0.9)) drop-shadow(0 0 17px rgba(246, 242, 232, 0.42));
}
.sw-star.is-in {
  opacity: 1;
  transform: scale(1);
}
.sw-star svg {
  display: block;
  width: 100%;
  height: 100%;
}
.sw-star path {
  fill: currentColor;
  stroke: currentColor;
  stroke-width: 8;
  stroke-linejoin: round;
}

/* 窄屏：星星与痕迹都按视口缩放，只把光晕收一点，免得糊成一片 */
@media (max-width: 760px) {
  .sw-star {
    left: -16px;
    top: -16px;
    width: 32px;
    height: 32px;
  }
  .sw-arc-line {
    stroke-width: 2.2;
  }
}

/* 尊重系统偏好：不划星、不裂幕，只留一次淡出 */
@media (prefers-reduced-motion: reduce) {
  .sw-pane,
  .sw.sw-open .sw-pane {
    animation: none;
  }
  .sw-star {
    display: none;
  }
  .sw-arc {
    display: none;
  }
  .sw {
    animation: sw-dim 220ms ease-out both;
  }
  @keyframes sw-dim {
    0%,
    40% {
      opacity: 1;
    }
    100% {
      opacity: 0;
    }
  }
}
</style>
