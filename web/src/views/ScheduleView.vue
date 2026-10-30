<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus/es/components/message/index";
import { useRouter } from "vue-router";
import { api } from "@/api/client";
import CheckinDialog from "@/components/CheckinDialog.vue";
import RegionBand from "@/components/RegionBand.vue";
import { useAuthStore } from "@/stores/auth";
import type { CheckinList, CheckinRecord, LessonSlot, TimetablePayload } from "@/types";

/**
 * 我的课表。
 * 课表不只是一张"什么时候在哪上课"的表格——每节课的格子上带着"记过没有"，
 * 所以它同时是课后记录的入口：点一下格子就能记这节课的状态。
 */
const auth = useAuthStore();
const router = useRouter();
const sid = computed(() => auth.profile?.sid || "");

const data = ref<TimetablePayload | null>(null);
const meta = ref<CheckinList | null>(null);
const week = ref(0);
const loading = ref(true);
const error = ref("");

async function load(w?: number) {
  if (!sid.value) return;
  loading.value = true;
  error.value = "";
  try {
    const payload = await api.timetable(sid.value, w || undefined);
    data.value = payload;
    week.value = payload.week;
    if (!meta.value) meta.value = await api.checkins(sid.value);
  } catch (e: any) {
    error.value = e?.message || "加载失败";
  } finally {
    loading.value = false;
  }
}

watch(() => sid.value, () => load(), { immediate: true });

const maxWeek = computed(() => data.value?.weeks.max || 16);
const current = computed(() => data.value?.weeks.current || 1);

function go(w: number) {
  if (w < 1 || w > maxWeek.value) return;
  load(w);
}

/* ---------------- 记录弹窗 ---------------- */
const dlgOpen = ref(false);
const active = ref<LessonSlot | null>(null);
const activeRecord = ref<CheckinRecord | null>(null);

function openLesson(slot: LessonSlot) {
  if (!slot.held) {
    ElMessage.info("这节课还没上，上完当天的课再来记");
    return;
  }
  active.value = slot;
  const found = meta.value?.rows.find((r) => r.id === slot.checkin_id);
  activeRecord.value = found || null;
  dlgOpen.value = true;
}

const activePoints = computed(() => {
  const code = active.value?.course || "";
  return meta.value?.points?.[code] || [];
});

function onSaved(row: CheckinRecord) {
  if (data.value) {
    for (const s of data.value.slots) {
      if (s.course === row.course && s.date === row.date && s.period === row.period) {
        s.recorded = true;
        s.state = row.state;
        s.state_label = row.state_label;
        s.break_label = row.break_label;
        s.point = row.point;
        s.checkin_id = row.id;
      }
    }
    data.value.stats.checked = data.value.slots.filter((s) => s.held && s.recorded).length;
    data.value.stats.pending = data.value.slots.filter((s) => s.held && !s.recorded).length;
  }
  api.checkins(sid.value).then((r) => (meta.value = r)).catch(() => {});
}

function cell(dayKey: number, period: string): LessonSlot[] {
  return data.value?.cells[`${dayKey}@${period}`] || [];
}

// 越近的课越值得记：倒序，今天没记的排最前
const pending = computed(() =>
  (data.value?.slots || [])
    .filter((s) => s.held && !s.recorded)
    .sort((a, b) => b.date.localeCompare(a.date) || b.period.localeCompare(a.period)),
);
const todayList = computed(() => (data.value?.slots || []).filter((s) => s.today));

const STATE_LABEL: Record<string, string> = { full: "听懂", fuzzy: "模糊", lost: "没懂" };

function dayNumber(iso: string) {
  return iso.slice(5).replace("-", "/");
}
</script>

