<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client";
import ActionList from "@/components/ActionList.vue";
import RegionBand from "@/components/RegionBand.vue";
import WisdomTree from "@/components/WisdomTree.vue";
import { useAuthStore } from "@/stores/auth";
import { useChatStore } from "@/stores/chat";
import type {
  AttendanceRecord,
  CourseTrend,
  FruitLedger,
  HomeworkRecord,
  StudentDetail,
  TreeFruit,
} from "@/types";

/**
 * 我的智慧树。
 * 一颗苹果一门课：颜色＝学期作业完成度（青→黄→红），大小＝学分×施肥成熟度。
 *
 * 这一页的树是**亲手养出来的**：仓库里攒着水（到课挣的）和肥（作业挣的），
 * 点一袋施一袋——浇水树当场长个子（苗→树，干和冠各长各的），施肥苹果当场变大；
 * 补交一次作业，仓库就多一袋肥。施完为止，一键全施可以快进。
 */
const auth = useAuthStore();
const chat = useChatStore();
const router = useRouter();
const sid = computed(() => auth.profile?.sid || "");

const detail = ref<StudentDetail | null>(null);
const loading = ref(true);
const error = ref("");
const selected = ref<string | null>(null);

async function load() {
  if (!sid.value) return;
  loading.value = true;
  error.value = "";
  try {
    detail.value = await api.student(sid.value);
    if (!selected.value) selected.value = worst.value?.code || detail.value.courses[0]?.code || null;
  } catch (e: any) {
    error.value = e?.message || "加载失败";
  } finally {
    loading.value = false;
  }
}
watch(() => sid.value, () => load(), { immediate: true });

function statusOf(score: number): TreeFruit["status"] {
  if (score < 60) return "risk";
  if (score < 70) return "watch";
  if (score >= 85) return "great";
  return "ok";
}

/* ------------------------------------------------------------------ */
/* 水肥账：到课是水，作业是肥                                          */
/* 水决定树干长多粗，肥决定果实长多大，两件事不能互相替代              */
/* ------------------------------------------------------------------ */

/** 作业质量系数：按时 1.0 / 迟交 0.6 / 缺交 0；提前 24 小时以上交算 1.1 */
function hwQuality(h: HomeworkRecord): number {
  if (h.status === "missing") return 0;
  if (h.status === "late") return 0.6;
  const due = Date.parse(h.due);
  const sub = Date.parse(h.submitted_at || "");
  if (Number.isFinite(due) && Number.isFinite(sub) && due - sub >= 86400000) return 1.1;
  return 1;
}

/** 肥账：只算已经截止的作业，还没到期的不算欠 */
function hwLedger(rows: HomeworkRecord[] | undefined): FruitLedger | null {
  const all = rows || [];
  if (!all.length) return null;
  const now = Date.now();
  const due = all.filter((h) => Number.isFinite(Date.parse(h.due)) && Date.parse(h.due) <= now);
  const n = due.length;
  const done = due.filter((h) => h.status !== "missing").length;
  const eff = due.reduce((s, h) => s + hwQuality(h), 0);
  return { due: n, done, rate: n ? Math.min(1, done / n) : 0, eff };
}

/** 水账：到课 1 节算 1，迟到算半次，旷课不浇 */
function attLedger(rows: AttendanceRecord[] | undefined): FruitLedger {
  const all = rows || [];
  const n = all.length;
  const done = all.filter((a) => a.status !== "absent").length;
  const eff = all.reduce((s, a) => s + (a.status === "present" ? 1 : a.status === "late" ? 0.5 : 0), 0);
  return { due: n, done, rate: n ? eff / n : 0, eff };
}

/**
 * 成熟度 0.45–1.0。
 * 分母用**真实已截止次数**，不做次数平滑：作业留得少的课（思政只留 3 次思考题）
 * 交齐了就该熟，不然"作业少"反而变成它长不大的理由 —— 这正是要避开的不公平。
 * 每门课各自跟自己比完成率，不跨课比绝对次数：次数只决定"分几口吃"，完成率决定"吃到几成"。
 */
function maturityOf(hw: FruitLedger | null, att: FruitLedger): number {
  if (hw && hw.due > 0) {
    return 0.45 + 0.55 * Math.min(1, hw.eff / hw.due);
  }
  // 该课没有作业 / 还没有到期作业：改按到课折算，标签写"按到课计"
  return 0.45 + 0.55 * att.rate;
}

/** 每门课一行"树上用的数"：最近一次测评 = 期中，风险概率来自风险引擎 */
const rows = computed(() => {
  const d = detail.value;
  if (!d) return [];
  const failOf = (code: string) => d.risk.pass_probability.find((p) => p.code === code)?.fail_probability ?? 0;
  const trendOf = (code: string) => d.grade_trend?.courses.find((c) => c.code === code);
  return d.courses.map((c) => {
    const t: CourseTrend | undefined = trendOf(c.code);
    const last = t?.points.length ? t.points[t.points.length - 1].score : c.midterm;
    const fail = failOf(c.code);
    const hw = hwLedger(c.homework);
    const attend = attLedger(c.attendance);
    return {
      code: c.code,
      name: c.name,
      teacher: c.teacher,
      credit: c.credit,
      score: Math.round(last),
      midterm: c.midterm,
      cohort: t?.cohort_avg ?? null,
      delta: t?.delta ?? 0,
      points: t?.points ?? [],
      fail,
      status: statusOf(last),
      hw,
      attend,
      maturity: maturityOf(hw, attend),
    };
  });
});

