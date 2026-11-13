<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { PORTAL, buildNodes, isMainKey, polygonPoints, type PortalNode } from "@/config/portal";
import { api } from "@/api/client";
import { useChatStore } from "@/stores/chat";
import { useNoticeStore } from "@/stores/notices";
import type { PortalSummary, Role } from "@/types";

/**
 * 端口首屏。
 *
 * 一张纸：左边一句大字说清现在什么状况，右边把入口画成节点，最下面一条 AI。
 * 纸面上没有第二层底板——不描边、不套卡、不分栏，所有东西都直接落在同一张纸上，
 * 靠留白和字重分层次。整页只有两张「白卡」：消息卡和 AI 输入卡。
 */
const props = defineProps<{ role: Role; sid: string | null }>();

const router = useRouter();
const chat = useChatStore();
const notices = useNoticeStore();

const meta = computed(() => PORTAL[props.role] ?? PORTAL.student);
const nodes = computed(() => buildNodes(props.role));
const size = computed(() => {
  const n = nodes.value.length;
  if (n <= 3) return 112;
  if (n <= 6) return 104;
  if (n <= 9) return 96;
  return 88;
});

const ROLE_CN: Record<Role, string> = {
  student: "学生端",
  counselor: "辅导员端",
  admin: "教务端",
  teacher: "教师端",
  parent: "家长端",
};
const roleCn = computed(() => ROLE_CN[props.role] ?? ROLE_CN.student);
/** 小标题只要英文那一截（「STUDENT PORTAL / 我的学习空间」→「STUDENT PORTAL」） */
const kicker = computed(() => meta.value.kicker.split("/")[0].trim());

/** 节点里那行字要塞进多边形，节点越多字越小 */
const labelBase = computed(() => {
  const n = nodes.value.length;
  return n >= 10 ? 11 : n >= 7 ? 12 : 13;
});
/** 字多的再缩一档：宁可字小一点，也不要让笔画压到轮廓线上 */
function labelFont(n: PortalNode, main: boolean): number {
  const len = [...n.label].length;
  const base = labelBase.value + (main ? 0.5 : 0);
  // 中腰处的可用宽度：六边形左右是竖边，取七成宽给文字，斜边不压字
  const factor = 0.7;
  const fit = (size.value * factor) / (len * 1.04);
  return Math.max(8.5, Math.min(base, fit));
}

/* ---------------- 数字与消息卡 ---------------- */
const summary = ref<PortalSummary | null>(null);

async function loadSummary() {
  try {
    summary.value = await api.portalSummary();
  } catch {
    summary.value = null;
  }
}
onMounted(loadSummary);
watch(() => props.role, loadSummary);

const stats = computed(() => {
  const rows = summary.value?.stats ?? [];
  if (rows.length) return rows;
  return [
    { label: "个入口", value: nodes.value.length },
    { label: "项待办", value: notices.todoCount },
  ];
});

const focus = computed(() => summary.value?.focus ?? []);
const focusTitle = computed(() => summary.value?.focus_title || "优先处理");

/* ---------------- AI 那条 ---------------- */
const AI_COPY: Record<Role, { title: string; sub: string; hint: string }> = {
  student: {
    title: "这学期，我该先做什么?",
    sub: "问我哪门课还能救、怎么补，或者下一步怎么走",
    hint: "问点什么，比如「我高数还有机会及格吗」…",
  },
  counselor: {
    title: "这周，先找谁谈?",
    sub: "问我名单里谁最急、话怎么开、台账怎么记",
    hint: "问点什么，比如「本班谁的风险上升最快」…",
  },
  admin: {
    title: "这一周，先看哪个院?",
    sub: "问我全校分布、规则改动的影响、报表怎么导",
    hint: "问点什么，比如「哪个院红色预警最多」…",
  },
  parent: {
    title: "孩子这学期，先看什么?",
    sub: "问我成绩、状态，和学校什么时候会联系你",
    hint: "问点什么，比如「他这学期还来得及吗」…",
  },
  teacher: {
    title: "我这门课，先抓谁?",
    sub: "问我课上谁掉队、作业怎么收、建议怎么给",
    hint: "问点什么，比如「我课上谁最需要关注」…",
  },
};
const ai = computed(() => AI_COPY[props.role] ?? AI_COPY.student);
/**
 * 页脚那行小字：这个端口接的是哪只模型。
 * 作答模型 glm-5.3-flash 直接读后端 /meta，不写死——以前兜底是 "GLM-5.3"，
 * 后端没配 .env 时会露出模板默认的 gpt-4o-mini，和实际调用对不上。
 */
