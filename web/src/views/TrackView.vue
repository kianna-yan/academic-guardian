<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus/es/components/message/index";
import { useRouter } from "vue-router";
import { api } from "@/api/client";
import CheckinDialog from "@/components/CheckinDialog.vue";
import RegionBand from "@/components/RegionBand.vue";
import { useAuthStore } from "@/stores/auth";
import { useChatStore } from "@/stores/chat";
import type { CheckinList, CheckinRecord, TrackCourse, TrackPayload } from "@/types";

/**
 * 学习轨迹。
 * 每门课一条横线：一节一个点，点的颜色就是那天课后你自己的判断。
 * 连续"没听懂"的一段画成红带，叫断点；断点后面第一次听懂，那个点带一圈环——修复。
 * 这条线不讲分数，只讲"你从哪儿开始掉队、后来接上没有"。
 */
const auth = useAuthStore();
const chat = useChatStore();
const router = useRouter();
const sid = computed(() => auth.profile?.sid || "");

const data = ref<TrackPayload | null>(null);
const meta = ref<CheckinList | null>(null);
const loading = ref(true);
const error = ref("");
const seeding = ref(false);
const expanded = ref<string | null>(null);

async function load() {
  if (!sid.value) return;
  loading.value = true;
  error.value = "";
  try {
    const [t, m] = await Promise.all([api.track(sid.value), api.checkins(sid.value)]);
    data.value = t;
    meta.value = m;
    if (!expanded.value) {
      const first = t.courses.find((c) => c.status === "break" || c.status === "watch");
      expanded.value = (first || t.courses[0])?.code || null;
    }
  } catch (e: any) {
    error.value = e?.message || "加载失败";
  } finally {
    loading.value = false;
  }
}

watch(() => sid.value, () => load(), { immediate: true });

const stats = computed(() => data.value?.stats);
const hasAny = computed(() => (stats.value?.recorded || 0) > 0);

const STATUS: Record<string, { label: string; tone: string }> = {
  break: { label: "断点未接上", tone: "red" },
  watch: { label: "有模糊", tone: "amber" },
  ok: { label: "跟得上", tone: "green" },
  empty: { label: "还没记录", tone: "grey" },
};

const STATE_TEXT: Record<string, string> = { full: "听懂了", fuzzy: "有点模糊", lost: "没听懂" };

/** 把逐节状态压成色带：位置和宽度按节数百分比算，格子数变了也不用改样式 */
function bands(t: TrackCourse) {
  const n = t.points.length || 1;
  const out: { state: string; from: number; to: number; left: string; width: string }[] = [];
  let i = 0;
  while (i < t.points.length) {
    const state = t.points[i].state || "none";
    let j = i;
    while (j + 1 < t.points.length && (t.points[j + 1].state || "none") === state) j += 1;
    out.push({
      state,
      from: i,
      to: j,
      left: `${(i / n) * 100}%`,
      width: `${((j - i + 1) / n) * 100}%`,
    });
    i = j + 1;
  }
  return out;
}

/** 同一周的第一节才标周次，避免 16 个点挤一堆数字 */
function weekMarks(t: TrackCourse) {
  const seen = new Set<number>();
  const marks = new Map<number, number>();
  t.points.forEach((p, i) => {
    if (!seen.has(p.week)) {
      seen.add(p.week);
      marks.set(i, p.week);
    }
  });
  return marks;
}

/** 断点之后第一次接上的那个点，加一圈修复环 */
function healedIndexes(t: TrackCourse) {
  return new Set(
    t.breaks.filter((b) => !b.open && typeof b.recovered_index === "number").map((b) => b.recovered_index as number),
  );
}

function nodeTitle(t: TrackCourse, i: number) {
  const p = t.points[i];
  const head = `第 ${p.week} 周 · ${p.weekday} ${p.period}`;
  if (!p.recorded) return `${head} · 还没记录（点一下补记）`;
  const tail = p.state === "full" ? "听懂了" : `${STATE_TEXT[p.state]}，${p.break_label || ""}`;
  return `${head} · ${tail}${p.point ? ` · 卡在「${p.point}」` : ""}`;
}

/* ---------------- 修改记录 ---------------- */
const dlgOpen = ref(false);
const activeRecord = ref<CheckinRecord | null>(null);
const active = ref<{
  course: string;
  name: string;
  teacher?: string;
  room?: string;
  date: string;
  week: number;
  weekday_label: string;
  period: string;
} | null>(null);

