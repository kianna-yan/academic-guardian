<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client";
import ActionList from "@/components/ActionList.vue";
import RegionBand from "@/components/RegionBand.vue";
import WisdomTree from "@/components/WisdomTree.vue";
import { useAuthStore } from "@/stores/auth";
import { useChatStore } from "@/stores/chat";
import type { CourseTrend, StudentDetail, TreeFruit } from "@/types";

/**
 * 我的智慧树。
 * 一颗果实一门课：颜色是学科、光环是状态、大小是学分。
 * 这一页只做一件事——让人先"看见"，再点进去看账。
 */
const auth = useAuthStore();
const chat = useChatStore();
const router = useRouter();
const sid = computed(() => auth.profile?.sid || "");

const detail = ref<StudentDetail | null>(null);
const loading = ref(true);
const error = ref("");
const mode = ref<"subject" | "status">("subject");
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
  })),
);

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
  if (counts.value.risk) {
    return `这棵树上有 ${counts.value.risk} 颗果实泛红，最急的是《${w.name}》（${w.score} 分）。一门课挂科就够影响学分，现在补成本最低。`;
  }
  if (highRisk.value.length) {
    const h = [...highRisk.value].sort((a, b) => b.fail - a.fail)[0];
    return `果子的颜色都在及格线以上，但按出勤和作业算，有 ${highRisk.value.length} 门课的挂科概率超过 60%——最高的是《${h.name}》（${Math.round(h.fail * 100)}%）。分数是果子的颜色，出勤和作业是它的根。`;
  }
  if (counts.value.watch) {
    return `没有红的，但有 ${counts.value.watch} 颗在泛黄，《${w.name}》最需要盯一下。现在动手，期末大概率不用过这根线。`;
  }
  return `${rows.value.length} 颗果实都稳住了，学分加权均分 ${avg.value}。保持这个节奏，重点是别让任何一门掉出安全区。`;
});

const modeLabel = computed(() => (mode.value === "subject" ? "按学科着色" : "按状态着色"));

function courseColor(code: string) {
  const colors = ["#c96f43", "#4a86bd", "#8a68c0", "#3f9a86", "#c05b7d", "#a9853d", "#5a7cc4", "#7d9a4c"];
  let h = 0;
  for (let i = 0; i < code.length; i++) h = (h * 31 + code.charCodeAt(i)) % 9973;
  return colors[h % colors.length];
}
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
  chat.ask("student", sid.value || null, `《${name}》这颗果实为什么是这个颜色？我该怎么让它变回绿色？`);
  router.push("/student");
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
        :desc="`${detail?.student.term || ''} · ${rows.length} 门课 · 一颗果实一门课`">
        <div class="seg">
          <button :class="{ on: mode === 'subject' }" @click="mode = 'subject'">按学科</button>
          <button :class="{ on: mode === 'status' }" @click="mode = 'status'">按状态</button>
        </div>
      </RegionBand>

      <div class="card tree-card">
        <div class="tree-grid">
          <div class="tree-stage">
            <WisdomTree :fruits="fruits" :mode="mode" :selected="selected" @select="selected = $event" />
          </div>

          <aside v-if="current" class="panel">
            <div class="panel-head">
              <span class="swatch" :style="{ background: mode === 'subject' ? courseColor(current.code) : STATUS_COLOR[current.status] }"></span>
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
              <div><span>挂科概率</span><b :style="{ color: current.fail > 0.5 ? 'var(--red)' : current.fail > 0.25 ? '#b45309' : 'var(--green)' }">
                {{ Math.round(current.fail * 100) }}%</b></div>
              <div><span>本期变化</span><b :style="{ color: current.delta >= 0 ? 'var(--green)' : 'var(--red)' }">
                {{ current.delta > 0 ? "+" : "" }}{{ current.delta }}</b></div>
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
                <i :style="{ background: mode === 'subject' ? courseColor(r.code) : STATUS_COLOR[r.status] }"></i>
                {{ r.name }}
                <em :style="{ color: STATUS_COLOR[r.status] }">{{ r.score }}</em>
              </button>
            </div>
          </aside>
        </div>

        <p class="tree-line">{{ summary }}</p>

        <div class="legend">
          <span class="lg-cap">图例</span>
          <span v-if="mode === 'subject'" class="lg-item">
            <i class="dot" style="background:#c96f43"></i><i class="dot" style="background:#4a86bd"></i><i class="dot" style="background:#8a68c0"></i>颜色 = 学科
          </span>
          <span v-else class="lg-item">
            <i class="dot" style="background:#46a06a"></i><i class="dot" style="background:#e0a02c"></i><i class="dot" style="background:#d9483b"></i>颜色 = 状态
          </span>
          <span class="lg-item"><i class="ring" style="border-color:#d9483b"></i>光环 = 分数段</span>
          <span class="lg-item"><i class="size sm"></i><i class="size lg"></i>大小 = 学分</span>
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
              <i class="swatch sm" :style="{ background: mode === 'subject' ? courseColor(r.code) : STATUS_COLOR[r.status] }"></i>
              {{ r.name }}
            </span>
            <span class="num">{{ r.score }}</span>
            <span class="num" :style="{ color: r.fail > 0.5 ? 'var(--red)' : r.fail > 0.25 ? '#b45309' : 'var(--green)' }">
              {{ Math.round(r.fail * 100) }}%
            </span>
            <span class="badge" :style="{ color: STATUS_COLOR[r.status], borderColor: STATUS_COLOR[r.status] }">{{ STATUS_LABEL[r.status] }}</span>
          </button>
        </div>

        <div class="card">
          <div class="card-head">
            <h3>想让果实变回绿色，先做这两件事</h3>
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
  overflow: hidden;
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
.seg {
  display: inline-flex;
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}
.seg button {
  border: 0;
  background: transparent;
  padding: 4px 11px;
  font-size: 11.5px;
  color: var(--muted);
}
.seg button.on {
  background: var(--brand-soft);
  color: var(--brand);
  font-weight: 600;
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
  background: #faf6ee;
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
@media (max-width: 1080px) {
  .tree-grid {
    grid-template-columns: 1fr;
  }
  .grid-2 {
    grid-template-columns: 1fr;
  }
}
</style>