const modelLabel = computed(() => summary.value?.model || "glm-5.3-flash");
const modelRoute = computed(() => summary.value?.model_route || "glm-4.5-air");
/** 没配 key 时写明走规则兜底：徽标不能写「在线」而顶上黄条说「未接入」 */
const modelOnline = computed(() => summary.value?.model_online !== false);

/** 快捷问题直接用会话里那一组（后端给了就用后端的，没给就用各端默认） */
const chips = computed(() => (chat.suggestions ?? []).slice(0, 4));

/* ------------------------------------------------------------------
 * 拓扑：主链按编号连，旁支另外挑两对，再撒几条不连接任何节点的悬空弧。
 * ---------------------------------------------------------------- */
function curve(a: PortalNode, b: PortalNode, bend: number) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len;
  const ny = dx / len;
  const k = len * bend;
  const mx = (a.x + b.x) / 2 + nx * k;
  const my = (a.y + b.y) / 2 + ny * k;
  return {
    d: `M${a.x.toFixed(2)} ${a.y.toFixed(2)} Q${mx.toFixed(2)} ${my.toFixed(2)} ${b.x.toFixed(2)} ${b.y.toFixed(2)}`,
    // 二次贝塞尔 t=0.5 的位置：线上那几颗小赭点
    mx: (a.x + 2 * mx + b.x) / 4,
    my: (a.y + 2 * my + b.y) / 4,
  };
}

const chain = computed(() => {
  const out: { d: string; mx: number; my: number; i: number }[] = [];
  const bends = [0.14, -0.19, 0.21, -0.13, 0.16, -0.22, 0.11, -0.17, 0.2, -0.15];
  for (let i = 0; i < nodes.value.length - 1; i++) {
    const c = curve(nodes.value[i], nodes.value[i + 1], bends[i % bends.length]);
    out.push({ ...c, i });
  }
  return out;
});

const branches = computed(() => {
  const n = nodes.value;
  if (n.length === 3) return [{ ...curve(n[2], n[0], -0.24), i: 0 }];
  if (n.length < 5) return [];
  const pairs: [number, number][] = [
    [0, Math.min(3, n.length - 1)],
    [Math.max(0, n.length - 4), n.length - 1],
  ];
  if (n.length >= 9) pairs.push([1, Math.min(7, n.length - 1)]);
  return pairs
    .filter(([a, b]) => b - a > 1)
    .map(([a, b], i) => ({ ...curve(n[a], n[b], i % 2 ? -0.3 : 0.3), i }));
});

/** 串在线上的小赭点：隔一条放一颗，位置跟着线走 */
const seamDots = computed(() =>
  [...chain.value, ...branches.value]
    .filter((_, i) => i % 2 === 0)
    // 落在节点身上的点不要，会看成节点上的脏东西
    .filter((c) => !nodes.value.some((n) => Math.abs(n.x - c.mx) < 6.4 && Math.abs(n.y - c.my) < 9))
    .map((c, i) => ({ x: c.mx, y: c.my, i })),
);

/** 悬空铅笔弧：纯装饰，不连任何节点 */
const arcs = computed(() => [
  { d: "M3.5 44 Q11 37 20 45", i: 0 },
  { d: "M50 86 Q60 80 68 85", i: 1 },
  { d: "M46 11 Q56 6 65 12", i: 2 },
]);

/** 纸面上的细碎点，位置由角色名做种子，刷新不跳动 */
interface Speck {
  x: number;
  y: number;
  s: number;
  o: number;
  clay: boolean;
}
const specks = computed<Speck[]>(() => {
  let seed = 2166136261;
  for (const ch of `${props.role}-speck`) {
    seed = (seed ^ ch.charCodeAt(0)) >>> 0;
    seed = Math.imul(seed, 16777619) >>> 0;
  }
  const rnd = () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 4294967296;
  };
  return Array.from({ length: 34 }, (_, i) => ({
    x: 2 + rnd() * 96,
    y: 3 + rnd() * 94,
    s: 1.8 + rnd() * 2,
    o: 0.22 + rnd() * 0.3,
    clay: i % 4 === 0,
  }));
});

/** 所有节点共用同一枚尖顶六边形，这里按边数缓存一次算好的顶点串 */
const shapeCache = new Map<number, string>();
function points(sides: number): string {
  let p = shapeCache.get(sides);
  if (!p) {
    p = polygonPoints(sides);
    shapeCache.set(sides, p);
  }
  return p;
}

