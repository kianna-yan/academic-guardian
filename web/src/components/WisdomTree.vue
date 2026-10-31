<script setup lang="ts">
import { computed } from "vue";
import type { TreeFruit } from "@/types";

/**
 * 智慧树：一棵树上看完一个学期的几门课。
 *
 * 不用图表语言（没有坐标轴、没有网格），它是一张"树"，但信息一项不少：
 * - 一颗果实 = 一门课；
 * - 果实颜色 = 学科的专属色（可切换成"按状态"）；
 * - 果实外圈的光环 = 这门课现在的风险状态（绿 / 黄 / 红），始终可见；
 * - 果实大小 = 学分，越重的课果实越大；
 * - 树根 = 六个评分因素；树冠的浓密程度跟着整体状态轻微变化。
 */
const props = withDefaults(
  defineProps<{
    fruits: TreeFruit[];
    mode?: "subject" | "status";
    selected?: string | null;
  }>(),
  { mode: "subject", selected: null },
);

const emit = defineEmits<{ (e: "select", code: string): void }>();

/** 学科专属色：同一门课在所有人的树上都是同一个颜色，便于对照 */
const SUBJECT_COLORS = ["#d2691e", "#2f7fc4", "#7b52c9", "#12876f", "#c93f6d", "#e0a020", "#4b6fc0", "#b04a2f"];

function colorOf(code: string): string {
  let h = 0;
  for (let i = 0; i < code.length; i++) h = (h * 31 + code.charCodeAt(i)) % 9973;
  return SUBJECT_COLORS[h % SUBJECT_COLORS.length];
}

const STATUS: Record<TreeFruit["status"], { color: string; label: string }> = {
  great: { color: "#2f8f6b", label: "很稳" },
  ok: { color: "#46a06a", label: "较稳" },
  watch: { color: "#e88a1e", label: "临界" },
  risk: { color: "#d9483b", label: "有挂科风险" },
};

/** 果实的挂点：沿树冠外沿排开，中间偏前留给学分最重的那门 */
const SLOTS = [
  { x: 306, y: 212 },
  { x: 458, y: 204 },
  { x: 224, y: 308 },
  { x: 542, y: 300 },
  { x: 378, y: 288 },
  { x: 518, y: 384 },
  { x: 204, y: 392 },
  { x: 450, y: 374 },
];

/** 按视觉宽度截断课程名：中文按 2 个宽度算，英文按 1 个算 */
function truncate(name: string, maxWidth: number): string {
  let w = 0;
  let out = "";
  for (const ch of name) {
    w += /[\u4e00-\u9fa5]/.test(ch) ? 2 : 1;
    if (w > maxWidth) return `${out}…`;
    out += ch;
  }
  return out;
}

function hexToRgb(hex: string) {
  const v = hex.replace("#", "");
  return [parseInt(v.slice(0, 2), 16), parseInt(v.slice(2, 4), 16), parseInt(v.slice(4, 6), 16)];
}
/** amt > 0 提亮，< 0 压暗 */
function shade(hex: string, amt: number): string {
  const [r, g, b] = hexToRgb(hex);
  const f = (c: number) => Math.round(amt >= 0 ? c + (255 - c) * amt : c * (1 + amt));
  return `rgb(${f(r)},${f(g)},${f(b)})`;
}

const items = computed(() => {
  const list = props.fruits.slice(0, SLOTS.length);
  return list.map((f, i) => {
    const slot = SLOTS[f.slot ?? i] ?? SLOTS[i % SLOTS.length];
    const subject = colorOf(f.code);
    const color = props.mode === "status" ? STATUS[f.status].color : subject;
    const r = Math.round(17 + (f.credit || 2) * 2);
    return {
      ...f,
      x: slot.x,
      y: slot.y,
      r,
      color,
      light: shade(color, 0.28),
      deep: shade(color, -0.18),
      ring: STATUS[f.status].color,
      statusLabel: STATUS[f.status].label,
      delay: `${(i * 0.7).toFixed(1)}s`,
      label: truncate(f.name, 18),
    };
  });
});

