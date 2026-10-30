<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus/es/components/message/index";
import { ElMessageBox } from "element-plus/es/components/message-box/index";
import { useRouter } from "vue-router";
import { api } from "@/api/client";
import CheckinDialog from "@/components/CheckinDialog.vue";
import RegionBand from "@/components/RegionBand.vue";
import { useAuthStore } from "@/stores/auth";
import type { CheckinList, CheckinRecord, TrackPayload } from "@/types";

/**
 * 课后打卡。
 * 两条线：上面是"还没记的课"（补录入口），下面是"记过的课"（可改可删）。
 * 记录本身不进风险分，这一点在页面上明说——不惩罚诚实，是这个模块的前提。
 */
const auth = useAuthStore();
const router = useRouter();
const sid = computed(() => auth.profile?.sid || "");

const track = ref<TrackPayload | null>(null);
const meta = ref<CheckinList | null>(null);
const loading = ref(true);
const error = ref("");
const seeding = ref(false);

async function load() {
  if (!sid.value) return;
  loading.value = true;
  error.value = "";
  try {
    const [t, m] = await Promise.all([api.track(sid.value), api.checkins(sid.value)]);
    track.value = t;
    meta.value = m;
  } catch (e: any) {
    error.value = e?.message || "加载失败";
  } finally {
    loading.value = false;
  }
}

watch(() => sid.value, () => load(), { immediate: true });

const stats = computed(() => track.value?.stats);

/* ---------------- 记录 / 修改 ---------------- */
const dlgOpen = ref(false);
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
const activeRecord = ref<CheckinRecord | null>(null);

function recordLesson(d: TrackPayload["due"][number]) {
  active.value = {
    course: d.course,
    name: d.course_name,
    teacher: d.teacher,
    room: d.room,
    date: d.date,
    week: d.week,
    weekday_label: d.weekday,
    period: d.period,
  };
  activeRecord.value = null;
  dlgOpen.value = true;
}

function editRecord(r: CheckinRecord) {
  active.value = {
    course: r.course,
    name: r.course_name,
    teacher: r.teacher,
    room: r.room,
    date: r.date,
    week: r.week,
    weekday_label: r.weekday || "",
    period: r.period,
  };
  activeRecord.value = r;
  dlgOpen.value = true;
}

const activePoints = computed(() => meta.value?.points?.[active.value?.course || ""] || []);

function onSaved() {
  load();
}

