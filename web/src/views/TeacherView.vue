<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { api, downloadDoc } from "@/api/client";
import ChatHome from "@/components/ChatHome.vue";
import ClassBars from "@/components/ClassBars.vue";
import DashNav from "@/components/DashNav.vue";
import DistDonut from "@/components/DistDonut.vue";
import HwFlow from "@/components/HwFlow.vue";
import ScoreBands from "@/components/ScoreBands.vue";
import StatGrid from "@/components/StatGrid.vue";
import TeacherStudentPanel from "@/components/TeacherStudentPanel.vue";
import WeeklyAttend from "@/components/WeeklyAttend.vue";
import { useNarrow } from "@/composables/useViewport";
import { useAuthStore } from "@/stores/auth";
import { useChatStore } from "@/stores/chat";
import type { ClassroomStudent, Level, TeacherClassroom } from "@/types";

/**
 * 教师端（第五端）：任课老师视角。
 *
 * 和其他四端最大的不同：这里的统计单位是「我教的这门课」。
 * - 学生端看自己、辅导员看名下学生、教务看全校、家长看一个孩子，
 *   只有任课老师是「横着看一个课堂」——同一份试卷、同一个进度下的几十上百人。
 * - 所以这一页的每一块都围绕课堂：成绩分布（不是单点分数）、逐周出勤
 *   （不是缺勤总数）、逐次作业（不是提交率总账）、分班对比（同一门课的班与班）。
 *
 * 账号隔离：六位任课教师各一个工号，进来看见的课程、名单、数字都不一样；
 * 数据由后端按登录态里的教师名过滤，前端不传任何身份参数。
 */
const auth = useAuthStore();
const chat = useChatStore();
const narrow = useNarrow();

const loading = ref(true);
const error = ref("");
const room = ref<TeacherClassroom | null>(null);

const activeCode = ref("");
const filter = ref<"all" | "risk" | "hw" | "absent" | "behind">("all");
const sortBy = ref<"risk" | "mid" | "absent" | "hw">("risk");
const kw = ref("");
const doneTodos = ref<Set<string>>(new Set());

const panel = reactive<{ open: boolean; stu: ClassroomStudent | null }>({
  open: false,
  stu: null,
});

const course = computed(() => {
  const list = room.value?.courses || [];
  return list.find((c) => c.code === activeCode.value) || list[0] || null;
});

const allStudents = computed(() => room.value?.students || []);

/** 课堂内排名/连旷等字段后端已算好，这里只做筛选与排序 */
const rows = computed(() => {
  let list = [...allStudents.value];
  const f = filter.value;
  if (f === "risk") list = list.filter((s) => s.level !== "green");
  else if (f === "hw") list = list.filter((s) => s.hw_missing > 0);
  else if (f === "absent") list = list.filter((s) => s.absent_streak >= 2);
  else if (f === "behind") list = list.filter((s) => s.gap <= -10);

  const q = kw.value.trim();
  if (q) {
    list = list.filter(
      (s) => s.name.includes(q) || s.id.includes(q) || s.class_name.includes(q),
    );
  }

  const key = sortBy.value;
  list.sort((a, b) => {
    if (key === "mid") return (a.midterm ?? 0) - (b.midterm ?? 0);
    if (key === "absent") return b.absent - a.absent;
    if (key === "hw") return b.hw_missing - a.hw_missing;
    return b.score - a.score;
  });
  return list;
});

const counts = computed(() => {
  const list = allStudents.value;
  return {
    all: list.length,
    risk: list.filter((s) => s.level !== "green").length,
    hw: list.filter((s) => s.hw_missing > 0).length,
    absent: list.filter((s) => s.absent_streak >= 2).length,
    behind: list.filter((s) => s.gap <= -10).length,
  };
});