function openPoint(t: TrackCourse, i: number) {
  const p = t.points[i];
  active.value = {
    course: t.code,
    name: t.name,
    teacher: t.teacher,
    room: t.room,
    date: p.date,
    week: p.week,
    weekday_label: p.weekday,
    period: p.period,
  };
  activeRecord.value = p.recorded ? meta.value?.rows.find((r) => r.id === p.id) || null : null;
  dlgOpen.value = true;
}

const activePoints = computed(() => meta.value?.points?.[active.value?.course || ""] || []);

function onSaved() {
  load();
}

async function seed() {
  seeding.value = true;
  try {
    const res = await api.demoTrack(sid.value);
    ElMessage.success(`已生成 ${res.added} 条示例记录（演示用，可随时删改）`);
    load();
  } catch (e: any) {
    ElMessage.error(e?.message || "生成失败");
  } finally {
    seeding.value = false;
  }
}

function md(iso: string) {
  const [, m, d] = iso.split("-");
  return `${Number(m)} 月 ${Number(d)} 日`;
}

function askAi(course?: string) {
  const q = course
    ? `《${course}》这门课我从哪一节开始没听懂？该怎么补？`
    : "看我的学习轨迹，哪门课最该先补？";
  chat.ask("student", sid.value || null, q);
  router.push("/student");
}
</script>

