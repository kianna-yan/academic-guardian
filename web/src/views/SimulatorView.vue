<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus/es/components/message/index";
import { useRoute, useRouter } from "vue-router";
import { api } from "@/api/client";
import RegionBand from "@/components/RegionBand.vue";
import { useAuthStore } from "@/stores/auth";
import { useChatStore } from "@/stores/chat";
import type { SimCourse, SimPayload, SimPlan } from "@/types";

/**
 * 成绩分配试算台。
 *
 * 一句话：把一门课的考核构成摊开，每一项你自己拖，最后看这门课会不会挂。
 * - 每一项的"起点"都来自学生自己的真实数据（随堂测均值、期中卷面、出勤、作业率）；
 * - 权重按课程性质给默认方案，学生可以改，改了按比例归一，总评立刻重算；
 * - 判定两条线：总评 ≥ 60，且期末卷面 ≥ 45（常见校规，页面写明是演示口径）。
 * 结论全部在前端算，拖滑杆零延迟；保存的是"你的分配方案"本身。
 */
const auth = useAuthStore();
const chat = useChatStore();
const route = useRoute();
const router = useRouter();
const sid = computed(() => auth.profile?.sid || "");

const data = ref<SimPayload | null>(null);
const loading = ref(true);
const error = ref("");
const saving = ref(false);
const editing = ref(false);
const selected = ref<string>("");
const dirty = ref(false);
const savedAt = ref<string | null>(null);

const plan = reactive<Record<string, SimPlan>>({});

const COMPONENT_COLOR: Record<string, string> = {
  daily: "#d9a04a",
  homework: "#6f9a8a",
  quiz: "#8a7bb8",
  midterm: "#5b8cc4",
  final: "#c96f43",
};

function seed(course: SimCourse, saved?: SimPlan) {
  const scores: Record<string, number> = {};
  const weights: Record<string, number> = {};
  for (const c of course.components) {
    scores[c.key] = Math.round(saved?.scores?.[c.key] ?? c.base);
    weights[c.key] = Math.round(saved?.weights?.[c.key] ?? c.weight);
  }
  return { scores, weights };
}

async function load() {
  if (!sid.value) return;
  loading.value = true;
  error.value = "";
  try {
    const payload = await api.simulate(sid.value);
    data.value = payload;
    savedAt.value = payload.saved.saved_at;
    for (const c of payload.courses) {
      plan[c.code] = seed(c, payload.saved.plans?.[c.code]);
    }
    const want = String(route.query.course || "");
    const hit = payload.courses.find((c) => c.code === want);
    const worst = [...payload.courses].sort((a, b) => b.fail_probability - a.fail_probability)[0];
    selected.value = hit?.code || worst?.code || payload.courses[0]?.code || "";
    dirty.value = false;
  } catch (e: any) {
    error.value = e?.message || "加载失败";
  } finally {
    loading.value = false;
  }
}
watch(() => sid.value, () => load(), { immediate: true });

const courses = computed(() => data.value?.courses || []);
const course = computed(() => courses.value.find((c) => c.code === selected.value) || courses.value[0] || null);

/* ---------------- 核心算法：全部在前端，拖一下就能算 ---------------- */
function weightSum(w: Record<string, number>) {
  return Object.values(w).reduce((s, v) => s + v, 0) || 1;
}