const stats = computed(() => {
  const c = course.value;
  if (!c) return [];
  const watch = c.risk.red + c.risk.yellow;
  return [
    { value: c.students, label: "修课学生 · 人" },
    {
      value: c.mid_avg,
      label: `期中均分 · 年级 ${c.grade_avg}（${c.gap_grade > 0 ? "+" : ""}${c.gap_grade}）`,
      tone: "" as const,
    },
    // dist[4] 是「60 分以下」档，count 才是不及格人数；
    // 总人数减它是及格人数，别写反。
    { value: `${c.pass_rate}%`, label: `及格率 · 不及格 ${c.dist[4].count} 人` },
    { value: `${c.attend.rate}%`, label: `课堂出勤率 · 已上 ${c.attend.sessions} 次` },
    { value: `${c.hw.rate}%`, label: `作业提交率 · 已布置 ${c.hw.assigned} 次` },
    {
      value: watch,
      label: `需关注 · 红 ${c.risk.red} / 黄 ${c.risk.yellow}`,
      tone: (c.risk.red ? "red" : watch ? "amber" : "") as "red" | "amber" | "",
    },
  ];
});

const levelTag = (lv: Level) => (lv === "red" ? "红" : lv === "yellow" ? "黄" : "绿");

async function load() {
  loading.value = true;
  error.value = "";
  try {
    // 只打这一个接口：/teacher/view 与它内容重叠（240 份考勤明细会有 800 KB），
    // 一起拉等于把同一份数据下载两遍，移动网络下首屏会明显变慢。
    const rc = await api.teacherClassroom();
    room.value = rc;
    if (!activeCode.value && rc.courses.length) activeCode.value = rc.courses[0].code;
  } catch (e: any) {
    error.value = e?.message || "课堂数据加载失败";
  } finally {
    loading.value = false;
  }
}

onMounted(load);

function openStudent(s: ClassroomStudent) {
  panel.stu = s;
  panel.open = true;
}

/** 待办里点名字：直接定位到这名学生，省得再去名单里翻 */
function openByName(name: string) {
  const clean = name.replace(/（.*$/, "");
  const hit = allStudents.value.find((s) => s.name === clean);
  if (hit) openStudent(hit);
}

function toggleTodo(id: string) {
  const set = new Set(doneTodos.value);
  if (set.has(id)) set.delete(id);
  else set.add(id);
  doneTodos.value = set;
}

const askQuick = (q: string) => chat.ask("teacher", null, q);

const profile = computed(() => room.value?.teacher || null);
</script>