/** 实心节点：每端两处——AI 那个 + 最该看的那块 */
function isMain(n: PortalNode, i: number): boolean {
  return isMainKey(n.key, i);
}

function badgeOf(n: PortalNode): number {
  if (n.badge !== "messages") return 0;
  return notices.messageUnread;
}

function openAi() {
  chat.openAi();
}

function go(n: PortalNode) {
  if (n.act === "ai") {
    openAi();
    return;
  }
  if (!n.to) return;
  void router.push(n.to);
}

function askFocus(title: string) {
  if (!title) return;
  chat.ask(props.role, props.sid, title);
}

function askChip(q: string) {
  if (!q) return;
  chat.ask(props.role, props.sid, q);
}
</script>

<template>
  <section
    class="portal"
    :class="[`pt-${role}`, { 'pt-wide': nodes.length >= 9 }]"
    :style="{ '--nd': `${size}px` }"
    data-test="portal"
  >
    <!-- 纸面网格：细线几乎看不见，只提供纸的质感 -->
    <div class="pt-grid" aria-hidden="true"></div>

    <!-- 纸面上撒的点，不是星空，就是印上去的小墨点 -->
    <div class="pt-specks" aria-hidden="true">
      <i
        v-for="(s, i) in specks"
        :key="`sk-${i}`"
        :class="{ clay: s.clay }"
        :style="{ left: `${s.x}%`, top: `${s.y}%`, width: `${s.s}px`, height: `${s.s}px`, opacity: s.o }"
      ></i>
    </div>

    <!-- ============ 上半张：左边说话，右边画图 ============ -->
    <div class="pt-body">
      <aside class="pt-side">
        <p class="pt-kicker"><i aria-hidden="true"></i>{{ kicker }}</p>

        <h1 class="pt-hero">
          <span class="hero-lead">{{ meta.lead }}</span>
          <span class="hero-line"><template v-if="meta.mid">{{ meta.mid }}</template><em>{{ nodes.length }}</em>{{ meta.tail }}</span>
        </h1>

        <p class="pt-sub">{{ meta.sub }}</p>

        <p class="pt-stats">
          <template v-for="(s, i) in stats" :key="s.label">
            <i v-if="i" class="st-sep" aria-hidden="true"></i>
            <span class="st"><b>{{ s.value }}</b>{{ s.label }}</span>
          </template>
        </p>

        <!-- 消息卡：卡里只露两条，多的在卡内滚 -->
        <div v-if="focus.length" class="pt-focus" data-test="portal-focus">
          <div class="fx-head">
            <span class="fx-tag">{{ meta.focusTag }}</span>
            <span class="fx-title">{{ focusTitle }}</span>
          </div>
          <div class="fx-list">
            <button
              v-for="(f, i) in focus"
              :key="f.title + f.meta + i"
              class="fx-row"
              @click="askFocus(f.title)"
            >
              <span class="fx-k">{{ String(i + 1).padStart(2, "0") }}</span>
              <span class="fx-body">
                <b>{{ f.title }}</b>
                <i v-if="f.meta">{{ f.meta }}</i>
              </span>
            </button>
          </div>
        </div>
      </aside>

      <div class="pt-canvas">
        <p class="pt-micro">
          <span>PORTAL</span><i aria-hidden="true">·</i>{{ roleCn }}<i aria-hidden="true">·</i
          >{{ nodes.length }} 个入口<i aria-hidden="true">→</i>入场查看<i aria-hidden="true">·</i>每周一更新
        </p>

        <svg class="pt-edges" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <path
            v-for="c in arcs"
            :key="`arc-${c.i}`"
            :d="c.d"
            class="edge-arc"
            vector-effect="non-scaling-stroke"
          />
          <path
            v-for="b in branches"
            :key="`br-${b.i}`"
            :d="b.d"
            class="edge-branch"
            vector-effect="non-scaling-stroke"
          />
          <path
            v-for="c in chain"
            :key="`ch-${c.i}`"
            :d="c.d"
            class="edge-chain"
            vector-effect="non-scaling-stroke"
          />
        </svg>

        <div class="pt-field">
          <button
            v-for="(n, i) in nodes"
            :key="n.key"
            class="pt-node"
            :class="{ main: isMain(n, i) }"
            :style="{ left: `${n.x}%`, top: `${n.y}%` }"
            :title="n.note"
            :data-node="n.key"
            @click="go(n)"
          >
            <span class="nd-shape" :style="{ '--tilt': `${n.rot || 0}deg`, '--s': n.scale || 1 }">
              <svg viewBox="0 0 100 100" aria-hidden="true">
                <polygon v-if="n.sides" :points="points(n.sides)" />
                <circle v-else cx="50" cy="50" r="46" />
              </svg>
              <span class="nd-txt">
                <i class="nd-no">{{ n.no }}</i>
                <b
                  class="nd-label"
                  :style="{ fontSize: `${labelFont(n, isMain(n, i))}px` }"
                  >{{ n.label }}</b
                >
                <i class="nd-en">{{ n.en }}</i>
              </span>
              <span v-if="badgeOf(n)" class="nd-badge">{{ badgeOf(n) > 99 ? "99+" : badgeOf(n) }}</span>
            </span>
          </button>
        </div>

        <i v-for="d in seamDots" :key="`dot-${d.i}`" class="pt-dot" :style="{ left: `${d.x}%`, top: `${d.y}%` }" aria-hidden="true"></i>
      </div>
    </div>

    <!-- ============ 下沿：AI ============ -->
    <div class="pt-ai">
      <p class="ai-head">
        <i class="ai-dot" aria-hidden="true"></i>
        <b>学业守夜 AI</b>
        <span>能看你的全部学情数据，但只说给你听</span>
        <em :title="`作答 ${modelLabel} · 意图路由 ${modelRoute}${modelOnline ? '' : '（未配 key，当前规则兜底）'}`">作答 {{ modelLabel }} · 意图路由 {{ modelRoute }}</em>
      </p>

      <div class="ai-card">
        <span class="ai-ico" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="17" height="17">
            <circle cx="12" cy="12" r="4.2" fill="none" stroke="currentColor" stroke-width="1.4" />
            <g stroke="currentColor" stroke-width="1.4" stroke-linecap="round">
              <path d="M12 2.6v2.4M12 19v2.4M2.6 12h2.4M19 12h2.4" />
              <path d="M5.4 5.4 7 7M17 17l1.6 1.6M18.6 5.4 17 7M7 17l-1.6 1.6" />
            </g>
          </svg>
          <i class="ai-live" aria-hidden="true"></i>
        </span>

        <div class="ai-copy">
          <b>{{ ai.title }}</b>
          <span>{{ ai.sub }}</span>
        </div>

        <button class="ai-input" data-test="ai-dock" @click="openAi">
          <span class="ai-ph">{{ ai.hint }}</span>
          <kbd aria-hidden="true">/</kbd>
          <i class="ai-go" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="14" height="14">
              <path
                d="M4.5 12h14M13 6.5l5.5 5.5L13 17.5"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </i>
        </button>
      </div>

      <div v-if="chips.length" class="ai-chips">
        <button v-for="(q, i) in chips" :key="q" class="chip" @click="askChip(q)">
          <i aria-hidden="true">
            <svg v-if="i === 0" viewBox="0 0 12 12" width="9" height="9">
              <path d="M6 2v8M2 6h8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
            </svg>
            <svg v-else-if="i === 1" viewBox="0 0 12 12" width="9" height="9">
              <path d="M2 3.5h8M2 6h8M2 8.5h5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" />
            </svg>
            <svg v-else-if="i === 2" viewBox="0 0 12 12" width="9" height="9">
              <path
                d="M2.4 3.2h7.2v4.4H5.6L3.4 9.4V7.6H2.4z"
                fill="none"
                stroke="currentColor"
                stroke-width="1.1"
                stroke-linejoin="round"
              />
            </svg>
            <svg v-else viewBox="0 0 12 12" width="9" height="9">
              <circle cx="6" cy="6" r="3.6" fill="none" stroke="currentColor" stroke-width="1.2" />
              <path d="M6 4.2v2.2M6 7.9v.1" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" />
            </svg>
          </i>
          {{ q }}
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* ==========================================================================
   端口首屏 · 一张纸
   底是纸，字是墨，只有两条线：一条是墨绿，一条是陶土赭。
   ========================================================================== */
