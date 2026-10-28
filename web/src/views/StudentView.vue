<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus/es/components/message/index";
import { api } from "@/api/client";
import ActionList from "@/components/ActionList.vue";
import ChatHome from "@/components/ChatHome.vue";
import CourseTrend from "@/components/CourseTrend.vue";
import DashNav from "@/components/DashNav.vue";
import FactorBars from "@/components/FactorBars.vue";
import GradeTrend from "@/components/GradeTrend.vue";
import RiskRing from "@/components/RiskRing.vue";
import { useAppStore } from "@/stores/app";
import { useAuthStore } from "@/stores/auth";
import { useChatStore } from "@/stores/chat";
import type { AttendanceRecord, Course, HomeworkRecord, StudentDetail } from "@/types";

const app = useAppStore();
const auth = useAuthStore();
const chat = useChatStore();
const detail = ref<StudentDetail | null>(null);
const loading = ref(true);
const error = ref("");
const appeal = reactive({
  open: false,
  text: "",
  sending: false,
  kind: "attendance" as "attendance" | "homework",
  record_id: "",
  course: "",
});

/** 对某条考勤/作业记录发起异议：预填课程与记录，弹开表单 */
function openAppeal(kind: "attendance" | "homework", record: { id?: string; date?: string; period?: string }, course: string) {
  appeal.kind = kind;
  appeal.course = course;
  appeal.record_id = record.id || (record.date && record.period ? `${course}-${record.date}-${record.period}` : course);
  appeal.text = "";
  appeal.open = true;
  document.querySelector(".appeal-form")?.scrollIntoView({ behavior: "smooth", block: "center" });
}

// 学号来自登录身份，不再读演示数据
const sid = computed(() => auth.profile?.sid || "");

async function load() {
  if (!sid.value) return;
  loading.value = true;
  error.value = "";
  try {
    detail.value = await api.student(sid.value);
  } catch (e: any) {
    error.value = e?.message || "加载失败";
  } finally {
    loading.value = false;
  }
}

watch(() => auth.profile?.sid, (v) => v && load(), { immediate: true });

const facts = computed(() => {
  const d = detail.value;
  if (!d) return [];
  const r = d.risk;
  return [
    { value: `${r.raw.absent} 次`, label: `缺勤次数 · ${r.raw.sessions} 次课中` },
    { value: `${r.raw.hw_submitted}/${r.raw.hw_assigned}`, label: "作业提交 · 本学期" },
    { value: r.raw.mid_avg, label: `期中均分 · 班级 ${r.raw.cohort_avg}` },
    { value: d.student.history.failed_credits, label: "累计挂科 · 学分" },
  ];
});

function failOf(course: Course) {
  const p = detail.value?.risk.pass_probability.find((x) => x.code === course.code);
  return p ? p.fail_probability : 0;
}
function failColor(p: number) {
  return p > 0.5 ? "var(--red)" : p > 0.25 ? "#d97706" : "var(--green)";
}

/* ---------------- 成绩走势 ---------------- */
const gradeTrend = computed(() => detail.value?.grade_trend || null);

const courseTrends = computed(() => gradeTrend.value?.courses || []);

function deltaLabel(d: number) {
  if (d > 0) return `+${d}`;
  return `${d}`;
}

/* ---------------- 考勤 / 作业 / 老师 ---------------- */
const onlyIssue = ref(true);

const myCourses = computed(() => detail.value?.courses || []);
const extraCourses = computed(() => detail.value?.extra_courses || []);

// 把每门课的考勤摊平成一条条记录：学生要看到"哪天、哪门课、第几节"
const allAttendance = computed(() => {
  const rows: (AttendanceRecord & { course: string; code: string })[] = [];
  for (const c of myCourses.value) {
    for (const a of c.attendance || []) {
      rows.push({ ...a, course: c.name, code: c.code });
    }
  }
  if (onlyIssue.value) return rows.filter((r) => r.status !== "present").sort((a, b) => b.date.localeCompare(a.date));
  return rows.sort((a, b) => b.date.localeCompare(a.date) || a.course.localeCompare(b.course));
});

const attendanceStats = computed(() => {
  let absent = 0;
  let late = 0;
  for (const c of myCourses.value) {
    absent += c.absent || 0;
    late += c.late || 0;
  }
  return { absent, late };
});