<template>
  <!-- 对话是主入口：进来先跟教学助手说话，看板按键过去 -->
  <ChatHome v-if="chat.homeMode === 'chat'" role="teacher" :sid="null" />

  <template v-else>
    <DashNav />

    <div v-if="loading" class="card empty"><span class="spinner"></span> 正在汇总课堂数据…</div>
    <div v-else-if="error" class="card empty">
      {{ error }}
      <button class="btn sm" style="margin-left: 10px" @click="load">重试</button>
    </div>

    <template v-else-if="room && course">
      <!-- ① 教师身份 + 我的课程：六位数工号各看各的课，这里直接标出来 -->
      <section id="classroom" class="card hero">
        <div class="hero-left">
          <div class="avatar">{{ (profile?.name || auth.profile?.name || "师").slice(0, 1) }}</div>
          <div class="who">
            <h2>
              {{ profile?.name || auth.profile?.name }}老师
              <span v-if="profile?.title" class="title-pill">{{ profile.title }}</span>
            </h2>
            <p class="meta">
              工号 {{ profile?.employee_id || auth.profile?.account }} · {{ profile?.dept || auth.profile?.class_name }}
              <template v-if="profile?.note"> · {{ profile.note }}</template>
            </p>
            <div class="chips">
              <span v-if="profile?.office" class="chip-i">办公室 {{ profile.office }}</span>
              <span v-if="profile?.email" class="chip-i">{{ profile.email }}</span>
              <span v-if="profile?.office_hour" class="chip-i">答疑 {{ profile.office_hour }}</span>
            </div>
          </div>
        </div>

        <div class="hero-right">
          <div class="scope">
            <b>我的课程</b>
            <span class="tiny muted">本账号只能看到自己任教的课与修课学生</span>
          </div>
          <div class="course-tabs">
            <button
              v-for="c in room.courses"
              :key="c.code"
              class="ctab"
              :class="{ on: c.code === course.code }"
              @click="activeCode = c.code"
            >
              <b>{{ c.name }}</b>
              <span>{{ c.credit }} 学分 · {{ c.kind }} · {{ c.period }} · {{ c.students }} 人</span>
            </button>
          </div>
          <div class="hero-acts">
            <button class="btn primary sm" @click="downloadDoc('/api/export/classroom')">
              导出课堂学情简报
            </button>
            <button class="btn sm" @click="askQuick('我课上的学生')">问 AI：我课上的学生</button>
          </div>
        </div>
      </section>

      <!-- ② 课堂概况：六项都以「这门课」为单位 -->
      <StatGrid :items="stats" :cols="6" />

      <!-- ③ 四张课堂图：分布、节奏、作业、班级差 -->
      <div class="grid2">
        <div class="card">
          <div class="card-head">
            <h3>期中成绩分布</h3>
            <span class="hint">看形状不看均分：两个班均分一样，教法可能完全不同</span>
          </div>
          <ScoreBands :dist="course.dist" :avg="course.mid_avg" :pass-rate="course.pass_rate" />
          <div class="band-foot tiny muted">
            最低 {{ course.lowest }} · 最高 {{ course.highest }} · 中位数 {{ course.median }} ·
            标准差 {{ course.std }}（越小说明整体越整齐）
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <h3>逐周出勤</h3>
            <span class="hint">哪一周开始塌的，比一共缺了几次更有用</span>
          </div>
          <WeeklyAttend :weekly="course.attend.weekly" />
          <div class="band-foot tiny muted">
            本周课堂累计旷课 {{ course.attend.absent }} 人次、迟到 {{ course.attend.late }} 人次
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <h3>逐次作业提交</h3>
            <span class="hint">总提交率会掩盖「最后一次塌一半」这种情况</span>
          </div>
          <HwFlow :items="course.hw.items" />
        </div>

        <div class="card">
          <div class="card-head">
            <h3>分班对比</h3>
            <span class="hint">同一套卷子同一个进度，班与班的差才是能改的东西</span>
          </div>
          <ClassBars :classes="course.classes" :course-avg="course.mid_avg" />
        </div>
      </div>

      <!-- ④ 教学待办：任课老师这一周真正要做的四件事 -->
      <div class="todo-wrap">
        <section class="card todo-card">
          <div class="card-head">
            <h3>本周教学待办</h3>
            <span class="hint">按紧急程度排，勾掉即视为已处理（本地）</span>
          </div>
          <div v-if="!room.todos.length" class="empty">这门课暂时没有需要处理的事</div>
          <div
            v-for="t in room.todos"
            :key="t.id"
            class="todo"
            :data-tone="t.tone"
            :class="{ done: doneTodos.has(t.id) }"
          >
            <button class="tick" :aria-label="'标记已处理'" @click="toggleTodo(t.id)">
              {{ doneTodos.has(t.id) ? "✓" : "" }}
            </button>
            <div class="todo-body">
              <b>{{ t.title }}</b>
              <p class="tiny muted">{{ t.detail }}</p>
              <div class="names">
                <button v-for="n in t.names" :key="n" class="name-chip" @click="openByName(n)">
                  {{ n }}
                </button>
                <span v-if="!t.names.length" class="tiny muted">—</span>
              </div>
              <p class="act-line"><b>建议动作：</b>{{ t.action }}</p>
            </div>
          </div>
        </section>

        <section class="card risk-card">
          <div class="card-head"><h3>课堂风险构成</h3></div>
          <DistDonut :dist="course.risk" />
          <ul class="risk-legend">
            <li><i style="background: #dc2626"></i>红色预警 <b>{{ course.risk.red }}</b> 人</li>
            <li><i style="background: #d97706"></i>黄色关注 <b>{{ course.risk.yellow }}</b> 人</li>
            <li><i style="background: #047857"></i>状态正常 <b>{{ course.risk.green }}</b> 人</li>
          </ul>
          <p class="tiny muted note">
            风险分跨六门课汇总，课堂只是其中一部分；红色学生建议反馈辅导员，
            课堂层面能做的（点名、提问、催作业）已列在左侧待办。
          </p>
        </section>
      </div>

      <!-- ⑤ 课堂名单 -->
      <section class="card">
        <div class="card-head">
          <h3>{{ course.name }} · 学生名单（{{ rows.length }} / {{ counts.all }} 人）</h3>
          <span class="hint">点击任意一行看这名学生在本课堂的考勤与作业</span>
        </div>

        <div class="filters">
          <button class="fchip" :class="{ on: filter === 'all' }" @click="filter = 'all'">
            全部 {{ counts.all }}
          </button>
          <button class="fchip" :class="{ on: filter === 'risk' }" @click="filter = 'risk'">
            需关注 {{ counts.risk }}
          </button>
          <button class="fchip" :class="{ on: filter === 'hw' }" @click="filter = 'hw'">
            有作业未交 {{ counts.hw }}
          </button>
          <button class="fchip" :class="{ on: filter === 'absent' }" @click="filter = 'absent'">
            连续缺勤 ≥2 {{ counts.absent }}
          </button>
          <button class="fchip" :class="{ on: filter === 'behind' }" @click="filter = 'behind'">
            低于均分 10 分 {{ counts.behind }}
          </button>
          <input v-model="kw" class="kw" placeholder="搜姓名 / 学号 / 班级" />
          <select v-model="sortBy" class="sel" aria-label="排序方式">
            <option value="risk">按风险分降序</option>
            <option value="mid">按期中升序</option>
            <option value="absent">按缺勤降序</option>
            <option value="hw">按未交作业降序</option>
          </select>
        </div>

        <!-- 手机屏：列太多必然溢出，换成列表 -->
        <div v-if="narrow" class="m-list">
          <div v-for="s in rows" :key="s.id" class="m-row" @click="openStudent(s)">
            <div class="m-main">
              <b>{{ s.name }}</b>
              <span class="tiny muted">{{ s.class_name }} · 期中 {{ s.midterm }} · 缺勤 {{ s.absent }}</span>
            </div>
            <span class="score-chip" :class="s.level">{{ s.score }}</span>
          </div>
          <div v-if="!rows.length" class="empty">没有符合条件的学生</div>
        </div>

        <div v-else class="table-wrap">
          <el-table
            :data="rows"
            height="430"
            style="width: 100%"
            :row-style="{ cursor: 'pointer' }"
            @row-click="openStudent"
          >
            <el-table-column label="学生 / 班级" min-width="150">
              <template #default="{ row }">
                <div class="stu-cell">
                  <b>{{ row.name }}</b>
                  <span class="tiny muted">{{ row.id }} · {{ row.class_name }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="期中" width="92">
              <template #default="{ row }">
                <div class="mid-cell">
                  <b>{{ row.midterm }}</b>
                  <span class="tiny" :class="row.gap <= -10 ? 'bad' : row.gap >= 10 ? 'good' : 'flat'">
                    {{ row.gap > 0 ? "+" : "" }}{{ row.gap }}
                  </span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="课堂排名" width="82">
              <template #default="{ row }">
                <span class="tiny">{{ row.rank }} / {{ row.rank_total }}</span>
              </template>
            </el-table-column>
            <el-table-column label="缺勤" width="82">
              <template #default="{ row }">
                <span :class="{ 'bad-txt': row.absent_streak >= 2 }">
                  {{ row.absent }} 次
                  <i v-if="row.absent_streak >= 2" class="streak">连{{ row.absent_streak }}</i>
                </span>
              </template>
            </el-table-column>
            <el-table-column label="作业" width="86">
              <template #default="{ row }">
                <span :class="{ 'bad-txt': row.hw_missing > 0 }">
                  {{ row.hw_submitted }}/{{ row.hw_assigned }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="风险" width="96">
              <template #default="{ row }">
                <div class="risk-cell">
                  <span class="score-chip" :class="row.level">{{ row.score }}</span>
                  <span class="tiny muted">{{ row.top_factor }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="等级" width="56">
              <template #default="{ row }">
                <span class="level-pill" :class="row.level" style="font-size: 11px">
                  {{ levelTag(row.level) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="" width="66">
              <template #default>
                <span class="tiny" style="color: var(--brand)">看档案</span>
              </template>
            </el-table-column>
            <template #empty>
              <div class="empty">没有符合条件的学生</div>
            </template>
          </el-table>
        </div>

        <p class="tiny muted foot-note">
          教师端只覆盖「我教的这门课」的数据。挂科学分、处分记录、家校沟通等跨课程事项
          由辅导员端与教务端处理——任课教师看到的是课堂，不是学生的全部。
        </p>
      </section>
    </template>

    <TeacherStudentPanel v-model="panel.open" :stu="panel.stu" />
  </template>
</template>

<style scoped>
.empty {
  padding: 34px 0;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}

/* ---------- 身份卡 ---------- */
.hero {
  display: grid;
  grid-template-columns: minmax(240px, 300px) 1fr;
  gap: 22px;
  align-items: start;
}
.hero-left {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}
.avatar {
  width: 54px;
  height: 54px;
  border-radius: 15px;
  display: grid;
  place-items: center;
  font-size: 22px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, #d97706, #b45309);
  flex: none;
}
.who h2 {
  font-size: 19px;
  margin: 0 0 3px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.title-pill {
  font-size: 11px;
  font-weight: 500;
  color: var(--brand);
  background: var(--brand-soft);
  border: 1px solid color-mix(in srgb, var(--brand) 25%, transparent);
  border-radius: 5px;
  padding: 1px 6px;
}
.who .meta {
  font-size: 12.5px;
  color: var(--muted);
  margin: 0 0 7px;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip-i {
  font-size: 11.5px;
  color: var(--text-2);
  background: #faf6ee;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 2px 7px;
}

.hero-right {
  border-left: 1px dashed var(--line);
  padding-left: 22px;
}
.scope {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 8px;
}
.scope b {
  font-size: 13px;
}
.course-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.ctab {
  text-align: left;
  border: 1px solid var(--line);
  background: #fffdf9;
  border-radius: 10px;
  padding: 8px 12px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.ctab b {
  display: block;
  font-size: 13.5px;
  color: var(--text);
  font-weight: 600;
}
.ctab span {
  font-size: 11.5px;
  color: var(--muted);
}
.ctab:hover {
  border-color: var(--brand);
}
.ctab.on {
  border-color: var(--brand);
  background: var(--brand-soft);
}
.hero-acts {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 12px;
}

/* ---------- 图表区 ---------- */
.grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.band-foot {
  margin: 4px 0 0;
}
.todo-wrap {
  display: grid;
  grid-template-columns: 1fr 268px;
  gap: 16px;
  align-items: start;
}

/* ---------- 待办 ---------- */
.todo {
  display: flex;
  gap: 10px;
  padding: 11px 0;
  border-top: 1px solid #f4ece0;
}
.todo:first-of-type {
  border-top: 0;
}
.todo.done {
  opacity: 0.45;
}
.todo.done .todo-body b {
  text-decoration: line-through;
}
.tick {
  width: 20px;
  height: 20px;
  flex: none;
  margin-top: 2px;
  border-radius: 6px;
  border: 1.5px solid var(--line-strong);
  background: #fff;
  color: var(--green);
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
}
.todo[data-tone="red"] .tick {
  border-color: #fca5a5;
}
.todo[data-tone="amber"] .tick {
  border-color: #fcd34d;
}
.todo-body {
  min-width: 0;
}
.todo-body b {
  font-size: 13.5px;
  color: var(--text);
}
.todo[data-tone="red"] .todo-body b {
  color: #9f1239;
}
.todo-body p {
  margin: 3px 0 6px;
  line-height: 1.6;
}
.names {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-bottom: 6px;
}
.name-chip {
  border: 1px solid var(--line);
  background: #faf6ee;
  border-radius: 999px;
  padding: 1px 9px;
  font-size: 11.5px;
  color: var(--text-2);
  cursor: pointer;
}
.name-chip:hover {
  border-color: var(--brand);
  color: var(--brand);
}
.act-line {
  margin: 0;
  font-size: 12px;
  color: var(--brand);
}

/* ---------- 风险卡片 ---------- */
.risk-legend {
  list-style: none;
  padding: 0;
  margin: 6px 0 0;
  font-size: 12.5px;
}
.risk-legend li {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 3px 0;
  color: var(--text-2);
}
.risk-legend i {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.risk-legend b {
  margin-left: auto;
  color: var(--text);
}
.risk-card .note {
  margin: 10px 0 0;
  line-height: 1.7;
  border-top: 1px dashed var(--line);
  padding-top: 9px;
}

/* ---------- 名单 ---------- */
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
  align-items: center;
}
.fchip {
  border: 1px solid var(--line);
  background: #fffdf9;
  color: var(--text-2);
  border-radius: 999px;
  padding: 4px 12px;
  font-size: 12.5px;
  cursor: pointer;
}
.fchip:hover {
  border-color: var(--brand);
}
.fchip.on {
  background: var(--brand-soft);
  border-color: var(--brand);
  color: var(--brand);
  font-weight: 600;
}
.kw {
  height: 30px;
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  padding: 0 10px;
  font-size: 12.5px;
  color: var(--text);
  background: #fff;
  width: 180px;
  margin-left: auto;
}
.kw:focus {
  outline: 2px solid var(--brand-soft);
  border-color: var(--brand);
}
.sel {
  height: 30px;
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  background: #fff;
  color: var(--text);
  font-size: 12.5px;
  padding: 0 8px;
  cursor: pointer;
}
.table-wrap {
  overflow-x: auto;
}
.stu-cell {
  display: flex;
  flex-direction: column;
  line-height: 1.4;
}
.mid-cell {
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.mid-cell b {
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}
.bad {
  color: var(--red);
}
.good {
  color: var(--green);
}
.flat {
  color: var(--muted);
}
.bad-txt {
  color: var(--red);
  font-weight: 500;
}
.streak {
  font-style: normal;
  font-size: 10.5px;
  color: #fff;
  background: var(--red);
  border-radius: 4px;
  padding: 0 4px;
  margin-left: 3px;
}
.risk-cell {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.risk-cell .tiny {
  font-size: 10.5px;
  white-space: nowrap;
}
.m-list {
  display: flex;
  flex-direction: column;
}
.m-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 2px;
  border-bottom: 1px solid #f4ece0;
  cursor: pointer;
}
.m-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.foot-note {
  margin: 12px 0 0;
  line-height: 1.7;
  border-top: 1px dashed var(--line);
  padding-top: 10px;
}

@media (max-width: 1080px) {
  .hero {
    grid-template-columns: 1fr;
  }
  .hero-right {
    border-left: 0;
    border-top: 1px dashed var(--line);
    padding-left: 0;
    padding-top: 14px;
  }
  .grid2 {
    grid-template-columns: 1fr;
  }
  .todo-wrap {
    grid-template-columns: 1fr;
  }
}
</style>