const fruits = computed<TreeFruit[]>(() =>
  rows.value.map((r, i) => ({
    code: r.code,
    name: r.name,
    credit: r.credit,
    score: r.score,
    fail: r.fail,
    status: r.status,
    slot: i,
    maturity: r.maturity,
    hw: r.hw,
    attend: r.attend,
    leaves: r.credit,
  })),
);

/** 全学期的水：有效到课 ÷ 应到节数 */
const water = computed(() => {
  const due = rows.value.reduce((s, r) => s + r.attend.due, 0);
  const eff = rows.value.reduce((s, r) => s + r.attend.eff, 0);
  return { due, eff, rate: due ? eff / due : 1 };
});

/** 全学期的肥：按实际分母算的真实交付率 */
const fert = computed(() => {
  const due = rows.value.reduce((s, r) => s + (r.hw?.due || 0), 0);
  const done = rows.value.reduce((s, r) => s + (r.hw?.done || 0), 0);
  return { due, done, rate: due ? Math.min(1, done / due) : 1 };
});

/** 学期第一周的周一：从考勤记录反推，不写死日期 */
function mondayMs(dateStr: string): number {
  const d = new Date(`${dateStr}T00:00:00`);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return d.getTime();
}
const week1Ms = computed(() => {
  let best = Infinity;
  for (const c of detail.value?.courses || []) {
    for (const a of c.attendance || []) {
      const w1 = mondayMs(a.date) - (a.week - 1) * 604800000;
      if (w1 < best) best = w1;
    }
  }
  return Number.isFinite(best) ? best : mondayMs("2026-08-31");
});
function weekOfDate(dateStr: string): number {
  return Math.floor((mondayMs(dateStr) - week1Ms.value) / 604800000) + 1;
}

/** 最近一周的结算：水还差几次，肥还差几次 */
const settle = computed(() => {
  const cs = detail.value?.courses || [];
  let wk = 0;
  for (const c of cs) for (const a of c.attendance || []) wk = Math.max(wk, a.week);
  if (!wk) return null;
  let aDue = 0;
  let aDone = 0;
  for (const c of cs) {
    for (const a of c.attendance || []) {
      if (a.week !== wk) continue;
      aDue += 1;
      if (a.status !== "absent") aDone += 1;
    }
  }
  let hDue = 0;
  let hDone = 0;
  for (const c of cs) {
    for (const h of c.homework || []) {
      if (weekOfDate(h.due) !== wk) continue;
      hDue += 1;
      if (h.status !== "missing") hDone += 1;
    }
  }
  return {
    week: wk,
    water: { due: aDue, done: aDone, gap: aDue - aDone },
    fert: { due: hDue, done: hDone, gap: hDue - hDone },
  };
});

const worst = computed(() => {
  const list = [...rows.value].sort((a, b) => b.fail - a.fail || a.score - b.score);
  return list[0];
});

const current = computed(() => rows.value.find((r) => r.code === selected.value) || rows.value[0] || null);

const counts = computed(() => ({
  risk: rows.value.filter((r) => r.status === "risk").length,
  watch: rows.value.filter((r) => r.status === "watch").length,
  ok: rows.value.filter((r) => r.status === "ok" || r.status === "great").length,
}));

const avg = computed(() => {
  if (!rows.value.length) return 0;
  const credits = rows.value.reduce((s, r) => s + (r.credit || 0), 0) || 1;
  return Math.round(rows.value.reduce((s, r) => s + r.score * (r.credit || 0), 0) / credits);
});

/** 风险引擎口径：按出勤与作业算出来的挂科概率（和果实颜色是两套口径，要说清） */
const highRisk = computed(() => rows.value.filter((r) => r.fail >= 0.6));

const summary = computed(() => {
  if (!rows.value.length) return "";
  const w = worst.value;
  const wf = `这棵树是这么长起来的：水＝到课 ${Math.round(water.value.rate * 100)}%（树形），肥＝作业 ${Math.round(fert.value.rate * 100)}%（苹果大小）——苹果颜色看作业完成度：青（没过半）→黄（过半）→红（全交）。`;
  if (counts.value.risk) {
    return `${wf}树上有 ${counts.value.risk} 颗挂着红色风险光环，最急的是《${w.name}》（${w.score} 分）。一门课挂科就够影响学分，现在补成本最低。`;
  }
  if (highRisk.value.length) {
    const h = [...highRisk.value].sort((a, b) => b.fail - a.fail)[0];
    return `${wf}光环还都安分，但按出勤和作业算，有 ${highRisk.value.length} 门课的挂科概率超过 60%——最高的是《${h.name}》（${Math.round(h.fail * 100)}%）。分数在面板里，出勤和作业才是它的根。`;
  }
  if (counts.value.watch) {
    return `${wf}没有红色风险光环，但有 ${counts.value.watch} 颗亮着临界光环，《${w.name}》最需要盯一下。现在动手，期末大概率不用过这根线。`;
  }
  return `${wf}${rows.value.length} 颗苹果都没挂风险光环，学分加权均分 ${avg.value}。保持这个节奏，重点是别让任何一门掉出安全区。`;
});

/**
 * 苹果颜色 = 学期作业完成度（已施袋数 ÷ 作业总次数）：
 * 靝（<50%）→ 黄（过半）→ 红（全交）。无作业的课跟着水长。
 * 页面上的小色点、图例用的也是这三色。
 */