function evaluate(c: SimCourse) {
  const p = plan[c.code] || seed(c);
  const tw = weightSum(p.weights);
  const parts = c.components.map((comp) => {
    const s = p.scores[comp.key] ?? 0;
    const w = p.weights[comp.key] ?? 0;
    const points = (s * w) / tw;
    return { key: comp.key, short: comp.short, label: comp.label, score: s, weight: w, share: (w / tw) * 100, points };
  });
  const total = parts.reduce((s, x) => s + x.points, 0);
  const finalPart = parts.find((x) => x.key === "final");
  const rest = parts.filter((x) => x.key !== "final").reduce((s, x) => s + x.points, 0);
  const wFinal = finalPart ? (finalPart.weight / tw) * 100 : 0;
  // 期末卷面最低要多少：总评够 60 与卷面够 45 取更狠的一条
  const needTotal = wFinal > 0 ? ((60 - rest) / wFinal) * 100 : 0;
  const needFinal = Math.min(100, Math.max(needTotal, 45));
  const guardOk = !finalPart || (p.scores.final ?? 100) >= 45;
  const pass = total >= 60 && guardOk;
  return {
    total,
    span: Math.max(total, 62),
    pass,
    margin: total - 60,
    needFinal: Number.isFinite(needFinal) ? Math.round(needFinal * 10) / 10 : 0,
    hopeless: needTotal > 100,
    needTotal: Math.round(needTotal * 10) / 10,
    guardOk,
    parts,
    changed: parts.some((x, i) => x.score !== c.components[i].base || x.weight !== c.components[i].weight),
  };
}

const evalNow = computed(() => (course.value ? evaluate(course.value) : null));
const evalMap = computed(() => {
  const m: Record<string, ReturnType<typeof evaluate>> = {};
  for (const c of courses.value) m[c.code] = evaluate(c);
  return m;
});

/** 学期口径：学分加权均分、绩点、会挂几门 */
const term = computed(() => {
  const list = courses.value.map((c) => ({ c, e: evalMap.value[c.code] }));
  const credits = list.reduce((s, x) => s + (x.c.credit || 0), 0) || 1;
  const avg = list.reduce((s, x) => s + x.e.total * (x.c.credit || 0), 0) / credits;
  const gpa = list.reduce((s, x) => s + gpaOf(x.e.total) * (x.c.credit || 0), 0) / credits;
  return {
    avg: Math.round(avg * 10) / 10,
    gpa: Math.round(gpa * 100) / 100,
    failing: list.filter((x) => !x.e.pass).length,
    credits,
  };
});

function gpaOf(score: number) {
  const table: [number, number][] = [[90, 4], [85, 3.7], [82, 3.3], [78, 3], [75, 2.7], [72, 2.3], [68, 2], [64, 1.5], [60, 1]];
  for (const [line, g] of table) if (score >= line) return g;
  return 0;
}

function verdictTone(e: { pass: boolean; total: number }) {
  if (!e.pass) return "risk";
  if (e.total >= 85) return "great";
  if (e.total >= 75) return "ok";
  return "watch";
}

/* ---------------- 编辑动作 ---------------- */
function touch() {
  dirty.value = true;
}
function clamp(v: number) {
  return Math.max(0, Math.min(100, Math.round(Number(v) || 0)));
}
function setScore(key: string, v: number | string) {
  if (!course.value) return;
  plan[course.value.code].scores[key] = clamp(Number(v));
  touch();
}
function setWeight(key: string, v: number | string) {
  if (!course.value) return;
  plan[course.value.code].weights[key] = Math.max(0, Math.min(100, Math.round(Number(v) || 0)));
  touch();
}

function preset(kind: "base" | "push" | "slip" | "grind") {
  if (!course.value) return;
  const c = course.value;
  const p = plan[c.code];
  for (const comp of c.components) {
    if (kind === "base") {
      p.scores[comp.key] = Math.round(comp.base);
      p.weights[comp.key] = Math.round(comp.weight);
    } else if (kind === "push") {
      p.scores[comp.key] = clamp((p.scores[comp.key] ?? comp.base) + (comp.key === "final" ? 12 : 4));
    } else if (kind === "slip") {
      p.scores[comp.key] = clamp((p.scores[comp.key] ?? comp.base) - (comp.key === "final" ? 15 : 5));
    } else {
      // 把过程分拉满，期末按现在的估计：最常见的"我能做的都做了"版本
      if (["daily", "homework", "quiz"].includes(comp.key)) p.scores[comp.key] = 100;
    }
  }
  touch();
}

