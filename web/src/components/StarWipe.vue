<script setup lang="ts">
/**
 * 端口开屏：星坠 · 揭幕
 *
 * 序列（约 2.4s，无进度条，纯仪式感）：
 *   1. 0–260ms   整屏染成墨绿（--moss），页面沉到幕布后面
 *   2. 120ms     右上角亮起一颗四角星（与登录页同款实心星）
 *   3. 320ms     星星沿一条下坠的弧线掠向左下，身后拖出奶白痕迹
 *   4. 1440ms    星星抵达左下角，这颗星就是切口；两块绿幕沿弧线法向分开
 *   5. 2370ms    幕布离场，露出当前端口的真实内容
 *
 * 几何全部由视口算：轨迹是一条二次贝塞尔弧（控制点朝左上鼓出：从右上角平着掠过天顶，
 * 越往左下越陡，像流星被重力拽下去），切口就是这条弧本身，
 * 所以任何分辨率下星星、奶白痕迹、幕布裂口三者严格重合。
 */
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps<{ seq: number }>();

/** 时间线（ms）：调这里就能整体调快慢，几何不用动 */
const T = {
  starIn: 120, // 星星亮起
  flyStart: 320, // 起飞（= starIn + 200，留一次呼吸）
  flyDur: 1000, // 星星沿弧线飞完一趟
  landPad: 120, // 落定后停一拍，再揭幕——"划到最左下角，然后才打开"
  openDur: 860, // 幕布分开
  tailPad: 70, // 收尾余量
};
const openAt = T.flyStart + T.flyDur + T.landPad;

/** 两块幕布接缝的重叠量（px）：足够盖住抗锯齿漏出的那一条底色 */
const SEAM = 1.2;

const active = ref(false);
const starIn = ref(false);
const open = ref(false);
const reduce = ref(false);

/**
 * 弧线几何（px）：S 右上角 → E 左下角，控制点 C 朝右下鼓出。
 * 同时给出两块幕布的裁剪路径——以这条弧为界，合起来严丝合缝。
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
  px: 0,
  py: 0,
});
/** 星星当前位置 / 弧线已画出的长度 */
const star = ref({ x: 0, y: 0 });
const drawn = ref(0);

let timers: number[] = [];
let raf = 0;
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

  // 弧长：采样累加，用于 stroke-dasharray 让痕迹随星星一起长出来
  let len = 0;
  let px = sx;
  let py = sy;
  for (let i = 1; i <= 64; i++) {
    const t = i / 64;
    const mt = 1 - t;
    const x = mt * mt * sx + 2 * mt * t * cx + t * t * ex;
    const y = mt * mt * sy + 2 * mt * t * cy + t * t * ey;
    len += Math.hypot(x - px, y - py);
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
    // 沿法向推开：0.94 个另一条边长，足够把整块三角甩出屏幕
    px: Math.round(h * 0.94),
    py: Math.round(w * 0.94),
  };
  star.value = { x: sx, y: sy };
  drawn.value = 0;
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
    <div
      v-if="active"
      class="sw"
      :class="{ 'sw-open': open }"
      :style="{ '--px': `${geo.px}px`, '--py': `${geo.py}px` }"
      aria-hidden="true"
    >
      <!-- 两块绿幕：以那条弧为界，合起来严丝合缝，分开就是"被划开" -->
      <div
        class="sw-pane sw-pane-a"
        :style="{ clipPath: geo.pa, webkitClipPath: geo.pa } as any"
      ></div>
      <div
        class="sw-pane sw-pane-b"
        :style="{ clipPath: geo.pb, webkitClipPath: geo.pb } as any"
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

/* ---- 幕布 ---- */
.sw-pane {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(72% 58% at 74% 16%, #1d6a5b 0%, rgba(29, 106, 91, 0) 62%),
    linear-gradient(158deg, #1a6154 0%, #16564a 46%, #0e3d35 100%);
  animation: sw-veil 260ms ease-out both;
  will-change: transform, opacity;
}
@keyframes sw-veil {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}
.sw.sw-open .sw-pane-a {
  animation: sw-open-a 860ms cubic-bezier(0.55, 0.02, 0.32, 1) both;
}
.sw.sw-open .sw-pane-b {
  animation: sw-open-b 860ms cubic-bezier(0.55, 0.02, 0.32, 1) both;
}
@keyframes sw-open-a {
  0% {
    transform: translate(0, 0);
    opacity: 1;
  }
  72% {
    opacity: 1;
  }
  100% {
    transform: translate(calc(-1 * var(--px)), calc(-1 * var(--py)));
    opacity: 0;
  }
}
@keyframes sw-open-b {
  0% {
    transform: translate(0, 0);
    opacity: 1;
  }
  72% {
    opacity: 1;
  }
  100% {
    transform: translate(var(--px), var(--py));
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
  .sw-pane {
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