/** 树冠浓密度：红的果实越多，树冠收得越紧（只轻微变化，别暗示"树快死了"） */
const crownScale = computed(() => {
  if (!props.fruits.length) return 1;
  const bad = props.fruits.filter((f) => f.status === "risk").length;
  return 1 - Math.min(bad, 3) * 0.016;
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

/** 树冠边缘的叶簇：让轮廓不是光滑的椭圆 */
const BUMPS = [
  { x: 168, y: 268, r: 26 }, { x: 186, y: 330, r: 24 }, { x: 214, y: 372, r: 22 },
  { x: 268, y: 396, r: 24 }, { x: 330, y: 404, r: 20 }, { x: 402, y: 400, r: 22 },
  { x: 468, y: 398, r: 21 }, { x: 530, y: 378, r: 24 }, { x: 576, y: 336, r: 23 },
  { x: 596, y: 276, r: 25 }, { x: 578, y: 208, r: 22 }, { x: 534, y: 158, r: 21 },
  { x: 470, y: 124, r: 22 }, { x: 396, y: 108, r: 21 }, { x: 320, y: 118, r: 22 },
  { x: 250, y: 150, r: 23 }, { x: 196, y: 196, r: 22 },
];
</script>

<template>
  <svg class="wt" viewBox="78 76 620 528" role="img" aria-label="智慧树：每颗果实是一门课">
    <defs>
      <radialGradient id="wt-sky" cx="46%" cy="8%" r="92%">
        <stop offset="0" stop-color="#fffdf7" />
        <stop offset="52%" stop-color="#fbf3e6" />
        <stop offset="100%" stop-color="#f0e3cb" />
      </radialGradient>
      <radialGradient id="wt-sun" cx="50%" cy="50%" r="50%">
        <stop offset="0" stop-color="#ffe4b0" stop-opacity=".7" />
        <stop offset="58%" stop-color="#ffe9c4" stop-opacity=".24" />
        <stop offset="100%" stop-color="#ffe9c4" stop-opacity="0" />
      </radialGradient>
      <linearGradient id="wt-ground" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#eee2ca" />
        <stop offset="100%" stop-color="#dbc7a5" />
      </linearGradient>
      <linearGradient id="wt-trunk" x1="0" y1="0" x2="1" y2="0.15">
        <stop offset="0" stop-color="#714524" />
        <stop offset="26%" stop-color="#a3703f" />
        <stop offset="62%" stop-color="#8d5a33" />
        <stop offset="100%" stop-color="#673d20" />
      </linearGradient>
      <radialGradient id="wt-c1" gradientUnits="userSpaceOnUse" cx="318" cy="168" r="352">
        <stop offset="0" stop-color="#a4c68c" />
        <stop offset="52%" stop-color="#86ac70" />
        <stop offset="100%" stop-color="#5d8250" />
      </radialGradient>
      <radialGradient id="wt-c2" gradientUnits="userSpaceOnUse" cx="306" cy="152" r="322">
        <stop offset="0" stop-color="#bcdc9f" />
        <stop offset="55%" stop-color="#9cc082" />
        <stop offset="100%" stop-color="#779d63" />
      </radialGradient>
      <radialGradient id="wt-c3" gradientUnits="userSpaceOnUse" cx="296" cy="142" r="238">
        <stop offset="0" stop-color="#d9eeba" />
        <stop offset="62%" stop-color="#bcd9a0" />
        <stop offset="100%" stop-color="#a6c88c" />
      </radialGradient>
      <radialGradient id="wt-halo-great" cx="50%" cy="50%" r="50%">
        <stop offset="0" stop-color="#2f8f6b" stop-opacity=".42" />
        <stop offset="72%" stop-color="#2f8f6b" stop-opacity=".22" />
        <stop offset="100%" stop-color="#2f8f6b" stop-opacity="0" />
      </radialGradient>
      <radialGradient id="wt-halo-ok" cx="50%" cy="50%" r="50%">
        <stop offset="0" stop-color="#46a06a" stop-opacity=".4" />
        <stop offset="72%" stop-color="#46a06a" stop-opacity=".2" />
        <stop offset="100%" stop-color="#46a06a" stop-opacity="0" />
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
        <stop offset="0" stop-color="#3f5f3a" stop-opacity=".3" />
        <stop offset="100%" stop-color="#3f5f3a" stop-opacity="0" />
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
        <path d="M348 558 C352 520 357 484 362 450 L366 402 L394 402 C398 450 402 484 408 518 C412 540 414 550 416 558 Z" />
      </clipPath>
    </defs>

    <!-- 天光 -->
    <rect x="0" y="0" width="760" height="620" fill="url(#wt-sky)" />
    <circle cx="566" cy="132" r="150" fill="url(#wt-sun)" />

    <!-- 地面 -->
    <path d="M0 548 C 120 530 250 544 380 540 C 510 536 640 528 760 542 L760 620 L0 620 Z" fill="url(#wt-ground)" />
    <path d="M0 560 C 140 544 260 556 380 552 C 500 548 630 542 760 554" fill="none" stroke="#c9b28c" stroke-width="1.5" opacity=".65" />
    <ellipse cx="380" cy="556" rx="216" ry="22" fill="url(#wt-shadow)" />

    <!-- 草地细节 -->
    <g stroke="#a2b978" stroke-width="1.6" stroke-linecap="round" fill="none" opacity=".8">
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

    <!-- 根：六个评分因素，埋在地下，不出声但决定了树能长多高 -->
    <g stroke="#835229" stroke-width="6" stroke-linecap="round" fill="none" opacity=".85">
      <path d="M358 552 C 344 560 330 568 312 574" />
      <path d="M404 552 C 418 560 434 566 452 572" />
    </g>
    <g stroke="#a3703f" stroke-width="2.6" stroke-linecap="round" fill="none" opacity=".7">
      <path d="M330 568 C 320 574 314 578 306 582" />
      <path d="M436 566 C 446 572 452 576 460 580" />
    </g>

    <!-- 树干 -->
    <path d="M348 558 C352 520 357 484 362 450 L366 402 L394 402 C398 450 402 484 408 518 C412 540 414 550 416 558 Z"
      fill="url(#wt-trunk)" />
    <g clip-path="url(#wt-trunk-clip)" stroke="#5f381c" stroke-width="1.7" fill="none" opacity=".34" stroke-linecap="round">
      <path d="M366 552 C 361 512 366 472 372 436" />
      <path d="M382 550 C 378 508 383 470 387 432" />
      <path d="M357 526 C 362 500 360 476 366 452" />
      <path d="M396 520 C 392 494 396 470 400 444" />
      <path d="M354 556 C 362 550 370 548 378 548" />
      <path d="M390 556 C 398 552 404 550 410 550" />
    </g>
    <path d="M348 558 C352 520 357 484 362 450 L366 402 L394 402 C398 450 402 484 408 518 C412 540 414 550 416 558"
      fill="none" stroke="#5a351b" stroke-width="1.4" opacity=".32" />
    <path d="M348 558 C 338 557 328 561 318 567 C 332 565 342 563 350 561 Z" fill="#714524" />
    <path d="M416 558 C 426 557 436 561 446 567 C 432 565 422 563 414 561 Z" fill="#714524" />

    <!-- 树冠 + 枝干（枝干大半被叶子挡住，露出来的几段决定"这棵树长没长开"） -->
    <g :transform="`translate(380 556) scale(${crownScale}) translate(-380 -556)`">
      <g class="crown">
        <g stroke="#8d5a33" stroke-linecap="round" fill="none">
          <path d="M372 408 C 348 380 316 350 284 320" stroke-width="13" />
          <path d="M392 408 C 418 380 450 350 484 320" stroke-width="13" />
          <path d="M376 404 C 362 364 346 326 336 292" stroke-width="9" />
          <path d="M390 404 C 404 362 420 326 430 292" stroke-width="9" />
        </g>
        <g stroke="#a3703f" stroke-linecap="round" fill="none" opacity=".5">
          <path d="M372 408 C 348 380 316 350 284 320" stroke-width="4" />
          <path d="M392 408 C 418 380 450 350 484 320" stroke-width="4" />
        </g>

        <!-- 树冠：三层，每层统一取一张渐变，椭圆叠起来才是一整团，而不是一串珠子 -->
        <g class="canopy">
          <!-- 底层：深绿，外沿用一圈圆拼出不规则轮廓 -->
          <g fill="url(#wt-c1)">
            <ellipse cx="302" cy="292" rx="146" ry="102" />
            <ellipse cx="462" cy="288" rx="144" ry="102" />
            <ellipse cx="380" cy="212" rx="162" ry="116" />
            <circle v-for="(b, i) in BUMPS" :key="'b' + i" :cx="b.x" :cy="b.y" :r="b.r" />
          </g>
          <!-- 中层：整体偏左上，做出受光面 -->
          <g fill="url(#wt-c2)">
            <ellipse cx="290" cy="272" rx="132" ry="92" />
            <ellipse cx="404" cy="252" rx="126" ry="90" />
            <ellipse cx="380" cy="190" rx="128" ry="86" />
            <ellipse cx="474" cy="270" rx="104" ry="74" />
            <ellipse cx="256" cy="300" rx="96" ry="66" />
            <circle cx="232" cy="300" r="30" /><circle cx="266" cy="342" r="27" />
            <circle cx="336" cy="360" r="27" /><circle cx="428" cy="356" r="26" />
            <circle cx="496" cy="332" r="28" /><circle cx="528" cy="288" r="27" />
            <circle cx="518" cy="220" r="26" /><circle cx="464" cy="178" r="26" />
            <circle cx="384" cy="162" r="27" /><circle cx="310" cy="178" r="27" />
            <circle cx="256" cy="218" r="26" />
          </g>
          <!-- 高光层：树顶受光的那几团 -->
          <g fill="url(#wt-c3)" opacity=".85">
            <ellipse cx="308" cy="198" rx="92" ry="62" />
            <ellipse cx="420" cy="180" rx="84" ry="56" />
            <ellipse cx="252" cy="244" rx="66" ry="46" />
          </g>
          <ellipse cx="378" cy="336" rx="196" ry="76" fill="url(#wt-shade)" />
          <g fill="#d9eeba" opacity=".35">
            <circle cx="286" cy="160" r="8" /><circle cx="352" cy="140" r="7" />
            <circle cx="424" cy="158" r="8" /><circle cx="470" cy="214" r="7" />
            <circle cx="206" cy="268" r="7" /><circle cx="514" cy="238" r="6" />
          </g>
        </g>
      </g>
    </g>

    <!-- 果实 -->
    <g class="fruits">
      <g
        v-for="f in items"
        :key="f.code"
        class="fruit"
        :class="[f.status, { dim: selected && selected !== f.code, sel: selected === f.code }]"
        :transform="`translate(${f.x},${f.y})`"
        tabindex="0"
        role="button"
        :aria-label="`${f.name}，${f.score} 分，${f.statusLabel}`"
        @click="emit('select', f.code)"
        @keydown.enter.prevent="emit('select', f.code)"
        @keydown.space.prevent="emit('select', f.code)"
      >
        <g class="float" :style="{ animationDelay: f.delay }">
          <g class="zoom">
            <!-- 状态光环：不管用哪种配色，风险一眼可见 -->
            <circle class="halo" :r="f.r + 15" :fill="`url(#wt-halo-${f.status})`" />
            <circle v-if="selected === f.code" class="pick-ring" :r="f.r + 16" :stroke="f.ring" />
            <!-- 果实本体 -->
            <circle :r="f.r" :fill="`url(#wt-f-${f.code})`" class="body" />
            <ellipse :cx="-f.r * 0.34" :cy="-f.r * 0.42" :rx="f.r * 0.36" :ry="f.r * 0.22" fill="#fff" opacity=".52" />
            <circle :r="f.r" fill="none" stroke="#fffdf7" stroke-width="1" opacity=".35" />
            <circle :r="f.r" fill="none" :stroke="f.deep" stroke-width=".9" opacity=".3" />
            <!-- 果柄与小叶 -->
            <path :d="`M0 ${-f.r + 1} C 1 ${-f.r - 5} 3 ${-f.r - 8} 6 ${-f.r - 11}`"
              stroke="#7a5533" stroke-width="2.6" fill="none" stroke-linecap="round" />
            <path :d="`M6 ${-f.r - 10} C 14 ${-f.r - 16} 24 ${-f.r - 14} 26 ${-f.r - 8} C 20 ${-f.r - 4} 11 ${-f.r - 5} 6 ${-f.r - 10} Z`"
              fill="#6f9a5f" />
          </g>
        </g>
        <text class="f-name" :y="f.r + 21" text-anchor="middle">{{ f.label }}</text>
        <text class="f-sub" :y="f.r + 37" text-anchor="middle">
          <tspan :fill="f.ring">{{ f.score }} 分</tspan>
          <tspan class="f-dot"> · {{ f.credit }} 学分</tspan>
        </text>
      </g>
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
.halo {
  transform-box: fill-box;
  transform-origin: center;
  animation: wt-pulse 3.8s ease-in-out infinite;
}
.fruit.risk .halo {
  animation-duration: 2.2s;
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
}
.f-sub {
  font-size: 11px;
  fill: #7a6a58;
  paint-order: stroke;
  stroke: rgba(253, 248, 240, 0.94);
  stroke-width: 3.2px;
  stroke-linejoin: round;
  pointer-events: none;
}
.dust circle {
  opacity: 0.6;
  animation: wt-drift 12s ease-in-out infinite;
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
  .halo,
  .pick-ring,
  .dust circle {
    animation: none !important;
  }
}
</style>