// 作业按「没交 → 迟交 → 已交」排，没交的永远在最前面
const allHomework = computed(() => {
  const rank: Record<string, number> = { missing: 0, late: 1, submitted: 2 };
  const rows = [] as (HomeworkRecord & { course: string; code: string })[];
  for (const c of myCourses.value) {
    for (const h of c.homework || []) {
      rows.push({ ...h, course: c.name, code: c.code });
    }
  }
  return rows.sort((a, b) => (rank[a.status] ?? 3) - (rank[b.status] ?? 3) || b.due.localeCompare(a.due));
});

const homeworkStats = computed(() => {
  const rows = allHomework.value;
  return {
    missing: rows.filter((r) => r.status === "missing").length,
    late: rows.filter((r) => r.status === "late").length,
    submitted: rows.filter((r) => r.status === "submitted").length,
  };
});

const ATTEND_LABEL: Record<string, string> = { absent: "旷课", late: "迟到", present: "出勤" };
const HW_LABEL: Record<string, string> = { missing: "未交", late: "迟交", submitted: "已交" };

function dateLabel(iso: string) {
  const [, m, d] = iso.split("-");
  return `${Number(m)} 月 ${Number(d)} 日`;
}
function daysLeft(due: string) {
  const now = new Date();
  const target = new Date(`${due}T23:59:59`);
  const diff = Math.ceil((target.getTime() - now.getTime()) / 86400000);
  if (diff < 0) return `已逾期 ${-diff} 天`;
  if (diff === 0) return "今天截止";
  return `还剩 ${diff} 天`;
}

async function submitAppeal() {
  if (!appeal.text.trim() || !sid.value) return;
  appeal.sending = true;
  try {
    await api.submitAppeal({
      kind: appeal.kind,
      record_id: appeal.record_id,
      course: appeal.course,
      reason: appeal.text.trim(),
    });
    appeal.text = "";
    appeal.open = false;
    ElMessage.success("异议已提交，辅导员会尽快核实并回执（可在消息中心看进度）");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || "提交失败");
  } finally {
    appeal.sending = false;
  }
}
</script>