<template>
  <div class="page">
    <div v-if="loading && !data" class="card"><div class="skeleton" style="height: 300px"></div></div>

    <div v-else-if="error" class="card">
      <b>加载失败</b>
      <p class="tiny muted">{{ error }}</p>
      <button class="btn" @click="load">重试</button>
    </div>

    <template v-else-if="data">
      <RegionBand no="01" title="学习轨迹" tone="learn"
        :desc="`${data.meta.term} · 第 ${data.meta.week} 周 · 只记录你自己的判断，不参与风险评分`">
        <div class="legend">
          <span><i class="dot full"></i>听懂</span>
          <span><i class="dot fuzzy"></i>模糊</span>
          <span><i class="dot lost"></i>没懂</span>
          <span><i class="dot none"></i>没记</span>
          <span><i class="dot heal"></i>已接上</span>
        </div>
      </RegionBand>

      <div class="card sum-card">
        <div class="sum-grid">
          <div class="sum">
            <b>{{ stats?.recorded }}</b><span>记过的课 · 节</span>
          </div>
          <div class="sum">
            <b>{{ Math.round((stats?.coverage || 0) * 100) }}%</b><span>占已上课时的比例</span>
          </div>
          <div class="sum" :class="{ red: (stats?.open_breaks || 0) > 0 }">
            <b>{{ stats?.open_breaks }}</b><span>还没接上的断点</span>
          </div>
          <div class="sum" :class="{ green: (stats?.fixed_breaks || 0) > 0 }">
            <b>{{ stats?.fixed_breaks }}</b><span>已经接上的断点</span>
          </div>
        </div>
        <p class="sum-line">
          <template v-if="hasAny">
            这学期你记了 <b>{{ stats?.recorded }}</b> 节，覆盖 <b>{{ stats?.courses }}</b> 门课；
            <template v-if="stats?.open_breaks">
              现在有 <b class="red-text">{{ stats?.open_breaks }}</b> 处断点还没补上。
            </template>
            <template v-else>目前没有连续掉队的段落。</template>
            <template v-if="stats?.fixed_breaks">
              另外有 {{ stats?.fixed_breaks }} 处断点在后面几节课自己接回来了——这件事值得记一笔。
            </template>
          </template>
          <template v-else>
            还没有课后记录。去课表点一节已经上过的课，记一句"听懂没有"，这条线就从那里开始。
          </template>
        </p>
      </div>

      <template v-if="data.advice.length">
        <RegionBand no="02" title="现在最值得做的几件事" tone="risk"
          :desc="'依据是你自己记的断点，不是模板建议'" />
        <div class="advice-grid">
          <div v-for="a in data.advice" :key="a.course + a.title" class="card advice" :class="a.kind">
            <div class="advice-head">
              <b>{{ a.title }}</b>
              <span class="tag">{{ a.course_name }}</span>
            </div>
            <p>{{ a.text }}</p>
            <div class="advice-foot">
              <span v-if="a.who">任课：{{ a.who }}</span>
              <span v-if="a.office_hour">答疑：{{ a.office_hour }}</span>
              <a v-if="a.email" :href="`mailto:${a.email}`">发邮件</a>
              <button class="link" @click="askAi(a.course_name)">问 AI 怎么补</button>
            </div>
          </div>
        </div>
      </template>

      <RegionBand :no="data.advice.length ? '03' : '02'" title="每门课一条线" tone="learn"
        :desc="`${data.courses.length} 门课 · 点任意一个点可以改那节课的记录`">
        <span v-if="!hasAny">
          <button class="ghost-btn" :disabled="seeding" @click="seed">
            {{ seeding ? "生成中…" : "生成示例记录（演示用）" }}
          </button>
        </span>
      </RegionBand>

      <div class="courses">
        <div v-for="t in data.courses" :key="t.code" class="card course" :class="t.status">
          <div class="course-head">
            <div class="ch-left">
              <b>{{ t.name }}</b>
              <span class="tiny muted">
                {{ t.code }} · {{ t.teacher }}<template v-if="t.room"> · {{ t.room }}</template>
                · {{ t.period }}
              </span>
            </div>
            <span class="status-pill" :class="STATUS[t.status].tone">{{ STATUS[t.status].label }}</span>
          </div>

          <p class="course-line" :class="t.status">{{ t.line }}</p>

          <div class="lane-wrap">
            <div class="lane" :style="{ '--n': t.points.length }">
              <div class="band-row">
                <span
                  v-for="(b, bi) in bands(t)"
                  :key="bi"
                  class="band"
                  :class="b.state"
                  :style="{ left: b.left, width: b.width }"
                ></span>
              </div>
              <div class="node-row">
                <div v-for="(p, i) in t.points" :key="p.index" class="slot">
                  <button
                    class="node"
                    :class="[p.state || 'none', { heal: healedIndexes(t).has(i), empty: !p.recorded }]"
                    :title="nodeTitle(t, i)"
                    @click="openPoint(t, i)"
                  >
                    <span v-if="healedIndexes(t).has(i)" class="heal-ring"></span>
                  </button>
                </div>
              </div>
              <div class="week-row">
                <div v-for="(p, i) in t.points" :key="'w' + p.index" class="wslot">
                  <em v-if="weekMarks(t).has(i)">{{ weekMarks(t).get(i) }}</em>
                </div>
              </div>
            </div>
            <div class="lane-legend">
              <span class="tiny muted">左 → 右：第 1 周到现在；数字是教学周</span>
            </div>
          </div>

          <div v-if="t.breaks.length" class="breaks">
            <div v-for="(b, bi) in t.breaks" :key="bi" class="brk" :class="{ open: b.open }">
              <span class="brk-dot"></span>
              <div class="brk-body">
                <b>
                  断点 · 第 {{ b.start_week }} 周（{{ md(b.start_date) }}）起连续 {{ b.count }} 节没听懂
                </b>
                <span class="tiny muted">
                  <template v-if="b.minute_from">从第 {{ b.minute_from }} 分钟开始没跟上</template>
                  <template v-if="b.point"> · 卡在「{{ b.point }}」</template>
                  <template v-if="b.open"> · 还没接上</template>
                  <template v-else> · 第 {{ b.recovered_week }} 周（{{ md(b.recovered_date || "") }}）接上了</template>
                </span>
              </div>
              <span class="brk-state" :class="b.open ? 'red' : 'green'">{{ b.open ? "未接上" : "已接上" }}</span>
            </div>
          </div>

          <div class="course-foot">
            <span class="tiny muted">
              已记录 {{ t.recorded }}/{{ t.held }} 节 ·
              听懂 {{ t.full }} · 模糊 {{ t.fuzzy }} · 没懂 {{ t.lost }}
            </span>
            <div class="foot-actions">
              <button class="link" @click="askAi(t.name)">问 AI</button>
              <button class="link" @click="router.push('/student/schedule')">去课表补记</button>
            </div>
          </div>
        </div>
      </div>

      <RegionBand :no="data.advice.length ? '04' : '03'" title="最近的记录" tone="archive"
        :desc="data.timeline.length ? `共 ${data.timeline.length} 条，按时间倒序` : '还没有记录'">
        <button class="link-btn" @click="router.push('/student/checkin')">全部记录 →</button>
      </RegionBand>

      <div class="card">
        <div v-if="!data.timeline.length" class="tl-empty">
          还没有记录。去课表点一节课，选"听懂了 / 有点模糊 / 没听懂"，这里就有内容了。
        </div>
        <div v-else class="mini-tl">
          <div v-for="r in data.timeline.slice(0, 8)" :key="r.id" class="mini-row" :class="r.state">
            <span class="mini-date">{{ md(r.date) }}</span>
            <span class="mini-course">{{ r.course_name }}</span>
            <span class="mini-state" :class="r.state">{{ r.state_label }}</span>
            <span class="mini-detail">
              <template v-if="r.break_label">{{ r.break_label }}</template>
              <template v-if="r.point"> · {{ r.point }}</template>
            </span>
          </div>
        </div>
      </div>

      <p class="tiny muted foot-note">
        学习轨迹的数据只用来回答"我从哪儿开始没跟上"，不进风险分、不进辅导员名单，
        也不作为任何处分的依据。断点接上了，环就在那儿留着。
      </p>

      <CheckinDialog
        v-model="dlgOpen"
        :sid="sid"
        :lesson="active"
        :record="activeRecord"
        :points="activePoints"
        :plans="meta?.plans"
        @saved="onSaved"
      />
    </template>
  </div>