<template>
  <div class="page">
    <div v-if="loading && !data" class="card"><div class="skeleton" style="height: 320px"></div></div>

    <div v-else-if="error" class="card">
      <b>加载失败</b>
      <p class="tiny muted">{{ error }}</p>
      <button class="btn" @click="load(week)">重试</button>
    </div>

    <template v-else-if="data">
      <RegionBand no="01" title="本周课表" tone="learn"
        :desc="`${data.term} · 第 ${data.week} 周 · 今天是 ${dayNumber(data.today)}`">
        <div class="week-switch">
          <button class="wk-btn" :disabled="week <= 1" @click="go(week - 1)">上一周</button>
          <button class="wk-btn" :class="{ on: week === current }" @click="go(current)">
            第 {{ week }} 周<template v-if="week === current"> · 本周</template>
          </button>
          <button class="wk-btn" :disabled="week >= maxWeek" @click="go(week + 1)">下一周</button>
        </div>
      </RegionBand>

      <div class="card tt-card">
        <div class="tt-stats">
          <div class="tt-stat">
            <b>{{ data.stats.total }}</b><span>本周课程</span>
          </div>
          <div class="tt-stat">
            <b>{{ data.stats.held }}</b><span>已经上过</span>
          </div>
          <div class="tt-stat ok">
            <b>{{ data.stats.checked }}</b><span>已记录</span>
          </div>
          <div class="tt-stat warn">
            <b>{{ data.stats.pending }}</b><span>待记录</span>
          </div>
          <div class="tt-legend">
            <span><i class="dot full"></i>听懂</span>
            <span><i class="dot fuzzy"></i>模糊</span>
            <span><i class="dot lost"></i>没懂</span>
            <span><i class="dot none"></i>还没记</span>
          </div>
        </div>

        <div class="tt-scroll">
          <div class="grid" :style="{ gridTemplateColumns: `72px repeat(${data.days.length}, minmax(148px, 1fr))` }">
            <div class="gh corner">节次</div>
            <div v-for="d in data.days" :key="d.key" class="gh day" :class="{ today: d.today }">
              <b>{{ d.label }}</b>
              <em>{{ dayNumber(d.date) }}</em>
              <span v-if="d.today" class="today-tag">今天</span>
            </div>

            <template v-for="p in data.periods" :key="p">
              <div class="period">{{ p }}</div>
              <div v-for="d in data.days" :key="`${d.key}-${p}`" class="cell" :class="{ today: d.today }">
                <button
                  v-for="s in cell(d.key, p)"
                  :key="s.course + s.period"
                  class="lesson"
                  :class="[s.state || 'none', { future: !s.held }]"
                  @click="openLesson(s)"
                >
                  <div class="lesson-top">
                    <b>{{ s.name }}</b>
                    <span v-if="s.held" class="lesson-state" :class="s.state || 'none'">
                      {{ s.recorded ? STATE_LABEL[s.state] : "待记" }}
                    </span>
                    <span v-else class="lesson-state future">未开始</span>
                  </div>
                  <div class="lesson-meta">
                    <span>{{ s.room }}</span>
                    <span class="muted">{{ s.teacher }}</span>
                  </div>
                  <div v-if="s.recorded && s.point" class="lesson-point">
                    {{ s.break_label || "跟上了" }}<template v-if="s.point"> · {{ s.point }}</template>
                  </div>
                  <div v-else-if="s.held" class="lesson-cta">点一下记这节课 →</div>
                </button>
              </div>
            </template>
          </div>
        </div>

        <p class="tiny muted tt-note">
          课表由教务排课生成，和「学情总览 → 课堂考勤」里的每一条记录是同一份数据。
          已经上过的课点开就能记录，记完去「学习轨迹」看这条线怎么走。
        </p>
      </div>

      <RegionBand no="02" title="今天这几节" tone="learn"
        :desc="todayList.length ? `共 ${todayList.length} 节，${todayList.filter((s) => s.recorded).length} 节已记录` : '今天没有课'">
        <button class="link-btn" @click="router.push('/student/track')">去看学习轨迹 →</button>
      </RegionBand>

      <div class="card">
        <div v-if="!todayList.length" class="empty">今天没排课，去把之前没记的补上吧。</div>
        <div v-else class="today-list">
          <button v-for="s in todayList" :key="s.course + s.period" class="today-item" :class="s.state || 'none'"
            @click="openLesson(s)">
            <div class="ti-when">
              <b>{{ s.period }}</b>
              <span class="tiny muted">{{ s.room }}</span>
            </div>
            <div class="ti-what">
              <b>{{ s.name }}</b>
              <span class="tiny muted">{{ s.teacher }} · {{ s.kind }} · {{ s.credit }} 学分</span>
            </div>
            <div class="ti-side">
              <span v-if="s.recorded" class="pill" :class="s.state">{{ s.state_label }}</span>
              <span v-else-if="s.held" class="pill warn">待记录</span>
              <span v-else class="pill">未开始</span>
            </div>
          </button>
        </div>
      </div>

      <template v-if="pending.length">
        <RegionBand no="03" title="还没记的课" tone="archive"
          :desc="`共 ${pending.length} 节，越近的越值得记——隔久了就想不起来从哪儿开始没懂了`" />
        <div class="card">
          <div class="due-list">
            <button v-for="s in pending.slice(0, 8)" :key="s.course + s.date + s.period" class="due-item" @click="openLesson(s)">
              <div class="di-date">
                <b>{{ dayNumber(s.date) }}</b>
                <span class="tiny muted">{{ s.weekday_label }} · 第 {{ s.week }} 周</span>
              </div>
              <div class="di-what">
                <b>{{ s.name }}</b>
                <span class="tiny muted">{{ s.period }} · {{ s.room }}</span>
              </div>
              <span class="di-btn">记一下</span>
            </button>
          </div>
        </div>
      </template>

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
.tt-card {
  padding: 14px 16px 12px;
}
.tt-stats {
  display: flex;
  align-items: center;
  gap: 18px;
  flex-wrap: wrap;
  padding-bottom: 12px;
  border-bottom: 1px dashed var(--line);
  margin-bottom: 12px;
}
.tt-stat {
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.tt-stat b {
  font-size: 19px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text);
}
.tt-stat span {
  font-size: 11.5px;
  color: var(--muted);
}
.tt-stat.ok b {
  color: var(--green);
}
.tt-stat.warn b {
  color: var(--brand);
}
.tt-legend {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 11px;
  color: var(--muted);
  flex-wrap: wrap;
}
.tt-legend span {
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
  background: #d9c9b3;
}