async function remove(r: CheckinRecord) {
  try {
    await ElMessageBox.confirm(
      `删除后这条记录不会出现在学习轨迹里，确定删除「${r.course_name} · ${r.date}」这条记录吗？`,
      "删除记录",
      { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" },
    );
  } catch {
    return;
  }
  try {
    await api.deleteCheckin(sid.value, r.id);
    ElMessage.success("已删除");
    load();
  } catch (e: any) {
    ElMessage.error(e?.message || "删除失败");
  }
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
function mdShort(iso: string) {
  return iso.slice(5).replace("-", "/");
}
</script>

<template>
  <div class="page">
    <div v-if="loading && !track" class="card"><div class="skeleton" style="height: 240px"></div></div>

    <div v-else-if="error" class="card">
      <b>加载失败</b>
      <p class="tiny muted">{{ error }}</p>
      <button class="btn" @click="load">重试</button>
    </div>

    <template v-else-if="track">
      <RegionBand no="01" title="课后打卡" tone="learn"
        :desc="`10 秒记一句：这节课听懂没有、从第几分钟开始没懂。已有 ${stats?.recorded} 条记录，覆盖 ${stats?.courses} 门课`">
        <button class="link-btn" @click="router.push('/student/schedule')">从课表记录 →</button>
      </RegionBand>

      <div class="card stat-card">
        <div class="s">
          <b>{{ stats?.recorded }}</b><span>已记录 · 节</span>
        </div>
        <div class="s" :class="{ warn: (stats?.due || 0) > 0 }">
          <b>{{ stats?.due }}</b><span>还没记 · 节</span>
        </div>
        <div class="s" :class="{ red: (stats?.open_breaks || 0) > 0 }">
          <b>{{ stats?.open_breaks }}</b><span>没接上的断点</span>
        </div>
        <div class="s">
          <b>{{ stats?.streak }}</b><span>最近连续记录 · 节</span>
        </div>
        <p class="stat-note">
          记录只服务你自己：<b>说"没听懂"不会扣分</b>，也进不了预警公式。它只决定你在下一节课之前，
          知不知道该补哪一小块。
        </p>
      </div>

      <RegionBand no="02" title="还没记的课" tone="archive"
        :desc="track.due.length ? `共 ${track.due.length} 节，越近的越记得住` : '全部记完了，保持住'">
        <span v-if="stats?.week_due" class="band-hint">本周 {{ stats.week_done }}/{{ stats.week_due }}</span>
      </RegionBand>

      <div class="card">
        <div v-if="!track.due.length" class="empty">
          最近上过的课都记完了。下一节下课后再来。
        </div>
        <div v-else class="due-list">
          <button v-for="d in track.due.slice(0, 10)" :key="`${d.course}${d.date}${d.period}`" class="due"
            @click="recordLesson(d)">
            <div class="due-when">
              <b>{{ mdShort(d.date) }}</b>
              <span class="tiny muted">{{ d.weekday }} · 第 {{ d.week }} 周</span>
            </div>
            <div class="due-what">
              <b>{{ d.course_name }}</b>
              <span class="tiny muted">{{ d.period }} · {{ d.room }} · {{ d.teacher }}</span>
            </div>
            <div class="due-side">
              <span v-if="d.today" class="pill on">今天</span>
              <span class="due-btn">记一下</span>
            </div>
          </button>
        </div>
      </div>

      <RegionBand no="03" title="记录过的课" tone="learn"
        :desc="track.timeline.length ? '点任意一条可以改；记录只属于你自己' : '还没有记录'">
        <button v-if="!track.timeline.length" class="ghost-btn" :disabled="seeding" @click="seed">
          {{ seeding ? "生成中…" : "生成示例记录（演示用）" }}
        </button>
      </RegionBand>

      <div v-if="!track.timeline.length" class="card empty-card">
        <b>还没有任何课后记录</b>
        <p class="tiny muted">
          从课表点一节已经上过的课，选"听懂了 / 有点模糊 / 没听懂"，10 秒就能记完。
          记满几周后，这里会变成一条能看到自己走向的轨迹。
        </p>
        <div class="empty-actions">
          <button class="btn primary" @click="router.push('/student/schedule')">去课表挑一节课</button>
          <button class="btn ghost" :disabled="seeding" @click="seed">先生成示例数据看看效果</button>
        </div>
        <p class="tiny muted demo-note">
          示例数据按你的期中成绩生成（低分课会有连续没听懂的段落），用来演示轨迹的样子，随时可以删。
        </p>
      </div>

      <div v-else class="card">
        <div class="tl">
          <div v-for="r in track.timeline" :key="r.id" class="tl-row" :class="r.state">
            <div class="tl-date">
              <b>{{ md(r.date) }}</b>
              <span class="tiny muted">{{ r.weekday }} · 第 {{ r.week }} 周 · {{ r.period }}</span>
            </div>
            <div class="tl-body">
              <div class="tl-title">
                <b>{{ r.course_name }}</b>
                <span class="pill" :class="r.state">{{ r.state_label }}</span>
                <span v-if="r.break_label" class="tl-break">{{ r.break_label }}</span>
              </div>
              <div class="tl-meta">
                <span v-if="r.point" class="tl-point">卡在「{{ r.point }}」</span>
                <span v-if="r.plan_label && r.plan !== 'none'" class="tl-plan">打算：{{ r.plan_label }}</span>
              </div>
              <p v-if="r.note" class="tl-note">{{ r.note }}</p>
            </div>
            <div class="tl-actions">
              <button class="mini" @click="editRecord(r)">改</button>
              <button class="mini danger" @click="remove(r)">删</button>
            </div>
          </div>
        </div>
      </div>

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
.stat-card {
  display: flex;
  align-items: center;
  gap: 26px;
  flex-wrap: wrap;
}
.s {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.s b {
  font-size: 22px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text);
  line-height: 1.2;
}
.s span {
  font-size: 11px;
  color: var(--muted);
}
.s.warn b {
  color: var(--brand);
}
.s.red b {
  color: var(--red);
}
.stat-note {
  flex: 1 1 260px;
  margin: 0;
  padding-left: 18px;
  border-left: 1px dashed var(--line);
  font-size: 11.5px;
  line-height: 1.65;
  color: var(--muted);
}
.stat-note b {
  color: var(--text-2);
  font-weight: 600;
}
.band-hint {
  font-size: 11.5px;
  color: var(--muted);
}
.link-btn,
.ghost-btn {
  border: 0;
  background: transparent;
  color: var(--brand);
  font-size: 11.5px;
  font-weight: 600;
  padding: 0;
}
.ghost-btn {
  color: var(--text-2);
  border: 1px dashed var(--line-strong);
  border-radius: 999px;
  padding: 3px 10px;
  font-weight: 400;
}
.ghost-btn:disabled {
  opacity: 0.5;
}

.empty {
  padding: 14px 0;
  text-align: center;
  font-size: 12.5px;
  color: var(--muted);
}
.due-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.due {
  display: grid;
  grid-template-columns: 92px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 9px 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fff;
  text-align: left;
  transition: border-color 0.12s, background 0.12s;
}
.due:hover {
  border-color: var(--line-strong);
  background: #fffdf9;
}
.due-when,
.due-what {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.due-when b {
  font-size: 12.5px;
  color: var(--text);
}
.due-what b {
  font-size: 13px;
  color: var(--text);
}
.due-side {
  display: flex;
  align-items: center;
  gap: 8px;
}
.due-btn {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--brand);
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid rgba(217, 119, 6, 0.28);
  white-space: nowrap;
}
.pill {
  font-size: 10.5px;
  padding: 1px 7px;
  border-radius: 99px;
  background: #f2e9da;
  color: var(--text-2);
  white-space: nowrap;
}
.pill.on {
  background: var(--brand-soft);
  color: var(--brand);
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

.empty-card {
  text-align: center;
  padding: 26px 20px;
}
.empty-card b {
  font-size: 14px;
}
.empty-card p {
  max-width: 460px;
  margin: 6px auto 0;
  line-height: 1.7;
}
.empty-actions {
  display: flex;
  justify-content: center;
  gap: 8px;
  margin-top: 14px;
  flex-wrap: wrap;
}
.demo-note {
  margin-top: 10px !important;
  opacity: 0.85;
}

.tl {
  display: flex;
  flex-direction: column;
}
.tl-row {
  display: grid;
  grid-template-columns: 132px minmax(0, 1fr) auto;
  gap: 12px;
  padding: 11px 0;
  border-bottom: 1px dashed var(--line);
}
.tl-row:last-child {
  border-bottom: 0;
}
.tl-date {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding-left: 10px;
  border-left: 3px solid #d9c9b3;
}
.tl-row.full .tl-date {
  border-left-color: #047857;
}
.tl-row.fuzzy .tl-date {
  border-left-color: #d97706;
}
.tl-row.lost .tl-date {
  border-left-color: #dc2626;
}
.tl-date b {
  font-size: 12.5px;
  color: var(--text);
}
.tl-body {
  min-width: 0;
}
.tl-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.tl-title b {
  font-size: 13px;
  color: var(--text);
}
.tl-break {
  font-size: 11px;
  color: #b45309;
}
.tl-meta {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 3px;
  font-size: 11.5px;
  color: var(--text-2);
}
.tl-point {
  color: #b45309;
}
.tl-note {
  margin: 5px 0 0;
  font-size: 11.5px;
  color: var(--muted);
  line-height: 1.6;
}
.tl-actions {
  display: flex;
  gap: 4px;
  align-items: flex-start;
}
.mini {
  border: 1px solid var(--line);
  background: #fff;
  color: var(--text-2);
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 999px;
}
.mini:hover {
  border-color: var(--brand);
  color: var(--brand);
}
.mini.danger:hover {
  border-color: var(--red);
  color: var(--red);
}
@media (max-width: 760px) {
  .stat-note {
    padding-left: 0;
    border-left: 0;
    padding-top: 10px;
    border-top: 1px dashed var(--line);
  }
  .tl-row {
    grid-template-columns: minmax(0, 1fr) auto;
  }
  .tl-date {
    grid-column: 1 / -1;
    flex-direction: row;
    align-items: baseline;
    gap: 8px;
  }
}
</style>