</template>

<style scoped>
.legend {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 10.5px;
  color: var(--muted);
}
.legend span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
}
.dot.full {
  background: #047857;
}
.dot.fuzzy {
  background: #d97706;
}
.dot.lost {
  background: #dc2626;
}
.dot.none {
  background: #fff;
  border: 1px solid #d9c9b3;
}
.dot.heal {
  background: #fff;
  border: 2px solid #047857;
}

.sum-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.sum-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.sum {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 8px 12px;
  border-radius: 10px;
  background: #faf6ee;
}
.sum b {
  font-size: 22px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
  color: var(--text);
}
.sum span {
  font-size: 11px;
  color: var(--muted);
}
.sum.red b {
  color: var(--red);
}
.sum.green b {
  color: var(--green);
}
.sum-line {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.75;
  color: var(--text-2);
}
.sum-line b {
  font-weight: 600;
  color: var(--text);
}
.red-text {
  color: var(--red) !important;
}

.advice-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.advice {
  border-left: 3px solid #d97706;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.advice.break {
  border-left-color: var(--red);
}
.advice-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}
.advice-head b {
  font-size: 13px;
  color: var(--text);
  line-height: 1.45;
}
.advice p {
  margin: 0;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-2);
}
.tag {
  flex: none;
  font-size: 10.5px;
  padding: 1px 7px;
  border-radius: 99px;
  background: var(--brand-soft);
  color: var(--brand);
  white-space: nowrap;
}
.advice-foot {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  font-size: 11px;
  color: var(--muted);
  padding-top: 7px;
  border-top: 1px dashed var(--line);
}
.advice-foot a {
  color: var(--brand);
}
.link,
.link-btn {
  border: 0;
  background: transparent;
  color: var(--brand);
  font-size: 11px;
  font-weight: 600;
  padding: 0;
}

.ghost-btn {
  border: 1px dashed var(--line-strong);
  background: transparent;
  color: var(--text-2);
  font-size: 11.5px;
  padding: 3px 10px;
  border-radius: 999px;
}
.ghost-btn:disabled {
  opacity: 0.5;
}