.tt-scroll {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  padding-bottom: 4px;
}
.grid {
  display: grid;
  gap: 6px;
  min-width: 640px;
}
.gh {
  font-size: 11.5px;
  color: var(--muted);
  padding: 6px 4px;
  text-align: center;
}
.gh.corner {
  text-align: left;
  padding-left: 8px;
}
.gh.day {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 6px;
  border-radius: 8px;
  background: #faf6ee;
  position: relative;
}
.gh.day b {
  font-size: 12.5px;
  color: var(--text);
}
.gh.day em {
  font-style: normal;
  font-size: 11px;
  color: var(--muted);
}
.gh.day.today {
  background: #fdf1de;
}
.today-tag {
  position: absolute;
  top: -7px;
  right: 6px;
  font-size: 9.5px;
  padding: 0 5px;
  border-radius: 99px;
  background: var(--brand);
  color: #fff;
  line-height: 15px;
}
.period {
  display: grid;
  place-items: center;
  font-size: 11px;
  color: var(--muted);
  background: #faf6ee;
  border-radius: 8px;
  padding: 6px 2px;
  letter-spacing: 0.2px;
}
.cell {
  min-height: 74px;
  border: 1px dashed rgba(234, 223, 205, 0.9);
  border-radius: 10px;
  padding: 3px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.cell.today {
  background: rgba(253, 241, 222, 0.45);
  border-color: #f0d9b5;
}
.lesson {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 7px 9px;
  border-radius: 8px;
  border: 1px solid var(--line);
  border-left: 3px solid #d9c9b3;
  background: #fff;
  text-align: left;
  transition: transform 0.12s, box-shadow 0.12s, border-color 0.12s;
}
.lesson:hover {
  box-shadow: var(--shadow);
  transform: translateY(-1px);
}
.lesson.full {
  border-left-color: #047857;
  background: linear-gradient(180deg, #f6fefb, #fff);
}
.lesson.fuzzy {
  border-left-color: #d97706;
  background: linear-gradient(180deg, #fffdf5, #fff);
}
.lesson.lost {
  border-left-color: #dc2626;
  background: linear-gradient(180deg, #fff7f7, #fff);
}
.lesson.future {
  background: #fbf8f2;
  border-style: dashed;
  opacity: 0.9;
}
.lesson-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 6px;
}
.lesson-top b {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.35;
}
.lesson-state {
  flex: none;
  font-size: 9.5px;
  padding: 1px 5px;
  border-radius: 99px;
  background: #f2e9da;
  color: var(--muted);
  white-space: nowrap;
}
.lesson-state.full {
  background: #ecfdf5;
  color: #047857;
}
.lesson-state.fuzzy {
  background: #fffbeb;
  color: #b45309;
}
.lesson-state.lost {
  background: #fef2f2;
  color: #dc2626;
}
.lesson-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 8px;
  font-size: 10.5px;
  color: var(--text-2);
  line-height: 1.5;
}
.lesson-point {
  font-size: 10.5px;
  color: #b45309;
  line-height: 1.45;
}
.lesson-cta {
  font-size: 10.5px;
  color: var(--muted);
  opacity: 0;
  transition: opacity 0.12s;
}
.lesson:hover .lesson-cta {
  opacity: 1;
}
.tt-note {
  margin: 12px 0 0;
  padding-top: 10px;
  border-top: 1px dashed var(--line);
  line-height: 1.6;
}

.week-switch {
  display: flex;
  gap: 4px;
  background: #faf6ee;
  padding: 2px;
  border-radius: 999px;
  border: 1px solid var(--line);
}
.wk-btn {
  border: 0;
  background: transparent;
  font-size: 11.5px;
  color: var(--text-2);
  padding: 3px 10px;
  border-radius: 999px;
}
.wk-btn:hover:not(:disabled) {
  background: #fff;
}
.wk-btn:disabled {
  opacity: 0.4;
  cursor: default;
}
.wk-btn.on {
  background: #fff;
  color: var(--brand);
  font-weight: 600;
  box-shadow: var(--shadow);
}
.link-btn {
  border: 0;
  background: transparent;
  color: var(--brand);
  font-size: 11.5px;
  font-weight: 600;
  padding: 0;
}

.empty {
  padding: 16px 0;
  text-align: center;
  font-size: 12.5px;
  color: var(--muted);
}
.today-list,
.due-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.today-item,
.due-item {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 9px 12px;
  border: 1px solid var(--line);
  border-left: 3px solid #d9c9b3;
  border-radius: 10px;
  background: #fff;
  text-align: left;
  transition: border-color 0.12s, background 0.12s;
}
.due-item {
  grid-template-columns: 92px minmax(0, 1fr) auto;
}
.today-item:hover,
.due-item:hover {
  border-color: var(--line-strong);
  background: #fffdf9;
}
.today-item.full {
  border-left-color: #047857;
}
.today-item.fuzzy {
  border-left-color: #d97706;
}
.today-item.lost {
  border-left-color: #dc2626;
}
.ti-when,
.ti-what,
.di-date,
.di-what {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.ti-when b,
.di-date b {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text);
}
.ti-what b,
.di-what b {
  font-size: 13px;
  color: var(--text);
}
.pill {
  font-size: 11px;
  padding: 2px 9px;
  border-radius: 999px;
  background: #f2e9da;
  color: var(--text-2);
  white-space: nowrap;
}
.pill.full {
  background: #ecfdf5;
  color: #047857;
}
.pill.fuzzy {
  background: #fffbeb;
  color: #b45309;
}
.pill.lost {
  background: #fef2f2;
  color: #dc2626;
}
.pill.warn {
  background: var(--brand-soft);
  color: var(--brand);
}
.di-btn {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--brand);
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid rgba(217, 119, 6, 0.28);
  background: #fff;
  white-space: nowrap;
}
@media (max-width: 760px) {
  .today-item,
  .due-item {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 4px 10px;
  }
  .ti-what,
  .di-what {
    grid-column: 1 / -1;
  }
  .tt-legend {
    margin-left: 0;
    width: 100%;
  }
}
</style>