const APPLE_MID = ["#7fc062", "#f0c23e", "#e2503f"];
function ripeRatioOf(code: string, hw: FruitLedger | null): number {
  if (hw && hw.due > 0) return Math.min(1, fertAppliedOf(code) / hw.due);
  return waterFrac.value;
}
function appleColorOf(r: { code: string; hw: FruitLedger | null }): string {
  const p = ripeRatioOf(r.code, r.hw);
  return APPLE_MID[p >= 1 ? 2 : p >= 0.5 ? 1 : 0];
}
/** 传给树的完成度表：树按它决定每颗苹果的颜色 */
const ripe = computed(() => {
  const out: Record<string, number> = {};
  for (const r of rows.value) out[r.code] = ripeRatioOf(r.code, r.hw);
  return out;
});
const STATUS_COLOR: Record<string, string> = {
  great: "#2f8f6b",
  ok: "#46a06a",
  watch: "#e0a02c",
  risk: "#d9483b",
};
const STATUS_LABEL: Record<string, string> = {
  great: "很稳",
  ok: "较稳",
  watch: "临界",
  risk: "不及格",
};

function goSimulate(code?: string) {
  router.push({ path: "/student/simulate", query: code ? { course: code } : {} });
}
function askAi(name: string) {
  chat.ask("student", sid.value || null, `《${name}》这颗苹果为什么还没红透？是哪项作业拖了后腿，我该怎么补？`);
  router.push("/student");
}

/* ------------------------------------------------------------------ */
/* 资源仓库：水和肥一袋袋施下去，树当场长                              */
/* ------------------------------------------------------------------ */

const REDUCE =
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const treeRef = ref<InstanceType<typeof WisdomTree> | null>(null);
const waterStockEl = ref<HTMLElement | null>(null);
/** 肥料袋按钮的位置：用 data-stock 属性现查，不用函数 ref（回调里写响应式状态会自触发渲染死循环） */
function fertStockElOf(code: string): HTMLElement | null {
  return document.querySelector<HTMLElement>(`.yard [data-stock="${CSS.escape(code)}"]`);
}

/** 已施下去的量 */
const waterApplied = ref(0);
const fertApplied = ref<Record<string, number>>({});
/** 飞在半空还没落地的袋数：先占位，防止连点超发 */
const pendingW = ref(0);
const pendingF = ref<Record<string, number>>({});
/** 补交挣来的额外肥袋 */
const extraFert = ref<Record<string, number>>({});
/** 一键全施进行中 */
const busy = ref(false);
/** 补交后仓库里那袋闪一下 */
const popStock = ref<string | null>(null);

/**
 * 水壶数：每壶 ≈ 7 节课的到课量，控制在 5–12 壶之间。
 * 一壶浇下去树干要看得见地粗一圈，太少没反馈，太多点不动。
 */
const waterBags = computed(() => Math.max(5, Math.min(12, Math.round(water.value.eff / 7) || 0)));

/** 该课仓库里的肥袋数 = 已交作业次数（每次作业一袋）+ 补交挣的 */
function fertBagsOf(code: string): number {
  const r = rows.value.find((x) => x.code === code);
  return (r?.hw?.done ?? 0) + (extraFert.value[code] || 0);
}
function fertAppliedOf(code: string): number {
  return fertApplied.value[code] || 0;
}
function fertPendingOf(code: string): number {
  return pendingF.value[code] || 0;
}
function fertLeftOf(code: string): number {
  return Math.max(0, fertBagsOf(code) - fertAppliedOf(code) - fertPendingOf(code));
}

const waterLeft = computed(() => Math.max(0, waterBags.value - waterApplied.value - pendingW.value));
const totalLeft = computed(() => {
  let n = waterLeft.value;
  for (const r of rows.value) n += fertLeftOf(r.code);
  return n;
});

/** 传给树的施肥进度：0 是青果，1 长到该课成熟度 */
const fertFrac = computed(() => {
  const out: Record<string, number> = {};
  for (const r of rows.value) {
    const base = r.hw?.done ?? 0;
    const applied = fertAppliedOf(r.code);
    // 作业一次没交的课：一袋就是一步，补交一袋就能把它从青果拉起来
    out[r.code] = base > 0 ? Math.min(1, applied / base) : Math.min(1, applied);
  }
  return out;
});

/** 补交挣的额外袋：每施一袋，果子再饱满一小圈（上限 3 袋） */
const fertBonus = computed(() => {
  const out: Record<string, number> = {};
  for (const r of rows.value) {
    const base = r.hw?.done ?? 0;
    out[r.code] = Math.max(0, fertAppliedOf(r.code) - base);
  }
  return out;
});

const waterFrac = computed(() => (waterBags.value ? Math.min(1, waterApplied.value / waterBags.value) : 0));