.courses {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.course {
  padding: 14px 16px;
}
.course.break {
  border-left: 3px solid var(--red);
}
.course.watch {
  border-left: 3px solid #d97706;
}
.course.ok {
  border-left: 3px solid var(--green);
}
.course-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}
.ch-left {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.ch-left b {
  font-size: 13.5px;
  color: var(--text);
}
.status-pill {
  flex: none;
  font-size: 10.5px;
  padding: 1px 8px;
  border-radius: 99px;
  background: #f2e9da;
  color: var(--text-2);
  white-space: nowrap;
}
.status-pill.red {
  background: #fef2f2;
  color: var(--red);
}
.status-pill.amber {
  background: #fffbeb;
  color: var(--amber);
}
.status-pill.green {
  background: #ecfdf5;
  color: var(--green);
}
.course-line {
  margin: 6px 0 12px;
  font-size: 12px;
  color: var(--text-2);
  line-height: 1.6;
}
.course-line.break {
  color: var(--red);
}

.lane-wrap {
  position: relative;
}
.lane {
  position: relative;
  padding: 6px 0 0;
}
.band-row {
  position: absolute;
  left: 0;
  right: 0;
  top: 14px;
  height: 22px;
}
.band {
  position: absolute;
  top: 0;
  height: 22px;
  opacity: 0.5;
  border-radius: 6px;
}
.band.lost {
  background: rgba(220, 38, 38, 0.24);
}
.band.fuzzy {
  background: rgba(217, 119, 6, 0.2);
}
.band.full {
  background: rgba(4, 120, 87, 0.16);
}
.band.none {
  background: transparent;
  border: 1px dashed rgba(217, 201, 179, 0.7);
}
.node-row {
  position: relative;
  display: flex;
  align-items: center;
}
.node-row::before {
  content: "";
  position: absolute;
  left: 6px;
  right: 6px;
  top: 50%;
  height: 1px;
  background: var(--line);
  transform: translateY(-50%);
}
.slot {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  justify-content: center;
  position: relative;
  z-index: 1;
}
.node {
  position: relative;
  width: 13px;
  height: 13px;
  border-radius: 50%;
  border: 2px solid #fff;
  background: #fff;
  padding: 0;
  box-shadow: 0 0 0 1px #d9c9b3;
  transition: transform 0.12s;
}
.node:hover {
  transform: scale(1.35);
}
.node.empty {
  background: #fff;
  box-shadow: 0 0 0 1px #e3d6c4;
}
.node.full {
  background: #047857;
  box-shadow: 0 0 0 1px #047857;
}
.node.fuzzy {
  background: #d97706;
  box-shadow: 0 0 0 1px #d97706;
}
.node.lost {
  background: #dc2626;
  box-shadow: 0 0 0 1px #dc2626;
}
.heal-ring {
  position: absolute;
  inset: -5px;
  border-radius: 50%;
  border: 1.5px solid #047857;
  opacity: 0.55;
}
.week-row {
  display: flex;
  margin-top: 7px;
}
.wslot {
  flex: 1 1 0;
  min-width: 0;
  text-align: center;
}
.wslot em {
  font-style: normal;
  font-size: 9.5px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.lane-legend {
  margin-top: 2px;
}

.breaks {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.brk {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 8px 11px;
  border-radius: 9px;
  background: #faf6ee;
  border: 1px solid var(--line);
}
.brk.open {
  background: #fef7f7;
  border-color: rgba(220, 38, 38, 0.2);
}
.brk-dot {
  flex: none;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-top: 6px;
  background: var(--green);
}
.brk.open .brk-dot {
  background: var(--red);
}
.brk-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.brk-body b {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.5;
}
.brk-state {
  flex: none;
  font-size: 10px;
  padding: 1px 7px;
  border-radius: 99px;
  white-space: nowrap;
}
.brk-state.red {
  background: #fef2f2;
  color: var(--red);
}
.brk-state.green {
  background: #ecfdf5;
  color: var(--green);
}
.course-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 11px;
  padding-top: 9px;
  border-top: 1px dashed var(--line);
}
.foot-actions {
  display: flex;
  gap: 12px;
}

.tl-empty {
  padding: 14px 0;
  text-align: center;
  font-size: 12.5px;
  color: var(--muted);
}
.mini-tl {
  display: flex;
  flex-direction: column;
}
.mini-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 7px 0;
  border-bottom: 1px dashed var(--line);
  font-size: 12px;
  min-width: 0;
}
.mini-row:last-child {
  border-bottom: 0;
}
.mini-date {
  flex: none;
  width: 66px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.mini-course {
  flex: none;
  width: 132px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mini-state {
  flex: none;
  font-size: 10.5px;
  padding: 0 7px;
  border-radius: 99px;
  background: #f2e9da;
  color: var(--text-2);
}
.mini-state.full {
  background: #ecfdf5;
  color: var(--green);
}
.mini-state.fuzzy {
  background: #fffbeb;
  color: var(--amber);
}
.mini-state.lost {
  background: #fef2f2;
  color: var(--red);
}
.mini-detail {
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.foot-note {
  margin: 14px 2px 4px;
  line-height: 1.7;
}
@media (max-width: 900px) {
  .sum-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .advice-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-width: 760px) {
  .mini-date {
    width: 58px;
  }
  .mini-course {
    width: 96px;
  }
  .mini-detail {
    display: none;
  }
}
</style>