.portal {
  --moss: #16564a;
  --clay: #b4552d;
  --ink: #1f2a24;
  --ink-3: #7c8175;
  --rule: #e4dfd2;
  position: relative;
  display: flex;
  flex-direction: column;
  padding: 0 0 26px;
  background: transparent;
  isolation: isolate;
}

/* 40px 方格：细线 + 每五格一条略深的线 */
.pt-grid {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background-image:
    linear-gradient(to right, rgba(35, 38, 31, 0.028) 1px, transparent 1px),
    linear-gradient(to bottom, rgba(35, 38, 31, 0.028) 1px, transparent 1px),
    linear-gradient(to right, rgba(35, 38, 31, 0.045) 1px, transparent 1px),
    linear-gradient(to bottom, rgba(35, 38, 31, 0.045) 1px, transparent 1px);
  background-size: 8px 8px, 8px 8px, 40px 40px, 40px 40px;
  -webkit-mask-image: linear-gradient(to bottom, #000 0%, #000 82%, rgba(0, 0, 0, 0.72) 100%);
  mask-image: linear-gradient(to bottom, #000 0%, #000 82%, rgba(0, 0, 0, 0.72) 100%);
}

.pt-specks {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  overflow: hidden;
}
.pt-specks i {
  position: absolute;
  border-radius: 50%;
  background: #16564a;
  transform: translate(-50%, -50%);
}
.pt-specks i.clay {
  background: #b4552d;
  border-radius: 1px;
}

/* ==========================================================================
   上半张
   ========================================================================== */
.pt-body {
  position: relative;
  z-index: 3;
  flex: 1 1 auto;
  display: grid;
  grid-template-columns: minmax(268px, 30%) minmax(0, 1fr);
  gap: clamp(24px, 4vw, 64px);
  padding: clamp(26px, 3.4vw, 44px) clamp(20px, 3vw, 40px) 8px clamp(24px, 3.6vw, 56px);
  min-height: min(500px, 58vh);
}
/* 入口多的端（学生 11 个）把画布拉高一档，节点之间才留得出空档，
   不至于挤成一团；整页本来就是可滚的，多这一截不影响首屏。 */
.pt-wide .pt-body {
  min-height: min(640px, 76vh);
}

/* ---------- 左栏 ---------- */
.pt-side {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding-top: 6px;
}
.pt-kicker {
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 0;
  font-size: 9px;
  font-weight: 500;
  letter-spacing: 0.24em;
  color: #8d9187;
  text-transform: uppercase;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pt-kicker i {
  flex: none;
  width: 18px;
  height: 1px;
  background: #c9c6b8;
}

.pt-hero {
  margin: 20px 0 0;
  font-family: var(--serif);
  font-weight: 700;
  font-size: clamp(26px, 2.75vw, 39px);
  line-height: 1.42;
  letter-spacing: 0.015em;
  color: var(--ink);
}
.hero-lead,
.hero-line {
  display: block;
}
.pt-hero em {
  position: relative;
  font-style: normal;
  margin: 0 3px;
  font-size: 1.12em;
  font-weight: 700;
}
/* 数字底下压一道极淡的薄荷荧光，像用荧光笔划了一下 */
.pt-hero em::after {
  content: "";
  position: absolute;
  left: -3px;
  right: -3px;
  bottom: 0.08em;
  height: 0.52em;
  background: rgba(122, 176, 152, 0.22);
  border-radius: 2px;
  z-index: -1;
}

.pt-sub {
  margin: 14px 0 0;
  max-width: 34ch;
  font-size: 12px;
  line-height: 2;
  color: #858a7e;
}

.pt-stats {
  margin: 16px 0 0;
  display: flex;
  align-items: baseline;
  gap: 7px;
  font-size: 10.5px;
  color: #858a7e;
}
.pt-stats .st {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
}
.pt-stats b {
  font-family: var(--serif);
  font-size: 16px;
  font-weight: 700;
  color: #2c3a32;
  letter-spacing: 0.02em;
  font-variant-numeric: tabular-nums;
}
.st-sep {
  width: 2px;
  height: 2px;
  border-radius: 50%;
  background: #c3c1b4;
  align-self: center;
  margin: 0 2px;
}

/* ---------- 消息卡：只露两条 ---------- */
.pt-focus {
  margin-top: auto;
  margin-bottom: 6px;
  width: 100%;
  max-width: 330px;
  padding: 10px 0 6px;
  border: 1px solid #e7e2d4;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(35, 38, 31, 0.04), 0 8px 20px rgba(35, 38, 31, 0.045);
}
.fx-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px 8px;
}
.fx-tag {
  flex: none;
  padding: 1px 6px;
  border-radius: 3px;
  background: #f2e6d8;
  color: #8d4a2a;
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.04em;
  line-height: 1.55;
}
.fx-title {
  font-size: 10px;
  color: #9a9e93;
  letter-spacing: 0.02em;
}

/* 两行 = 2 × 44px，多出来的在卡里滚 */
.fx-list {
  max-height: 92px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: rgba(22, 86, 74, 0.28) transparent;
}
.fx-list::-webkit-scrollbar {
  width: 3px;
}
.fx-list::-webkit-scrollbar-thumb {
  background: rgba(22, 86, 74, 0.26);
  border-radius: 3px;
}
.fx-list::-webkit-scrollbar-track {
  background: transparent;
}
.fx-row {
  width: 100%;
  height: 46px;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 12px 0;
  border: 0;
  border-top: 1px dashed #e8e3d6;
  background: none;
  text-align: left;
}
.fx-row:first-child {
  border-top: 0;
}
.fx-k {
  flex: none;
  margin-top: 1px;
  font-family: var(--serif);
  font-size: 8.5px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: #b4b2a4;
  font-variant-numeric: tabular-nums;
}
.fx-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
  overflow: hidden;
}
.fx-body b {
  font-size: 11.5px;
  font-weight: 600;
  line-height: 1.5;
  color: #2c322c;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color 0.15s;
}
.fx-body i {
  font-style: normal;
  font-size: 9.5px;
  line-height: 1.5;
  color: #a3a79c;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.fx-row:hover .fx-body b {
  color: var(--moss);
}

/* ==========================================================================
   右半张：画布
   ========================================================================== */
.pt-canvas {
  position: relative;
  min-width: 0;
  min-height: 470px;
}
.pt-micro {
  position: absolute;
  top: 2px;
  right: 2px;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 8px;
  letter-spacing: 0.16em;
  color: #b0b1a5;
  text-transform: uppercase;
  white-space: nowrap;
}
.pt-micro span {
  color: #8d9187;
  letter-spacing: 0.2em;
}
.pt-micro i {
  font-style: normal;
  color: #cbc9bd;
  letter-spacing: 0;
}

.pt-edges {
  position: absolute;
  inset: 0;
  z-index: 2;
  width: 100%;
  height: 100%;
  pointer-events: none;
  overflow: visible;
}
.edge-chain {
  fill: none;
  stroke: rgba(22, 86, 74, 0.45);
  stroke-width: 1;
  stroke-dasharray: 2 4;
  stroke-linecap: round;
}
.edge-branch {
  fill: none;
  stroke: rgba(35, 38, 31, 0.16);
  stroke-width: 1;
  stroke-dasharray: 2 5;
}
.edge-arc {
  fill: none;
  stroke: rgba(35, 38, 31, 0.1);
  stroke-width: 1;
  stroke-dasharray: 1.5 5;
}

.pt-field {
  position: absolute;
  inset: 0;
  z-index: 3;
}

.pt-dot {
  position: absolute;
  z-index: 4;
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: #b4552d;
  transform: translate(-50%, -50%);
  box-shadow: 0 0 0 1.5px rgba(180, 85, 45, 0.12);
}

/* ---------- 节点 ---------- */
.pt-node {
  position: absolute;
  transform: translate(-50%, -50%);
  width: calc(var(--nd, 64px) * 1.34);
  padding: 0;
  border: 0;
  background: none;
  /* 按钮默认 overflow:hidden，实心节点放大 1.28 倍后上下尖角会被切掉，
     看着像八边形——必须放开 */
  overflow: visible;
  transition: transform 0.18s ease;
}
.pt-node:hover,
.pt-node:focus-visible {
  transform: translate(-50%, -50%) translateY(-2px);
  outline: none;
}
.nd-shape {
  position: relative;
  display: grid;
  place-items: center;
  width: var(--nd, 64px);
  height: var(--nd, 64px);
  margin: 0 auto;
  transform: rotate(var(--tilt, 0deg)) scale(var(--s, 1));
  transition: transform 0.18s ease;
}
.nd-shape svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  overflow: visible;
}
.nd-shape polygon,
.nd-shape circle {
  fill: #fffdf7;
  stroke: rgba(22, 86, 74, 0.55);
  stroke-width: 1.25;
  stroke-linejoin: round;
  transition: fill 0.18s ease, stroke 0.18s ease;
}