function resetCourse() {
  if (!course.value) return;
  plan[course.value.code] = seed(course.value);
  touch();
  ElMessage.success("这门课已回到你的真实起点");
}

async function save() {
  if (!sid.value) return;
  saving.value = true;
  try {
    const plans: Record<string, SimPlan> = {};
    for (const c of courses.value) plans[c.code] = plan[c.code];
    const res = await api.saveSimulation(sid.value, { plans });
    savedAt.value = res.saved.saved_at;
    dirty.value = false;
    ElMessage.success(res.persistent ? "分配方案已保存，下次打开还在" : "已在本次会话中生效（磁盘不可写）");
  } catch (e: any) {
    ElMessage.error(e?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function resetAll() {
  if (!sid.value) return;
  saving.value = true;
  try {
    await api.saveSimulation(sid.value, { plans: {}, action: "reset" });
    for (const c of courses.value) plan[c.code] = seed(c);
    savedAt.value = null;
    dirty.value = false;
    ElMessage.success("已清空，回到你的真实成绩构成");
  } catch (e: any) {
    ElMessage.error(e?.message || "清空失败");
  } finally {
    saving.value = false;
  }
}

function askAi() {
  if (!course.value) return;
  const e = evalNow.value;
  chat.ask(
    "student",
    sid.value || null,
    `我在试算《${course.value.name}》：期末预计 ${plan[course.value.code]?.scores.final ?? 0} 分，总评 ${e?.total.toFixed(1)} 分，${e?.pass ? "能过" : "会挂"}。这个分配合理吗？我该把力气花在哪一项上？`,
  );
  router.push("/student");
}

const pct = (v: number) => `${Math.max(0, Math.min(100, v))}%`;
</script>

<template>
  <div class="page">
    <div v-if="loading && !data" class="card"><div class="skeleton" style="height: 360px"></div></div>

    <div v-else-if="error" class="card">
      <b>加载失败</b>
      <p class="tiny muted">{{ error }}</p>
      <button class="btn" @click="load">重试</button>
    </div>

    <template v-else-if="data">
      <RegionBand no="01" title="成绩分配试算台" tone="learn"
        :desc="`${data.student.term} · 每一项你自己定，总评和挂科判定实时重算`">
        <button class="ghost-btn" @click="resetAll">全部回到起点</button>
      </RegionBand>

      <div class="card hero">
        <div class="hero-grid">
          <div class="hero-cell">
            <b>{{ term.avg }}</b><span>学分加权预计均分</span>
          </div>
          <div class="hero-cell" :class="{ red: term.failing > 0, green: term.failing === 0 }">
            <b>{{ term.failing }}</b><span>按当前分配会挂的课</span>
          </div>
          <div class="hero-cell">
            <b>{{ term.gpa.toFixed(2) }}</b><span>预计绩点（4.0 制）</span>
          </div>
          <div class="hero-cell">
            <b>{{ term.credits }}</b><span>本学期学分</span>
          </div>
        </div>
        <p class="hero-line">
          口径：总评 ≥ <b>{{ data.pass_line }}</b> 且期末卷面 ≥ <b>{{ data.final_guard }}</b> 才算过。
          权重按课程性质给了默认方案，教务最终方案为准；每一项的起点分都来自你自己的真实数据。
        </p>
      </div>

      <div class="work">
        <!-- 课程列 -->
        <div class="card picker">
          <div class="picker-cap">选一门课</div>
          <button v-for="c in courses" :key="c.code" class="pick" :class="{ on: c.code === selected }" @click="selected = c.code">
            <span class="pick-top">
              <b>{{ c.name }}</b>
              <em>{{ c.credit }} 学分</em>
            </span>
            <span class="pick-bar">
              <i :style="{ width: pct(evalMap[c.code]?.total || 0), background: evalMap[c.code]?.pass ? (evalMap[c.code].total >= 75 ? '#46a06a' : '#e0a02c') : '#d9483b' }"></i>
              <u class="line"></u>
            </span>
            <span class="pick-foot">
              <span class="num">{{ (evalMap[c.code]?.total || 0).toFixed(1) }}</span>
              <span class="tag-mini" :class="verdictTone(evalMap[c.code] || { pass: true, total: 0 })">
                {{ evalMap[c.code]?.pass ? "能过" : "会挂" }}
              </span>
            </span>
          </button>
        </div>

        <!-- 分配台 -->
        <div v-if="course && evalNow" class="card desk">
          <div class="desk-head">
            <div class="desk-title">
              <b>{{ course.name }}</b>
              <em>{{ course.teacher }} · {{ course.scheme_label }} · 共 {{ course.components.length }} 项</em>
            </div>
            <div class="desk-side">
              <button class="seg-btn" :class="{ on: editing }" @click="editing = !editing">
                {{ editing ? "完成改占比" : "改占比" }}
              </button>
            </div>
          </div>

          <!-- 判定条 -->
          <div class="verdict" :class="verdictTone(evalNow)">
            <div class="v-left">
              <b>{{ evalNow.total.toFixed(1) }}</b>
              <span>总评（100 分制）</span>
            </div>
            <div class="v-mid">
              <strong>{{ evalNow.pass ? "不会挂" : "会挂" }}</strong>
              <span v-if="evalNow.pass">
                比及格线高 {{ evalNow.margin.toFixed(1) }} 分<template v-if="evalNow.guardOk">，期末卷面也过了 45 分线</template>
              </span>
              <span v-else-if="!evalNow.guardOk">期末卷面不到 45 分，总评再高也算不通过</span>
              <span v-else>离及格线还差 {{ Math.abs(evalNow.margin).toFixed(1) }} 分</span>
            </div>
            <div class="v-right">
              <template v-if="!evalNow.pass">
                <b>{{ evalNow.hopeless ? "—" : evalNow.needFinal }}</b>
                <span>{{ evalNow.hopeless ? "期末满分也救不回来" : "期末至少考这么多分" }}</span>
              </template>
              <template v-else>
                <b>{{ evalNow.needFinal }}</b>
                <span>期末考到这些仍能过</span>
              </template>
            </div>
          </div>

          <!-- 贡献条：每项往上加了多少分 -->
          <div class="stack">
            <div class="stack-bar">
              <i v-for="p in evalNow.parts" :key="p.key" :style="{ width: `${(p.points / evalNow.span) * 100}%`, background: COMPONENT_COLOR[p.key] }"
                :title="`${p.label} ${p.weight}% × ${p.score} = ${p.points.toFixed(1)} 分`"></i>
              <span class="pass-mark" :style="{ left: `${(60 / evalNow.span) * 100}%` }"></span>
            </div>
            <div class="stack-cap">
              <span v-for="p in evalNow.parts" :key="p.key">
                <i :style="{ background: COMPONENT_COLOR[p.key] }"></i>{{ p.short }} {{ p.points.toFixed(1) }}
              </span>
              <span class="stack-total">合计 {{ evalNow.total.toFixed(1) }}<em>（白线 = 60 分及格线）</em></span>
            </div>
          </div>

          <!-- 每一项 -->
          <div class="comps">
            <div v-for="comp in course.components" :key="comp.key" class="comp">
              <div class="comp-head">
                <span class="comp-name">
                  <i class="cc" :style="{ background: COMPONENT_COLOR[comp.key] }"></i>
                  {{ comp.label }}
                </span>
                <span class="comp-w">
                  <template v-if="editing">
                    <input class="winput" type="number" min="0" max="100" :value="plan[course.code].weights[comp.key]"
                      @input="setWeight(comp.key, ($event.target as HTMLInputElement).value)" />%
                  </template>
                  <template v-else>{{ Math.round(plan[course.code].weights[comp.key]) }}%</template>
                </span>
              </div>

              <div class="comp-body">
                <input class="range" type="range" min="0" max="100" step="1"
                  :value="plan[course.code].scores[comp.key]"
                  :style="{ '--cc': COMPONENT_COLOR[comp.key], '--p': `${plan[course.code].scores[comp.key]}%` }"
                  @input="setScore(comp.key, ($event.target as HTMLInputElement).value)" />
                <input class="score-input" type="number" min="0" max="100" :value="plan[course.code].scores[comp.key]"
                  @input="setScore(comp.key, ($event.target as HTMLInputElement).value)" />
              </div>

              <div class="comp-foot">
                <span>{{ comp.basis }} · 起点 {{ Math.round(comp.base) }} 分</span>
                <button class="link" @click="setScore(comp.key, comp.base); touch()">回到起点</button>
              </div>
            </div>
          </div>

          <div class="preset-row">
            <span class="preset-cap">一键情景</span>
            <button class="chip" @click="preset('base')">按现状</button>
            <button class="chip" @click="preset('push')">超常发挥</button>
            <button class="chip" @click="preset('slip')">失手一次</button>
            <button class="chip" @click="preset('grind')">过程分拉满</button>
            <span class="preset-note" v-if="editing">改占比后按比例折算，总评立刻重算 —— 占比以教务最终方案为准</span>
          </div>

          <div class="desk-actions">
            <button class="btn primary" :disabled="saving" @click="save">
              {{ saving ? "保存中…" : dirty ? "保存我的分配" : "方案已保存 · 再存一次" }}
            </button>
            <button class="btn" @click="resetCourse">这门课回到起点</button>
            <button class="btn" @click="askAi">问 AI 这个分配合理吗</button>
            <span class="saved" v-if="savedAt">上次保存 {{ savedAt }}</span>
          </div>
        </div>
      </div>

      <RegionBand no="02" title="这套算法是怎么算的" tone="archive"
        :desc="`五套权重方案 · ${data.courses.length} 门课各按自己的性质取一套`" />

      <div class="card method">
        <div class="method-grid">
          <div v-for="(sch, key) in data.schemes" :key="key" class="method-item">
            <b>{{ sch.label }}</b>
            <div class="method-row">
              <span v-for="c in sch.components" :key="c.key">{{ c.short }} {{ c.weight }}%</span>
            </div>
          </div>
        </div>
        <p class="method-note">
          期末还没考，起点分按"期中 + 本学期测评趋势"估了一个参考值；随堂测取 4 次均值，平时按出勤与迟到折算，作业按提交率折算。
          你调的是"打算考多少"，不是"已经考了多少"——所以这里的所有数字都不进风险评分，也不会被辅导员看到。
        </p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.hero {
  padding: 14px 16px;
}
.hero-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.hero-cell {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 8px 12px;
  border-radius: 10px;
  background: #faf6ee;
}
.hero-cell b {
  font-size: 24px;
  font-weight: 600;
  line-height: 1.15;
  font-variant-numeric: tabular-nums;
}
.hero-cell span {
  font-size: 11px;
  color: var(--muted);
}
.hero-cell.red b {
  color: var(--red);
}
.hero-cell.green b {
  color: var(--green);
}
.hero-line {
  margin: 10px 0 0;
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--muted);
}
.hero-line b {
  color: var(--text-2);
}

.work {
  display: grid;
  grid-template-columns: 236px minmax(0, 1fr);
  gap: 12px;
  margin-top: 12px;
  align-items: start;
}
.picker {
  padding: 12px 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.picker-cap {
  font-size: 10.5px;
  color: var(--muted);
  padding: 0 4px 2px;
}
.pick {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 8px 9px;
  border: 1px solid transparent;
  border-radius: 9px;
  background: #fbf7ef;
  text-align: left;
  transition: border-color 0.16s, background 0.16s;
}
.pick:hover {
  background: #f7f1e4;
}
.pick.on {
  background: #fff;
  border-color: var(--brand);
  box-shadow: 0 1px 6px rgba(217, 119, 6, 0.12);
}
.pick-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 6px;
}
.pick-top b {
  font-size: 12px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pick-top em {
  flex: none;
  font-style: normal;
  font-size: 10px;
  color: var(--muted);
}
.pick-bar {
  position: relative;
  height: 4px;
  border-radius: 3px;
  background: #eadfcd;
  overflow: hidden;
}
.pick-bar i {
  display: block;
  height: 100%;
  border-radius: 3px;
}
.pick-bar .line {
  position: absolute;
  left: 60%;
  top: 0;
  width: 1px;
  height: 100%;
  background: rgba(59, 46, 36, 0.45);
}
.pick-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 10.5px;
  color: var(--muted);
}
.pick-foot .num {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: var(--text-2);
  font-size: 11.5px;
}
.tag-mini {
  font-size: 10px;
  padding: 0 6px;
  border-radius: 8px;
  border: 1px solid;
}
.tag-mini.risk {
  color: var(--red);
  border-color: rgba(220, 38, 38, 0.35);
  background: var(--red-soft);
}
.tag-mini.watch {
  color: #b45309;
  border-color: rgba(217, 119, 6, 0.35);
  background: var(--amber-soft);
}
.tag-mini.ok,
.tag-mini.great {
  color: var(--green);
  border-color: rgba(4, 120, 87, 0.3);
  background: var(--green-soft);
}

.desk {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.desk-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}
.desk-title {
  display: flex;
  flex-direction: column;
  line-height: 1.4;
}
.desk-title b {
  font-size: 15px;
  font-weight: 600;
}
.desk-title em {
  font-style: normal;
  font-size: 11px;
  color: var(--muted);
}
.seg-btn {
  border: 1px solid var(--line-strong);
  background: #fff;
  border-radius: 8px;
  padding: 4px 10px;
  font-size: 11.5px;
  color: var(--text-2);
}
.seg-btn.on {
  background: var(--brand-soft);
  border-color: rgba(217, 119, 6, 0.4);
  color: var(--brand);
  font-weight: 600;
}

.verdict {
  display: grid;
  grid-template-columns: 128px minmax(0, 1fr) 148px;
  gap: 12px;
  align-items: center;
  padding: 12px 14px;
  border-radius: 11px;
  border: 1px solid var(--line);
  background: #faf6ee;
}
.verdict.risk {
  background: linear-gradient(180deg, #fef2f2, #fff8f6);
  border-color: #f6d5d1;
}
.verdict.watch {
  background: linear-gradient(180deg, #fffbeb, #fffdf6);
  border-color: #f7e4bf;
}
.verdict.ok,
.verdict.great {
  background: linear-gradient(180deg, #ecfdf5, #f7fdf9);
  border-color: #cfe9dd;
}
.v-left {
  display: flex;
  flex-direction: column;
}
.v-left b {
  font-size: 34px;
  font-weight: 600;
  line-height: 1.05;
  font-variant-numeric: tabular-nums;
}
.v-left span {
  font-size: 10.5px;
  color: var(--muted);
}
.v-mid {
  display: flex;
  flex-direction: column;
  gap: 2px;
  border-left: 1px dashed rgba(59, 46, 36, 0.18);
  padding-left: 12px;
}
.v-mid strong {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.5px;
}
.verdict.risk .v-mid strong {
  color: var(--red);
}
.verdict.watch .v-mid strong {
  color: #b45309;
}
.verdict.ok .v-mid strong,
.verdict.great .v-mid strong {
  color: var(--green);
}
.v-mid span {
  font-size: 11.5px;
  color: var(--text-2);
  line-height: 1.55;
}
.v-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  text-align: right;
}
.v-right b {
  font-size: 22px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.v-right span {
  font-size: 10.5px;
  color: var(--muted);
}

.stack {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.stack-bar {
  position: relative;
  display: flex;
  height: 14px;
  border-radius: 7px;
  overflow: hidden;
  background: #f2e9da;
}
.stack-bar i {
  height: 100%;
  transition: width 0.25s ease;
}
.pass-mark {
  position: absolute;
  top: -3px;
  bottom: -3px;
  width: 2px;
  background: rgba(255, 255, 255, 0.95);
  box-shadow: 0 0 0 1px rgba(59, 46, 36, 0.25);
}
.stack-cap {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 10.5px;
  color: var(--muted);
}
.stack-cap i {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 2px;
  margin-right: 4px;
}
.stack-total {
  margin-left: auto;
  color: var(--text-2);
}
.stack-total em {
  font-style: normal;
  color: var(--muted);
}

.comps {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.comp {
  padding: 9px 10px;
  border-radius: 9px;
}
.comp:hover {
  background: #fbf7ef;
}
.comp-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.comp-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: var(--text);
}
.cc {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.comp-w {
  font-size: 11.5px;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 2px;
}
.winput {
  width: 46px;
  padding: 2px 4px;
  border: 1px solid var(--line-strong);
  border-radius: 6px;
  font-size: 11.5px;
  text-align: right;
  color: var(--text);
  background: #fff;
}
.comp-body {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 4px 0 2px;
}
.range {
  flex: 1;
  -webkit-appearance: none;
  appearance: none;
  height: 6px;
  border-radius: 4px;
  background: linear-gradient(90deg, var(--cc, #d97706) 0%, var(--cc, #d97706) var(--p, 0%), #eee5d5 var(--p, 0%), #eee5d5 100%);
  outline: none;
}
.range::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 15px;
  height: 15px;
  border-radius: 50%;
  background: #fff;
  border: 2px solid var(--cc, #d97706);
  box-shadow: 0 1px 3px rgba(59, 46, 36, 0.25);
  cursor: grab;
}
.range::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #fff;
  border: 2px solid var(--cc, #d97706);
  cursor: grab;
}
.score-input {
  width: 54px;
  padding: 3px 6px;
  border: 1px solid var(--line-strong);
  border-radius: 7px;
  font-size: 12.5px;
  font-variant-numeric: tabular-nums;
  text-align: right;
  color: var(--text);
  background: #fff;
}
.comp-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 10.5px;
  color: var(--muted);
}
.comp-foot .link {
  border: 0;
  background: transparent;
  color: var(--brand);
  font-size: 10.5px;
  padding: 0;
  text-decoration: underline;
}
.preset-row {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
  padding-top: 4px;
  border-top: 1px dashed var(--line);
}
.preset-cap {
  font-size: 10.5px;
  color: var(--muted);
}
.chip {
  border: 1px solid var(--line-strong);
  background: #fff;
  border-radius: 14px;
  padding: 3px 11px;
  font-size: 11.5px;
  color: var(--text-2);
}
.chip:hover {
  border-color: var(--brand);
  color: var(--brand);
}
.preset-note {
  font-size: 10.5px;
  color: var(--muted);
}
.desk-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.saved {
  font-size: 10.5px;
  color: var(--muted);
  margin-left: auto;
}

.method {
  padding: 14px 16px;
}
.method-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(196px, 1fr));
  gap: 10px;
}
.method-item {
  padding: 9px 11px;
  border-radius: 9px;
  background: #faf6ee;
}
.method-item b {
  font-size: 12px;
  font-weight: 600;
}
.method-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
  margin-top: 3px;
  font-size: 10.5px;
  color: var(--muted);
}
.method-note {
  margin: 10px 0 0;
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--muted);
}
@media (max-width: 1080px) {
  .work {
    grid-template-columns: 1fr;
  }
  .hero-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .verdict {
    grid-template-columns: 100px minmax(0, 1fr);
  }
  .v-right {
    grid-column: 1 / -1;
    align-items: flex-start;
    text-align: left;
    border-top: 1px dashed rgba(59, 46, 36, 0.15);
    padding-top: 6px;
  }
}
</style>