function wait(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

/** 袋子从仓库飞到树上的落点 */
function flyBag(
  kind: "water" | "fert",
  from: DOMRect | undefined,
  to: { x: number; y: number } | null,
): Promise<void> {
  return new Promise((resolve) => {
    if (REDUCE || !from || !to || typeof document === "undefined") {
      resolve();
      return;
    }
    const el = document.createElement("div");
    el.className = `fly-bag ${kind}`;
    el.innerHTML =
      kind === "water"
        ? `<svg viewBox="0 0 36 36" width="36" height="36"><path d="M18 4c5.2 6.2 9 10.8 9 15A9 9 0 0 1 9 19c0-4.2 3.8-8.8 9-15z" fill="#6aa9dd"/><path d="M13.6 19.4a3.4 3.4 0 0 0 2.6 3.3" stroke="#fff" stroke-width="1.8" fill="none" stroke-linecap="round"/></svg>`
        : `<svg viewBox="0 0 36 36" width="36" height="36"><path d="M12 11c0-3 2.7-5.4 6-5.4S24 8 24 11l2.2 13.2A3.8 3.8 0 0 1 22.4 29h-8.8a3.8 3.8 0 0 1-3.8-4.8z" fill="#c98d4e"/><path d="M13.4 10.6c2.7 1.5 6.5 1.5 9.2 0" stroke="#8a5c2e" stroke-width="1.8" fill="none" stroke-linecap="round"/><path d="M18 5.6V10" stroke="#7da05c" stroke-width="2" stroke-linecap="round"/></svg>`;
    document.body.appendChild(el);
    const x0 = from.left + from.width / 2 - 18;
    const y0 = from.top + from.height / 2 - 18;
    const x1 = to.x - 18;
    const y1 = to.y - 18;
    const anim = el.animate(
      [
        { transform: `translate(${x0}px,${y0}px) scale(.85) rotate(-10deg)`, opacity: 1 },
        {
          transform: `translate(${(x0 + x1) / 2}px,${Math.min(y0, y1) - 48}px) scale(1.08) rotate(8deg)`,
          opacity: 1,
          offset: 0.55,
        },
        { transform: `translate(${x1}px,${y1}px) scale(.5) rotate(14deg)`, opacity: 0.2 },
      ],
      { duration: 560, easing: "cubic-bezier(.32,.72,.36,1)" },
    );
    anim.onfinish = () => {
      el.remove();
      resolve();
    };
    // 兜底：个别环境下 onfinish 不触发也别把流程卡死
    setTimeout(() => {
      el.remove();
      resolve();
    }, 900);
  });
}

/** 浇一壶水：袋子飞到树根 → 水花 → 树干当场粗一点 */
async function applyWater() {
  if (busy.value || waterLeft.value <= 0) return;
  pendingW.value++;
  const from = waterStockEl.value?.getBoundingClientRect();
  const to = treeRef.value?.getTrunkPos() ?? null;
  await flyBag("water", from, to);
  pendingW.value = Math.max(0, pendingW.value - 1);
  waterApplied.value++;
  treeRef.value?.splashWater();
}

/** 施一袋肥：袋子飞到那颗果 → 光晕炸开 → 果子当场大一圈 */
async function applyFert(code: string) {
  if (busy.value || fertLeftOf(code) <= 0) return;
  pendingF.value = { ...pendingF.value, [code]: fertPendingOf(code) + 1 };
  const from = fertStockElOf(code)?.getBoundingClientRect();
  const to = treeRef.value?.getFruitPos(code) ?? treeRef.value?.getTrunkPos() ?? null;
  await flyBag("fert", from, to);
  pendingF.value = { ...pendingF.value, [code]: Math.max(0, fertPendingOf(code) - 1) };
  fertApplied.value = { ...fertApplied.value, [code]: fertAppliedOf(code) + 1 };
  treeRef.value?.popFruit(code);
}

/** 补交一次作业：仓库当场多一袋肥（点它施下去，果子再饱满一圈） */
function addFertBag(code: string) {
  const r = rows.value.find((x) => x.code === code);
  if (!r?.hw) return;
  if (fertBagsOf(code) >= r.hw.due) return;
  extraFert.value = { ...extraFert.value, [code]: (extraFert.value[code] || 0) + 1 };
  popStock.value = code;
  window.setTimeout(() => {
    if (popStock.value === code) popStock.value = null;
  }, 720);
}

/** 一键全施：像延时摄影一样把剩下的水肥全部施完 */
async function autoApply() {
  if (busy.value || totalLeft.value <= 0) return;
  busy.value = true;
  try {
    while (waterLeft.value > 0) {
      waterApplied.value++;
      treeRef.value?.splashWater();
      await wait(REDUCE ? 0 : 150);
    }
    for (const r of rows.value) {
      while (fertLeftOf(r.code) > 0) {
        fertApplied.value = { ...fertApplied.value, [r.code]: fertAppliedOf(r.code) + 1 };
        treeRef.value?.popFruit(r.code);
        await wait(REDUCE ? 0 : 150);
      }
    }
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="page">
    <div v-if="loading && !detail" class="card"><div class="skeleton" style="height: 380px"></div></div>

    <div v-else-if="error" class="card">
      <b>加载失败</b>
      <p class="tiny muted">{{ error }}</p>
      <button class="btn" @click="load">重试</button>
    </div>

    <template v-else>
      <RegionBand no="01" title="我的智慧树" tone="learn"
        :desc="`${detail?.student.term || ''} · ${rows.length} 门课 · 浇水＝到课（长树），施肥＝作业（长苹果）——青→黄→红是作业完成度，点仓库里的袋子一袋袋养出来`" />

      <div class="card tree-card">
        <div class="tree-grid">
          <div class="tree-stage">
            <WisdomTree
              ref="treeRef"
              :fruits="fruits"
              :selected="selected"
              :water-rate="water.rate"
              :water-count="Math.round(water.eff)"
              :water-frac="waterFrac"
              :fert-frac="fertFrac"
              :fert-bonus="fertBonus"
              :ripe="ripe"
              @select="selected = $event"
            />

            <!-- 资源仓库：水和肥都在这儿，点一袋施一袋 -->
            <div class="yard">
              <div class="yard-cap">
                <b>资源仓库</b>
                <em>点袋子 → 飞到树上 → 当场长大；补交作业会多一袋肥</em>
              </div>

              <div class="yard-grid">
                <button
                  ref="waterStockEl"
                  class="stock"
                  :class="{ 'stock-pop': false, empty: !waterLeft }"
                  :disabled="!waterLeft || busy"
                  @click="applyWater()"
                >
                  <svg class="bag-ic" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M12 2.5c4 5 7 8.6 7 11.6a7 7 0 1 1-14 0c0-3 3-6.6 7-11.6z" fill="#6aa9dd" />
                    <path d="M8.8 14.2a2.9 2.9 0 0 0 2.2 2.8" stroke="#fff" stroke-width="1.5" fill="none" stroke-linecap="round" />
                  </svg>
                  <span class="stock-body">
                    <b>水 ×{{ waterBags }}</b>
                    <em>已浇 {{ waterApplied }}/{{ waterBags }} 壶 · 每壶 ≈ 7 节课</em>
                  </span>
                  <span class="stock-act">{{ waterLeft ? "浇水" : "浇完" }}</span>
                </button>

                <button
                  v-for="r in rows"
                  :key="r.code"
                  class="stock"
                  :class="{ 'stock-pop': popStock === r.code, empty: !fertLeftOf(r.code) }"
                  :disabled="!fertLeftOf(r.code) || busy"
                  :data-stock="r.code"
                  @click="applyFert(r.code)"
                >
                  <svg class="bag-ic" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M8 7.2c0-2.4 2.2-4.2 4.8-4.2s4.8 1.8 4.8 4.2l1.4 10.4A3 3 0 0 1 16.1 21H9.5a3 3 0 0 1-2.9-3.4z" fill="#c98d4e" />
                    <path d="M9.2 7c2.2 1.2 5 1.2 7.2 0" stroke="#8a5c2e" stroke-width="1.4" fill="none" stroke-linecap="round" />
                    <path d="M12.8 3.6V6.6" stroke="#7da05c" stroke-width="1.6" stroke-linecap="round" />
                  </svg>
                  <span class="stock-body">
                    <b>{{ r.name }}</b>
                    <em v-if="r.hw">×{{ fertBagsOf(r.code) }} 袋 · 施 {{ fertAppliedOf(r.code) }}/{{ fertBagsOf(r.code) }}</em>
                    <em v-else>无作业 · 跟着水长</em>
                  </span>
                  <span class="stock-act">{{ fertLeftOf(r.code) ? "施肥" : r.hw ? "施完" : "—" }}</span>
                </button>
              </div>

              <div class="yard-foot">
                <button class="btn sm primary" :disabled="!totalLeft || busy" @click="autoApply">
                  {{ busy ? "正在施…" : "一键全施（自动生长）" }}
                </button>
                <span v-if="!totalLeft" class="yard-done">水肥都施完了，这棵树长到了本学期的状态</span>
                <span v-else class="hint">还剩 {{ totalLeft }} 袋没施，每施一袋树当场长一点</span>
              </div>
            </div>
          </div>

          <aside v-if="current" class="panel">
            <div class="panel-head">
              <span class="swatch" :style="{ background: appleColorOf(current) }"></span>
              <div class="panel-title">
                <b>{{ current.name }}</b>
                <em>{{ current.code }} · {{ current.credit }} 学分 · {{ current.teacher }}</em>
              </div>
              <span class="badge" :style="{ color: STATUS_COLOR[current.status], borderColor: STATUS_COLOR[current.status] }">
                {{ STATUS_LABEL[current.status] }}
              </span>
            </div>

            <div class="big">
              <b>{{ current.score }}</b>
              <span>最近一次测评（期中）</span>
            </div>

            <div class="kv">
              <div><span>期中卷面</span><b>{{ current.midterm }}</b></div>
              <div><span>班级均分</span><b>{{ current.cohort ?? "—" }}</b></div>
              <div><span>挂科概率</span><b :style="{ color: current.fail > 0.5 ? 'var(--red)' : current.fail > 0.25 ? '#16564a' : 'var(--green)' }">
                {{ Math.round(current.fail * 100) }}%</b></div>
              <div><span>本期变化</span><b :style="{ color: current.delta >= 0 ? 'var(--green)' : 'var(--red)' }">
                {{ current.delta > 0 ? "+" : "" }}{{ current.delta }}</b></div>
            </div>

            <!-- 这颗果实的水肥账：为什么长到这么大 -->
            <div class="wf">
              <div class="wf-row">
                <span><i class="chip fert"></i>肥 · 作业</span>
                <div class="bar">
                  <i :style="{ width: `${Math.round((current.hw ? current.hw.rate : current.attend.rate) * 100)}%` }"></i>
                </div>
                <b v-if="current.hw">{{ current.hw.done }}/{{ current.hw.due }}</b>
                <b v-else>无作业</b>
              </div>
              <div class="wf-row">
                <span><i class="chip water"></i>水 · 到课</span>
                <div class="bar"><i :style="{ width: `${Math.round(current.attend.rate * 100)}%` }"></i></div>
                <b>{{ current.attend.done }}/{{ current.attend.due }}</b>
              </div>
              <p class="wf-tip">
                苹果颜色＝作业完成度（青→黄→红），大小＝{{ current.credit }} 学分 × 成熟度 {{ Math.round(current.maturity * 100) }}%
                <template v-if="current.hw && current.hw.due > 0">
                  。只算已经截止的作业，每门课各自比完成率——留 {{ current.hw.due }} 次的课和留 7 次的课，
                  交齐了就一样红，不比次数
                </template>
                <template v-else-if="!current.hw">
                  。这门课没有留作业，颜色与个头都按到课与随堂折算
                </template>
                <template v-else>
                  。这门课还没有到期作业，暂按到课折算
                </template>
              </p>
              <!-- 补交：仓库当场多一袋肥 -->
              <button
                v-if="current.hw && fertBagsOf(current.code) < current.hw.due"
                class="btn sm tiny makeup"
                :disabled="busy"
                @click="addFertBag(current.code)"
              >
                补交一次作业 → 仓库 +1 袋肥
              </button>
            </div>

            <div class="spark">
              <span class="spark-cap">本学期 5 次测评</span>
              <div class="spark-bars">
                <i v-for="(p, i) in current.points" :key="i"
                  :style="{ height: `${Math.max(6, Math.min(100, p.score))}%`, background: p.kind === 'exam' ? STATUS_COLOR[current.status] : 'rgba(217,119,6,.35)' }"
                  :title="`${p.label} ${p.score} 分`"></i>
              </div>
            </div>

            <p class="panel-tip">
              <template v-if="current.status === 'risk'">
                这颗果实最该先处理。它拖的是 {{ current.credit }} 个学分，补考成本比现在补高得多。
              </template>
              <template v-else-if="current.fail >= 0.6">
                分数看着还行，但风险引擎给的挂科概率是 {{ Math.round(current.fail * 100) }}%——它算的是出勤和作业，
                这两项一塌，卷面分再好看也可能过不了。先补这两项。
              </template>
              <template v-else-if="current.status === 'watch'">
                还在这根线附近晃。别等期末，先把随堂测和作业的分数拿稳。
              </template>
              <template v-else>
                状态不错。保持住，别让出勤和作业先松掉——松的往往就是这两项。
              </template>
            </p>

            <div class="panel-actions">
              <button class="btn primary sm" @click="goSimulate(current.code)">去试算台看看怎么救</button>
              <button class="btn sm" @click="askAi(current.name)">问 AI 怎么补</button>
            </div>

            <div class="sibs">
              <span class="sibs-cap">换一颗看</span>
              <button v-for="r in rows.filter((x) => x.code !== current.code)" :key="r.code" class="sib" @click="selected = r.code">
                <i :style="{ background: appleColorOf(r) }"></i>
                {{ r.name }}
                <em :style="{ color: STATUS_COLOR[r.status] }">{{ r.score }}</em>
              </button>
            </div>
          </aside>
        </div>

        <p class="tree-line">{{ summary }}</p>

        <!-- 水肥账本：这棵树是浇出来的，也是施出来的 -->
        <div class="ledger">
          <div class="led">
            <span class="led-cap"><i class="chip water"></i>水 · 到课</span>
            <div class="bar"><i :style="{ width: `${Math.round(water.rate * 100)}%` }"></i></div>
            <b>{{ Math.round(water.eff) }}/{{ water.due }} 节 · {{ Math.round(water.rate * 100) }}%</b>
            <em>每到一次课树长一点；断水只蔫不缩</em>
          </div>
          <div class="led">
            <span class="led-cap"><i class="chip fert"></i>肥 · 作业</span>
            <div class="bar"><i :style="{ width: `${Math.round(fert.rate * 100)}%` }"></i></div>
            <b>{{ fert.done }}/{{ fert.due }} 次 · {{ Math.round(fert.rate * 100) }}%</b>
            <em>每交一次那颗果实大一圈；按各课完成率算，与留多少次无关</em>
          </div>
          <div v-if="settle" class="led week">
            <span class="led-cap">第 {{ settle.week }} 周结算</span>
            <p>
              水 <b>{{ settle.water.done }}/{{ settle.water.due }}</b>
              <template v-if="settle.water.gap > 0">，还差 <b>{{ settle.water.gap }}</b> 次浇水</template>
              <template v-else>，浇足了</template>
            </p>
            <p>
              肥 <b>{{ settle.fert.done }}/{{ settle.fert.due }}</b>
              <template v-if="settle.fert.gap > 0">，还差 <b>{{ settle.fert.gap }}</b> 次施肥</template>
              <template v-else-if="settle.fert.due">，施足了</template>
              <template v-else>，本周没有到期作业</template>
            </p>
          </div>
        </div>

        <div class="legend">
          <span class="lg-cap">图例</span>
          <span class="lg-item">
            <i class="dot" style="background:#7fc062"></i><i class="dot" style="background:#f0c23e"></i><i class="dot" style="background:#e2503f"></i>
            颜色 = 作业完成度（青没过半 → 黄过半 → 红全交）
          </span>
          <span class="lg-item"><i class="ring" style="border-color:#d9483b"></i>光环 = 临界/风险提示</span>
          <span class="lg-item"><i class="size sm"></i><i class="size lg"></i>大小 = 学分 × 成熟度（施肥）</span>
          <span class="lg-item"><i class="trunk-ic"></i>树形 = 到课（浇水）</span>
          <span class="lg-item"><i class="leaf-ic"></i>果柄叶片 = 学分</span>
          <span class="lg-item muted">≥70 稳 {{ counts.ok }} · 60–69 临界 {{ counts.watch }} · &lt;60 不及格 {{ counts.risk }}</span>
        </div>
      </div>

      <RegionBand no="02" title="果实背后的账" tone="archive"
        :desc="`学分加权均分 ${avg} · 与学业档案同源；挂科概率是风险引擎口径，和果实颜色是两套`" />

      <div class="grid-2">
        <div class="card list-card">
          <div class="row head">
            <span>课程</span><span>期中</span><span>挂科概率</span><span>状态</span>
          </div>
          <button v-for="r in rows" :key="r.code" class="row" :class="{ on: selected === r.code }" @click="selected = r.code">
            <span class="row-name">
              <i class="swatch sm" :style="{ background: appleColorOf(r) }"></i>
              {{ r.name }}
            </span>
            <span class="num">{{ r.score }}</span>
            <span class="num" :style="{ color: r.fail > 0.5 ? 'var(--red)' : r.fail > 0.25 ? '#16564a' : 'var(--green)' }">
              {{ Math.round(r.fail * 100) }}%
            </span>
            <span class="badge" :style="{ color: STATUS_COLOR[r.status], borderColor: STATUS_COLOR[r.status] }">{{ STATUS_LABEL[r.status] }}</span>
          </button>
        </div>

        <div class="card">
          <div class="card-head">
            <h3>想让苹果红透、风险光环退掉，先做这两件事</h3>
            <span class="hint">按风险优先级排的</span>
          </div>
          <ActionList :actions="detail?.actions || []" :limit="2" />
          <button class="ghost-btn wide" @click="goSimulate()">打开成绩分配试算台 →</button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.tree-card {
  padding: 16px 18px 14px;
}
.tree-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.42fr) minmax(268px, 0.58fr);
  gap: 20px;
  align-items: start;
}
.tree-stage {
  min-width: 0;
  border-radius: 12px;
}
.panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: linear-gradient(180deg, #fffdf8, #fbf6ec);
}
.panel-head {
  display: flex;
  align-items: flex-start;
  gap: 9px;
}
.swatch {
  flex: none;
  width: 12px;
  height: 12px;
  border-radius: 4px;
  margin-top: 4px;
}
.swatch.sm {
  width: 8px;
  height: 8px;
  border-radius: 3px;
  margin: 0 6px 0 0;
  display: inline-block;
}
.panel-title {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  line-height: 1.35;
}
.panel-title b {
  font-size: 14px;
  font-weight: 600;
}
.panel-title em {
  font-style: normal;
  font-size: 11px;
  color: var(--muted);
}
.badge {
  flex: none;
  font-size: 10.5px;
  padding: 1px 7px;
  border: 1px solid;
  border-radius: 10px;
  line-height: 1.6;
}
.big {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.big b {
  font-size: 38px;
  font-weight: 600;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.big span {
  font-size: 10.5px;
  color: var(--muted);
}
.kv {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 10px;
}
.kv div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 6px;
  padding: 5px 9px;
  border-radius: 8px;
  background: #fff;
  border: 1px solid var(--line);
}
.kv span {
  font-size: 10.5px;
  color: var(--muted);
}
.kv b {
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.spark {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.spark-cap {
  font-size: 10.5px;
  color: var(--muted);
}
.spark-bars {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  height: 46px;
  padding: 0 2px;
}
.spark-bars i {
  flex: 1;
  border-radius: 3px 3px 2px 2px;
  display: block;
}
.panel-tip {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.65;
  color: var(--text-2);
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(217, 119, 6, 0.07);
}
.panel-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.sibs {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-top: 10px;
  border-top: 1px dashed var(--line);
}
.sibs-cap {
  font-size: 10.5px;
  color: var(--muted);
}
.sib {
  display: flex;
  align-items: center;
  gap: 6px;
  border: 0;
  background: transparent;
  padding: 3px 4px;
  border-radius: 6px;
  font-size: 11.5px;
  color: var(--text-2);
  text-align: left;
}
.sib:hover {
  background: #fff;
}
.sib i {
  width: 7px;
  height: 7px;
  border-radius: 3px;
  flex: none;
}
.sib em {
  margin-left: auto;
  font-style: normal;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  font-size: 11px;
}
.tree-line {
  margin: 12px 0 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-2);
  padding-left: 2px;
}
.legend {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 8px;
  padding-top: 9px;
  border-top: 1px dashed var(--line);
  font-size: 10.5px;
  color: var(--muted);
}
.lg-cap {
  font-weight: 600;
  color: var(--text-2);
}
.lg-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.ring {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  border: 1.5px solid;
  display: inline-block;
}
.size {
  border-radius: 50%;
  background: #9dc183;
  display: inline-block;
}
.size.sm {
  width: 7px;
  height: 7px;
}
.size.lg {
  width: 11px;
  height: 11px;
}
.grid-2 {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(0, 0.75fr);
  gap: 12px;
  align-items: start;
}
.list-card {
  padding: 8px 10px;
}
.row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 52px 74px 84px;
  align-items: center;
  gap: 6px;
  width: 100%;
  border: 0;
  background: transparent;
  padding: 7px 8px;
  border-radius: 8px;
  text-align: left;
  font-size: 12.5px;
  color: var(--text);
}
.row:hover {
  background: #f8f5ee;
}
.row.on {
  background: var(--brand-soft);
}
.row.head {
  font-size: 10.5px;
  color: var(--muted);
  padding-bottom: 4px;
  border-bottom: 1px dashed var(--line);
  border-radius: 0;
}
.row-name {
  display: flex;
  align-items: center;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.num {
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  text-align: right;
}
.row.head span:nth-child(2),
.row.head span:nth-child(3) {
  text-align: right;
}
.ghost-btn.wide {
  width: 100%;
  margin-top: 12px;
}

/* ---- 资源仓库：点袋子，树当场长 ---- */
.yard {
  margin-top: 10px;
  padding: 11px 12px 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: linear-gradient(180deg, #fffdf7, #f8f1e2);
}
.yard-cap {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 9px;
}
.yard-cap b {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
}
.yard-cap em {
  font-style: normal;
  font-size: 10.5px;
  color: var(--muted);
}
.yard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(178px, 1fr));
  gap: 8px;
}
.stock {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 9px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fff;
  cursor: pointer;
  text-align: left;
  transition:
    transform 0.18s cubic-bezier(0.3, 0.9, 0.3, 1),
    box-shadow 0.18s ease,
    border-color 0.18s ease;
}
.stock:hover:not(:disabled) {
  transform: translateY(-2px);
  border-color: var(--brand);
  box-shadow: 0 5px 14px rgba(120, 90, 40, 0.13);
}
.stock:active:not(:disabled) {
  transform: translateY(0) scale(0.97);
}
.stock:disabled {
  cursor: default;
  opacity: 0.55;
}
.stock.empty {
  opacity: 0.42;
}
.stock-pop {
  animation: stock-bump 0.6s cubic-bezier(0.3, 1.1, 0.4, 1);
}
.bag-ic {
  flex: none;
  width: 26px;
  height: 26px;
}
.stock-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.stock-body b {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.stock-body em {
  font-style: normal;
  font-size: 9.5px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.stock-act {
  flex: none;
  font-size: 10px;
  font-weight: 600;
  color: var(--brand);
  padding: 2px 7px;
  border-radius: 9px;
  background: var(--brand-soft);
}
.yard-foot {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 10px;
}
.yard-done {
  font-size: 11px;
  font-weight: 600;
  color: var(--green);
}
.makeup {
  align-self: flex-start;
}

/* 飞在半空的袋子（挂在 body 上的浮层） */
:global(.fly-bag) {
  position: fixed;
  left: 0;
  top: 0;
  width: 36px;
  height: 36px;
  z-index: 9999;
  pointer-events: none;
  filter: drop-shadow(0 4px 8px rgba(80, 55, 20, 0.28));
}

@keyframes stock-bump {
  0% {
    transform: scale(1);
    box-shadow: 0 0 0 0 rgba(217, 119, 6, 0.4);
  }
  40% {
    transform: scale(1.07);
    box-shadow: 0 0 0 7px rgba(217, 119, 6, 0.12);
  }
  100% {
    transform: scale(1);
    box-shadow: 0 0 0 0 rgba(217, 119, 6, 0);
  }
}

/* ---- 水肥账本 ---- */
.ledger {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
  padding-top: 11px;
  border-top: 1px dashed var(--line);
}
.led {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 9px 11px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fff;
  min-width: 0;
}
.led.week {
  background: linear-gradient(180deg, #fffdf8, #fbf6ec);
}
.led-cap {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 10.5px;
  font-weight: 600;
  color: var(--text-2);
}
.led b {
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.led em {
  font-style: normal;
  font-size: 10px;
  line-height: 1.55;
  color: var(--muted);
}
.led.week p {
  margin: 0;
  font-size: 11px;
  line-height: 1.7;
  color: var(--text-2);
}
.chip {
  width: 8px;
  height: 8px;
  border-radius: 3px;
  display: inline-block;
  flex: none;
}
.chip.water {
  background: #4a86bd;
}
.chip.fert {
  background: #c96f43;
}
.bar {
  height: 6px;
  border-radius: 999px;
  background: #f1ece1;
  overflow: hidden;
}
.bar i {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #9dc183, #6f9a5f);
  transition: width 0.5s cubic-bezier(0.3, 0.9, 0.3, 1);
}
.trunk-ic {
  width: 6px;
  height: 12px;
  border-radius: 3px;
  background: #8d5a33;
  display: inline-block;
}
.leaf-ic {
  width: 11px;
  height: 7px;
  border-radius: 50% 6px 50% 6px;
  background: #6f9a5f;
  display: inline-block;
  transform: rotate(-18deg);
}

/* ---- 单科面板里的水肥 ---- */
.wf {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 9px 10px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: #fff;
}
.wf-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
}
.wf-row > span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 10.5px;
  color: var(--muted);
  white-space: nowrap;
}
.wf-row b {
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.wf-tip {
  margin: 2px 0 0;
  font-size: 10.5px;
  line-height: 1.65;
  color: var(--muted);
}
@media (max-width: 1080px) {
  .ledger {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 1080px) {
  .tree-grid {
    grid-template-columns: 1fr;
  }
  .grid-2 {
    grid-template-columns: 1fr;
  }
}
@media (prefers-reduced-motion: reduce) {
  .stock,
  .stock-pop {
    transition: none !important;
    animation: none !important;
  }
}
</style>