<template>
  <!-- 对话是主入口：进来就是整页 AI 问答，学情档案按键前往 -->
  <ChatHome v-if="chat.homeMode === 'chat'" role="student" :sid="sid || null" />

  <template v-else>
    <DashNav />

    <div v-if="loading" class="card">
      <div class="skeleton" style="height: 148px"></div>
    </div>

  <div v-else-if="error" class="card">
    <b>加载失败</b>
    <p class="tiny muted">{{ error }}</p>
    <button class="btn" @click="load">重试</button>
  </div>

  <div v-else-if="detail">
    <!-- 风险主卡 -->
    <div class="card risk-hero" :class="detail.risk.level">
      <div class="ring-wrap">
        <RiskRing :score="detail.risk.score" :level="detail.risk.level" />
        <span class="level-pill" :class="detail.risk.level">{{ detail.risk.level_label }}</span>
      </div>

      <div style="min-width: 0">
        <div class="risk-title">
          <span class="risk-name">{{ detail.student.name }}</span>
          <span class="tiny muted">
            {{ detail.student.class_name }} · {{ detail.student.major }} · {{ detail.student.grade }}
          </span>
        </div>
        <p class="tiny muted" style="margin: 0 0 10px">
          较上学期
          <b
            :class="{
              'trend-up': detail.risk.trend.direction === 'up',
              'trend-down': detail.risk.trend.direction === 'down',
              'trend-flat': detail.risk.trend.direction === 'flat',
            }"
          >
            {{ detail.risk.trend.label }}
            {{ detail.risk.trend.delta > 0 ? "+" : "" }}{{ detail.risk.trend.delta.toFixed(0) }} 分
          </b>
          （上学期折算 {{ detail.risk.trend.last_score }} 分） · 数据截至第 {{ app.week }} 教学周
        </p>

        <div class="risk-facts">
          <div v-for="f in facts" :key="f.label" class="fact">
            <b>{{ f.value }}</b>
            <span>{{ f.label }}</span>
          </div>
        </div>

        <div v-if="detail.risk.overrides.length" class="override-note">
          {{ detail.risk.overrides.join("；") }}
        </div>
      </div>
    </div>

    <!-- 成绩走势：五个学期一条线，外加本学期每门课的测评 -->
    <div v-if="gradeTrend && gradeTrend.terms.length" class="card mt">
      <div class="card-head">
        <h3>成绩走势 · 从大一到这学期</h3>
        <div class="head-side">
          <span class="hint">条上的每个点都能点开看班级均分与名次</span>
          <button class="ask-ai" @click="chat.ask('student', sid, '我的成绩是在涨还是在掉？')">问 AI：这条线说明什么？</button>
        </div>
      </div>
      <GradeTrend :trend="gradeTrend" />
      <p v-if="gradeTrend.watch" class="tiny muted note-line">
        {{ gradeTrend.watch }}。
      </p>
    </div>

    <div v-if="courseTrends.length" class="card mt">
      <div class="card-head">
        <h3>本学期每门课的测评走势</h3>
        <div class="head-side">
          <span class="hint">4 次随堂测 + 期中 · 分数在涨还是在掉，一条线看明白</span>
          <button class="ask-ai" @click="chat.ask('student', sid, '哪门课在往下掉？我该先抓哪门？')">问 AI：先抓哪门课？</button>
        </div>
      </div>
      <CourseTrend :courses="courseTrends" :worst="gradeTrend?.worst_code || ''" />
      <div class="ct-chips">
        <span
          v-for="c in courseTrends"
          :key="c.code"
          class="ct-chip"
          :class="c.trend"
          :title="`${c.name}：${c.points.map((p) => p.score).join(' → ')}`"
        >
          {{ c.name }}
          <b>{{ deltaLabel(c.delta) }}</b>
        </span>
      </div>
      <p class="tiny muted note-line">
        测评分数直接来自课程平台，期中成绩同时参与风险评分；随堂测不计入风险分，但能提前看出趋势。
      </p>
    </div>

    <!-- 因素 / 行动 -->
    <div class="two-col mt">
      <div class="card">
        <div class="card-head">
          <h3>风险从哪里来</h3>
          <span class="hint">每一项的分数相加等于风险分</span>
        </div>
        <FactorBars :items="detail.risk.factors" />
        <p class="tiny muted note-line">
          计算方式：各因素归一化后按权重加权，命中硬性红线时直接抬升等级。阈值可在教务端修改。
        </p>
      </div>

      <div class="card">
        <div class="card-head">
          <h3>接下来做什么</h3>
          <span class="hint">{{ detail.actions.length }} 条行动建议</span>
        </div>
        <ActionList :actions="detail.actions" />
      </div>
    </div>

    <!-- 课程明细 -->
    <div class="card mt">
      <div class="card-head">
        <h3>课程风险明细</h3>
        <span class="hint">挂科概率由期中成绩、作业与出勤共同估算</span>
      </div>
      <table class="table">
        <thead>
          <tr>
            <th>课程</th>
            <th>学分</th>
            <th>期中</th>
            <th>班级均分</th>
            <th>出勤</th>
            <th>作业</th>
            <th>挂科概率</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in detail.courses" :key="c.code">
            <td>
              {{ c.name }}<span class="tiny muted"> · {{ c.teacher }}</span>
            </td>
            <td class="num">{{ c.credit }}</td>
            <td class="num">{{ c.midterm }}</td>
            <td class="num muted">
              {{ detail.risk.pass_probability.find((x) => x.code === c.code)?.cohort_avg ?? "-" }}
            </td>
            <td class="num">缺 {{ c.absent }}</td>
            <td class="num">{{ c.hw_submitted }}/{{ c.hw_assigned }}</td>
            <td>
              <div style="display: flex; align-items: center; gap: 8px">
                <div class="bar" style="flex: 1; height: 5px">
                  <i
                    :style="{
                      width: `${(failOf(c) * 100).toFixed(0)}%`,
                      background: failColor(failOf(c)),
                    }"
                  ></i>
                </div>
                <span class="tiny num" :style="{ color: failColor(failOf(c)), width: '34px' }">
                  {{ (failOf(c) * 100).toFixed(0) }}%
                </span>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 我的老师：每门课的任课教师与联系方式 -->
    <div class="card mt">
      <div class="card-head">
        <h3>我的任课老师</h3>
        <span class="hint">{{ myCourses.length }} 门课 · 联系方式由教务维护</span>
      </div>
      <div class="teacher-list">
        <div v-for="c in myCourses" :key="c.code" class="teacher-item">
          <div class="teacher-top">
            <div class="teacher-who">
              <b>{{ c.teacher_profile?.name || c.teacher }}</b>
              <span class="tiny muted">
                {{ c.teacher_profile?.title || "任课教师" }}
                <template v-if="c.teacher_profile?.dept"> · {{ c.teacher_profile.dept }}</template>
              </span>
            </div>
            <span class="course-tag">{{ c.name }}</span>
          </div>
          <div class="teacher-meta">
            <span v-if="c.teacher_profile?.email">
              邮箱
              <a :href="`mailto:${c.teacher_profile.email}`">{{ c.teacher_profile.email }}</a>
            </span>
            <span v-if="c.teacher_profile?.phone">
              电话
              <a :href="`tel:${c.teacher_profile.phone}`">{{ c.teacher_profile.phone }}</a>
            </span>
            <span v-if="c.teacher_profile?.office">办公室 {{ c.teacher_profile.office }}</span>
            <span v-if="c.teacher_profile?.office_hour">答疑 {{ c.teacher_profile.office_hour }}</span>
            <span v-if="c.period" class="muted">{{ c.period }}</span>
          </div>
          <p v-if="c.teacher_profile?.note" class="tiny muted teacher-note">{{ c.teacher_profile.note }}</p>
        </div>

        <div v-for="c in extraCourses" :key="c.code" class="teacher-item pending">
          <div class="teacher-top">
            <div class="teacher-who">
              <b>{{ c.teacher_profile?.name || c.teacher }}</b>
              <span class="tiny muted">{{ c.teacher_profile?.title || "任课教师" }}</span>
            </div>
            <span class="course-tag ghost">{{ c.name }} · {{ c.status }}</span>
          </div>
          <div class="teacher-meta">
            <span v-if="c.teacher_profile?.email">
              邮箱
              <a :href="`mailto:${c.teacher_profile.email}`">{{ c.teacher_profile.email }}</a>
            </span>
            <span v-if="c.teacher_profile?.phone">
              电话
              <a :href="`tel:${c.teacher_profile.phone}`">{{ c.teacher_profile.phone }}</a>
            </span>
            <span v-if="c.teacher_profile?.office">办公室 {{ c.teacher_profile.office }}</span>
            <span v-if="c.period" class="muted">{{ c.period }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 考勤记录：哪一天、哪门课、第几节，一眼能对上 -->
    <div class="card mt">
      <div class="card-head">
        <h3>课堂考勤 · 具体到每一天</h3>
        <span class="hint">累计旷课 {{ attendanceStats.absent }} 次 · 迟到 {{ attendanceStats.late }} 次</span>
      </div>
      <div class="filter-row">
        <button class="chip" :class="{ on: onlyIssue }" @click="onlyIssue = true">
          只看异常（{{ attendanceStats.absent + attendanceStats.late }}）
        </button>
        <button class="chip" :class="{ on: !onlyIssue }" @click="onlyIssue = false">
          全部 {{ myCourses.reduce((n, c) => n + (c.attendance?.length || 0), 0) }} 次
        </button>
      </div>

      <div v-if="!allAttendance.length" class="empty-line">
        这段时间没有旷课或迟到记录，保持住。
      </div>
      <div v-else class="rec-list">
        <div v-for="a in allAttendance" :key="`${a.code}-${a.date}-${a.period}`" class="rec" :class="a.status">
          <div class="rec-when">
            <b>{{ dateLabel(a.date) }}</b>
            <span class="tiny muted">{{ a.weekday }} · 第 {{ a.week }} 周 · {{ a.period }}</span>
          </div>
          <div class="rec-what">
            <b>{{ a.course }}</b>
            <span class="tiny muted">{{ a.note || "正常到课" }}</span>
          </div>
          <div class="rec-side">
            <span class="pill" :class="a.status">{{ ATTEND_LABEL[a.status] }}</span>
            <button v-if="a.status !== 'present'" class="appeal-btn" @click="openAppeal('attendance', a, a.course)">
              异议
            </button>
          </div>
        </div>
      </div>
      <p class="tiny muted note-line">
        记录来自课堂考勤机与任课教师点名。若某天你实际到课，可在下方提交复核，辅导员会人工核实。
      </p>
    </div>

    <!-- 作业清单：要交什么、什么时候交、交没交 -->
    <div class="card mt">
      <div class="card-head">
        <h3>作业清单 · 要交什么写清楚</h3>
        <span class="hint">
          未交 {{ homeworkStats.missing }} · 迟交 {{ homeworkStats.late }} · 已交 {{ homeworkStats.submitted }}
        </span>
      </div>
      <div class="rec-list">
        <div v-for="h in allHomework" :key="h.id" class="rec hw" :class="h.status">
          <div class="rec-when">
            <b>{{ h.title }}</b>
            <span class="tiny muted">{{ h.course }} · {{ h.code }}</span>
          </div>
          <div class="rec-what">
            <span class="tiny">{{ h.brief }}</span>
            <span class="tiny muted hw-dates">
              布置 {{ dateLabel(h.assigned) }} · 截止 {{ dateLabel(h.due) }}
              <template v-if="h.status !== 'submitted'"> · {{ daysLeft(h.due) }}</template>
              <template v-else> · 已于 {{ h.submitted_at.slice(5, 16) }} 提交</template>
            </span>
          </div>
          <div class="rec-side">
            <span class="pill" :class="h.status">{{ HW_LABEL[h.status] }}</span>
            <button v-if="h.status !== 'submitted'" class="appeal-btn" @click="openAppeal('homework', h, h.course)">
              异议
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 申诉入口：AI 不能单方面决定学生命运 -->
    <div class="card mt">
      <div class="card-head">
        <h3>对数据或评分有异议？</h3>
        <span class="hint">任何预警都要经过人工核实</span>
      </div>
      <p class="tiny muted" style="margin: 0 0 10px">
        数据来自教务成绩、课堂考勤、作业平台与学习行为日志。若记录有误，可提交复核，系统不会仅凭评分作出任何处分决定。
      </p>
      <div v-if="!appeal.open">
        <button class="btn" @click="appeal.open = true">提交复核申请</button>
      </div>
      <div v-else class="appeal-form">
        <p v-if="appeal.course" class="tiny appeal-target">
          针对：{{ appeal.kind === "homework" ? "作业" : "考勤" }}记录 · {{ appeal.course }}
          <span v-if="appeal.record_id && appeal.record_id !== appeal.course" class="muted">（{{ appeal.record_id }}）</span>
        </p>
        <el-input
          v-model="appeal.text"
          type="textarea"
          :rows="3"
          maxlength="200"
          show-word-limit
          placeholder="请说明哪一项数据有误，例如：9 月 20 日的《数据结构》我实际到课，考勤记录有出入"
        />
        <div class="appeal-actions">
          <button class="btn" @click="appeal.open = false">取消</button>
          <button
            class="btn primary"
            :disabled="appeal.sending || !appeal.text.trim()"
            @click="submitAppeal"
          >
            {{ appeal.sending ? "提交中…" : "提交复核" }}
          </button>
        </div>
      </div>

      <div v-if="detail.interventions.length" class="appeal-list">
        <div v-for="i in detail.interventions" :key="i.id" class="tiny">
          <b>{{ i.title }}</b> · {{ i.status }} · {{ i.created_at }}
        </div>
      </div>
    </div>
  </div>
  </template>
</template>

<style scoped>
.note-line {
  margin: 14px 0 0;
  padding-top: 12px;
  border-top: 1px dashed var(--line);
}

/* 卡头右侧：提示语 + 问 AI 按钮 */
.head-side {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.ask-ai {
  flex: none;
  border: 1px solid #f0d9b5;
  background: #fdf1de;
  color: #4338ca;
  font-size: 11.5px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 99px;
  cursor: pointer;
  white-space: nowrap;
}
.ask-ai:hover {
  background: #f8e8cc;
  border-color: #e3b980;
}

/* 课程走势下面的小标签：哪门在涨、哪门在掉 */
.ct-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}
.ct-chip {
  font-size: 11.5px;
  padding: 2px 9px;
  border-radius: 999px;
  border: 1px solid var(--line);
  color: var(--text-2);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ct-chip b {
  margin-left: 5px;
  font-variant-numeric: tabular-nums;
}
.ct-chip.up {
  border-color: rgba(4, 120, 87, 0.25);
  background: var(--green-soft, #ecfdf5);
  color: var(--green, #047857);
}
.ct-chip.down {
  border-color: rgba(220, 38, 38, 0.25);
  background: var(--red-soft, #fef2f2);
  color: var(--red, #dc2626);
}

/* ---------------- 任课老师 ---------------- */
.teacher-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.teacher-item {
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px 14px;
  background: var(--card-2, rgba(0, 0, 0, 0.015));
  min-width: 0;
}
.teacher-item.pending {
  border-style: dashed;
  opacity: 0.85;
}
.teacher-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.teacher-who {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.course-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--brand-soft, rgba(37, 99, 235, 0.1));
  color: var(--brand, #b45309);
  white-space: nowrap;
  max-width: 52%;
  overflow: hidden;
  text-overflow: ellipsis;
}
.course-tag.ghost {
  background: var(--line);
  color: var(--text-2);
}
.teacher-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  font-size: 12px;
  color: var(--text-2);
  line-height: 1.7;
}
.teacher-meta a {
  color: var(--brand, #b45309);
  text-decoration: none;
  word-break: break-all;
}
.teacher-meta a:hover {
  text-decoration: underline;
}
.teacher-note {
  margin: 8px 0 0;
}

/* ---------------- 考勤 / 作业 ---------------- */
.filter-row {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.chip {
  font-size: 12px;
  padding: 5px 12px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: transparent;
  color: var(--text-2);
  cursor: pointer;
}
.chip.on {
  border-color: var(--brand, #b45309);
  color: var(--brand, #b45309);
  background: var(--brand-soft, rgba(37, 99, 235, 0.08));
}
.empty-line {
  padding: 18px 0;
  text-align: center;
  font-size: 13px;
  color: var(--text-2);
}
.rec-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.rec {
  display: grid;
  grid-template-columns: 150px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-left: 3px solid transparent;
  border-radius: 10px;
  min-width: 0;
}
.rec-side {
  display: flex;
  align-items: center;
  gap: 8px;
}
.appeal-btn {
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #fff;
  color: var(--text-2);
  font-size: 11px;
  padding: 2px 10px;
  cursor: pointer;
}
.appeal-btn:hover {
  color: var(--brand);
  border-color: var(--brand);
  background: var(--brand-soft);
}
.appeal-target {
  margin: 0 0 8px;
  padding: 6px 10px;
  border-radius: 8px;
  background: var(--brand-soft);
  color: var(--brand);
}
.rec.absent {
  border-left-color: var(--red, #dc2626);
  background: rgba(220, 38, 38, 0.04);
}
.rec.late {
  border-left-color: #d97706;
  background: rgba(217, 119, 6, 0.04);
}
.rec.hw.missing {
  border-left-color: var(--red, #dc2626);
  background: rgba(220, 38, 38, 0.04);
}
.rec.hw.late {
  border-left-color: #d97706;
}
.rec-when,
.rec-what {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.rec-what .tiny {
  line-height: 1.5;
  word-break: break-word;
}
.hw-dates {
  margin-top: 2px;
}
.pill {
  font-size: 11px;
  padding: 3px 9px;
  border-radius: 999px;
  white-space: nowrap;
  background: var(--line);
  color: var(--text-2);
}
.pill.absent,
.pill.missing {
  background: rgba(220, 38, 38, 0.12);
  color: var(--red, #dc2626);
}
.pill.late {
  background: rgba(217, 119, 6, 0.14);
  color: #b45309;
}
.pill.present,
.pill.submitted {
  background: rgba(22, 163, 74, 0.12);
  color: var(--green, #16a34a);
}

@media (max-width: 900px) {
  .teacher-list {
    grid-template-columns: minmax(0, 1fr);
  }
  .rec {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 6px 10px;
    align-items: start;
  }
  .rec-when {
    grid-column: 1 / 2;
  }
  .rec-what {
    grid-column: 1 / -1;
  }
  .pill {
    grid-column: 2 / 3;
    grid-row: 1 / 2;
  }
}

.appeal-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.appeal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
.appeal-list {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--line);
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: var(--text-2);
}
</style>