/* 字塞在多边形里：编号 / 名字 / 英文，三层都居中 */
.nd-txt {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  width: 74%;
  transform: rotate(calc(-1 * var(--tilt, 0deg)));
  text-align: center;
  line-height: 1.25;
}
.nd-no {
  font-style: normal;
  font-family: var(--serif);
  font-size: 8.5px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: #9aa196;
  font-variant-numeric: tabular-nums;
}
.nd-label {
  font-size: var(--lf, 9.5px);
  font-weight: 600;
  letter-spacing: 0.01em;
  color: #26332b;
  word-break: break-all;
  transition: color 0.18s ease;
}
.nd-en {
  font-style: normal;
  font-size: 7px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #a8ab9f;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

/* 实心节点：墨绿底、纸色字。
   体量比描边节点大 28%——重点靠大小说话，不靠加深颜色：深色已经够重，
   再压暗就和纸面脱开了，看起来会突兀。 */
.pt-node.main .nd-shape {
  transform: rotate(var(--tilt, 0deg)) scale(calc(var(--s, 1) * 1.28));
}
.pt-node.main:hover .nd-shape,
.pt-node.main:focus-visible .nd-shape {
  transform: rotate(0deg) scale(calc(var(--s, 1) * 1.34));
}
.pt-node.main .nd-shape polygon,
.pt-node.main .nd-shape circle {
  fill: var(--moss);
  stroke: var(--moss);
}
.pt-node.main .nd-label {
  color: #f6f3e9;
  letter-spacing: 0;
}
.pt-node.main .nd-no {
  font-size: 9px;
}
.pt-node.main .nd-en {
  font-size: 7.5px;
}
.pt-node.main .nd-no {
  color: rgba(246, 243, 233, 0.62);
}
.pt-node.main .nd-en {
  color: rgba(246, 243, 233, 0.5);
}

.pt-node:hover .nd-shape polygon,
.pt-node:hover .nd-shape circle,
.pt-node:focus-visible .nd-shape polygon,
.pt-node:focus-visible .nd-shape circle {
  fill: var(--moss);
  stroke: var(--moss);
}
.pt-node:hover .nd-label,
.pt-node:focus-visible .nd-label {
  color: #f6f3e9;
}
.pt-node:hover .nd-no,
.pt-node:focus-visible .nd-no {
  color: rgba(246, 243, 233, 0.62);
}
.pt-node:hover .nd-en,
.pt-node:focus-visible .nd-en {
  color: rgba(246, 243, 233, 0.5);
}
.pt-node:hover .nd-shape,
.pt-node:focus-visible .nd-shape {
  transform: rotate(0deg) scale(calc(var(--s, 1) * 1.04));
}

/* 未读数：右上角一颗赭色小方块，不是红点 */
.nd-badge {
  position: absolute;
  top: -2px;
  right: 2px;
  min-width: 15px;
  height: 15px;
  padding: 0 3px;
  display: grid;
  place-items: center;
  border-radius: 2.5px;
  background: #b4552d;
  color: #fff;
  font-size: 9px;
  font-weight: 600;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  transform: rotate(calc(-1 * var(--tilt, 0deg)));
  box-shadow: 0 1px 2px rgba(180, 85, 45, 0.35);
}

/* ==========================================================================
   下沿：AI
   ========================================================================== */
.pt-ai {
  position: relative;
  z-index: 5;
  flex: none;
  padding: 26px clamp(20px, 3vw, 40px) 0 clamp(24px, 3.6vw, 56px);
}
.ai-head {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0 0 9px;
  font-size: 9.5px;
  color: #a4a89c;
}
.ai-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--moss);
  box-shadow: 0 0 0 3px rgba(22, 86, 74, 0.1);
}
.ai-head b {
  font-size: 10px;
  font-weight: 600;
  color: #3d4a42;
  letter-spacing: 0.02em;
}
.ai-head span {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ai-head em {
  flex: none;
  font-style: normal;
  font-size: 8.5px;
  letter-spacing: 0.06em;
  color: #b6b8ac;
  /* 模型 id 是「glm-5.3-flash」这种小写写法，不再转大写：
     转大写会显示成 GLM-5.3-FLASH，和接口里返回的名字对不上 */
}

.ai-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 13px 13px;
  border-radius: 12px;
  border: 1px solid #ebe6d8;
  background: #fff;
  box-shadow: 0 1px 2px rgba(35, 38, 31, 0.04), 0 10px 24px rgba(35, 38, 31, 0.05);
}
.ai-ico {
  position: relative;
  flex: none;
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: #e7efe8;
  color: #3c6b58;
}
.ai-live {
  position: absolute;
  top: -1px;
  right: -1px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #5a9a72;
  box-shadow: 0 0 0 2px #fff;
}
.ai-copy {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: clamp(180px, 20vw, 250px);
  min-width: 0;
}
.ai-copy b {
  font-size: 12.5px;
  font-weight: 600;
  color: #232c26;
  letter-spacing: 0.01em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ai-copy span {
  font-size: 9.5px;
  color: #a5a89d;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 输入条：整条是一个按钮，点一下展开对话 */
.ai-input {
  flex: 1;
  min-width: 0;
  height: 38px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 5px 0 15px;
  border: 1px solid #ece7d9;
  border-radius: 999px;
  background: #fdfdfa;
  text-align: left;
  transition: border-color 0.16s ease, background 0.16s ease;
}
.ai-input:hover {
  border-color: #d9d3c2;
  background: #fff;
}
.ai-ph {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: #a9aca1;
}
.ai-input kbd {
  flex: none;
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  border: 1px solid #eee9db;
  border-radius: 5px;
  background: #fff;
  font-family: inherit;
  font-size: 9px;
  color: #b8bbaf;
}
.ai-go {
  flex: none;
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  background: var(--moss);
  color: #f7f4ea;
  transition: background 0.16s ease;
}
.ai-input:hover .ai-go {
  background: #0f4038;
}

/* 快捷问题：纸面上的小胶囊 */
.ai-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 10px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 22px;
  padding: 0 9px;
  border: 1px solid #e9e4d6;
  border-radius: 999px;
  background: #fff;
  color: #6b7169;
  font-size: 9.5px;
  letter-spacing: 0.01em;
  white-space: nowrap;
  transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}
.chip i {
  display: grid;
  place-items: center;
  color: #a9ada2;
}
.chip:hover {
  border-color: #cdd8ce;
  color: var(--moss);
  background: #fbfdfb;
}
.chip:hover i {
  color: var(--moss);
}

/* ==========================================================================
   窄屏
   ========================================================================== */
@media (max-width: 1180px) {
  .pt-body {
    grid-template-columns: minmax(240px, 34%) minmax(0, 1fr);
    gap: 26px;
  }
  .pt-hero {
    font-size: clamp(23px, 2.5vw, 28px);
  }
  .ai-copy {
    width: 190px;
  }
}

/* 一列：字 → 图 → 卡 → AI */
@media (max-width: 900px) {
  .portal {
    min-height: 0;
  }
  .pt-body {
    grid-template-columns: minmax(0, 1fr);
    gap: 18px;
    min-height: 0;
    padding: 22px 18px 6px;
  }
  .pt-side {
    padding-top: 0;
  }
  .pt-hero {
    margin-top: 14px;
    font-size: clamp(23px, 5vw, 30px);
  }
  .pt-sub {
    max-width: none;
  }
  .pt-focus {
    margin: 20px 0 0;
    max-width: none;
    order: 3;
  }
  .pt-canvas {
    min-height: 420px;
    order: 2;
  }
  .pt-ai {
    padding: 20px 18px 4px;
  }
  .ai-card {
    flex-wrap: wrap;
    gap: 10px;
  }
  .ai-copy {
    width: auto;
    flex: 1;
  }
  .ai-input {
    flex: 1 0 100%;
  }
}

@media (max-width: 620px) {
  /* 两列网格按内容长高：这里不能压 min-height:0，否则行高被判成 0，节点会糊到 AI 条上 */
  .pt-canvas {
    min-height: auto;
  }
  .pt-micro,
  .pt-edges,
  .pt-dot {
    display: none;
  }
  .pt-field {
    position: relative;
    inset: auto;
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px 4px;
  }
  .pt-node {
    position: static;
    transform: none;
    width: 100%;
  }
  .pt-node:hover,
  .pt-node:focus-visible {
    transform: translateY(-2px);
  }
  .nd-shape {
    width: 84px;
    height: 84px;
  }
  /* 六字标签在手机上也要一行放得下，宁可把节点做大一点 */
  .nd-label {
    font-size: 10.5px;
    line-height: 1.15;
  }
  .ai-head span {
    display: none;
  }
  .ai-head em {
    margin-left: auto;
  }
}

@media (prefers-reduced-motion: reduce) {
  .pt-node,
  .nd-shape,
  .ai-input,
  .chip {
    transition: none;
  }
}
</style>
