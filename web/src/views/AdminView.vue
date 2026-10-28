<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus/es/components/message/index";
import { api, downloadDoc } from "@/api/client";
import ChatHome from "@/components/ChatHome.vue";
import ClassCompare from "@/components/ClassCompare.vue";
import DashNav from "@/components/DashNav.vue";
import DistDonut from "@/components/DistDonut.vue";
import FactorBars from "@/components/FactorBars.vue";
import StatGrid from "@/components/StatGrid.vue";
import { useAppStore } from "@/stores/app";
import { useChatStore } from "@/stores/chat";
import type {
  AccountRow,
  CurriculumImportResult,
  CurriculumPayload,
  ImportResult,
} from "@/types";

const app = useAppStore();
const chat = useChatStore();
const loading = ref(true);
const saving = ref(false);
const message = ref("");

const cfg = reactive({ red_line: 55, yellow_line: 35, absence_pct: 25 });

/* ---------------- 学生账号批量开通 ---------------- */
const importText = ref("");
const importing = ref(false);
const importResult = ref<ImportResult | null>(null);
const accounts = ref<AccountRow[]>([]);
const accStats = ref<Record<string, number>>({});
const fileName = ref("");

async function loadAccounts() {
  try {
    const res = await api.accounts(200);
    accounts.value = res.rows;
    accStats.value = res.stats;
  } catch (e: any) {
    // 账号列表拉不到不影响主看板，静默即可
  }
}

function pickFile(ev: Event) {
  const input = ev.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  fileName.value = file.name;
  const reader = new FileReader();
  reader.onload = () => {
    importText.value = String(reader.result || "");
  };
  reader.readAsText(file, "utf-8");
  input.value = "";
}

function fillSample() {
  const rows = app.meta?.classes?.slice(0, 3) ?? [];
  importText.value = accounts.value
    .slice(0, 5)
    .map((a) => `${a.sid},${a.name},${a.class_name}`)
    .join("\n");
  if (!importText.value && rows.length) {
    importText.value = `20240001,示例学生,${rows[0]}\n20240002,示例学生,${rows[0]}`;
  }
}

async function runImport() {
  if (!importText.value.trim()) {
    ElMessage.warning("先粘贴学号清单，或选择一个 CSV 文件");
    return;
  }
  importing.value = true;
  try {
    const res = await api.importStudents(importText.value);
    importResult.value = res;
    accounts.value = res.accounts;
    await loadAccounts();
    ElMessage.success(`批量开通完成：新增 ${res.created}，重置 ${res.reset}`);
  } catch (e: any) {
    ElMessage.error(e?.message || "导入失败");
  } finally {
    importing.value = false;
  }
}

const overview = computed(() => app.overview);

/* ---------------- 课程与教师档案导入 ---------------- */
const courseText = ref("");
const courseImporting = ref(false);
const courseResult = ref<CurriculumImportResult | null>(null);
const courseFileName = ref("");
const curriculum = ref<CurriculumPayload | null>(null);

async function loadCurriculum() {
  try {
    curriculum.value = await api.curriculum();
  } catch (e: any) {
    // 读不到不影响其他面板
  }
}

function pickCourseFile(ev: Event) {
  const input = ev.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  courseFileName.value = file.name;
  const reader = new FileReader();
  reader.onload = () => {
    courseText.value = String(reader.result || "");
  };
  reader.readAsText(file, "utf-8");
  input.value = "";
}

function fillCourseSample() {
  const rows = curriculum.value?.courses ?? [];
  if (!rows.length) {
    courseText.value = [
      "课程代码,课程名称,学分,类型,任课教师,上课时间,教师邮箱,教师电话,办公室,答疑时间",
      "CS201,数据结构,4,必修,周立群,周一 1-2 节,zhoulq@cs.univ.edu.cn,138-0013-8001,信息楼 A503,周二 14:00-16:00",
      "CS301,数据库原理,3,必修,赵敏,周四 3-4 节,zhaomin@cs.univ.edu.cn,138-0013-8099,信息楼 B401,周五 10:00-12:00",
    ].join("\n");
    return;
  }
  courseText.value = [
    "课程代码,课程名称,学分,类型,任课教师,上课时间,教师邮箱,教师电话,办公室,答疑时间",
    ...rows.slice(0, 3).map((c) => {
      const t = c.teacher_profile || ({} as any);
      return [
        c.code, c.name, c.credit, c.kind, c.teacher, c.period,
        t.email || "", t.phone || "", t.office || "", t.office_hour || "",
      ].join(",");
    }),
  ].join("\n");
}

async function runCourseImport() {
  if (!courseText.value.trim()) {
    ElMessage.warning("先粘贴课程与教师清单，或选择一个 CSV 文件");
    return;
  }
  courseImporting.value = true;
  try {
    const res = await api.importCurriculum(courseText.value);
    courseResult.value = res;
    await loadCurriculum();
    ElMessage.success(`导入完成：更新 ${res.updated} 门，新增 ${res.added} 门`);
  } catch (e: any) {
    ElMessage.error(e?.message || "导入失败");
  } finally {
    courseImporting.value = false;
  }
}

const stats = computed(() => {
  const o = overview.value;
  if (!o) return [];
  return [
    { value: o.total, label: "在册学生", tone: "" as const },
    { value: o.dist.red, label: `红色预警 · ${o.dist_pct.red}%`, tone: "red" as const },
    { value: o.dist.yellow, label: `黄色关注 · ${o.dist_pct.yellow}%`, tone: "amber" as const },
    { value: o.rising_count, label: "风险上升人数", tone: "" as const },
  ];
});

const pressure = computed(() =>
  (overview.value?.top_factors ?? []).map((f) => ({ label: f.label, points: f.points })),
);

async function load() {
  loading.value = true;
  try {
    await app.loadOverview();
    const c = app.meta?.config;
    if (c) {
      cfg.red_line = c.red_line;
      cfg.yellow_line = c.yellow_line;
      cfg.absence_pct = Math.round(c.policy.absence_warn_ratio * 100);
    }
  } catch (e: any) {
    ElMessage.error(e?.message || "看板加载失败");
  } finally {
    loading.value = false;
  }
}

/* ---------------- 每日预警日报（定时任务同款聚合） ---------------- */
const daily = ref<Awaited<ReturnType<typeof api.dailyReport>> | null>(null);
async function loadDaily() {
  try {
    daily.value = await api.dailyReport();
  } catch {
    daily.value = null; // 日报卡失败不挡页面，对话里问「今日日报」同样能拿到
  }
}

onMounted(() => {
  load();
  loadAccounts();
  loadCurriculum();
  loadDaily();
});

async function save() {
  if (cfg.yellow_line >= cfg.red_line) {
    message.value = "黄色线必须低于红色线";
    return;
  }
  saving.value = true;
  message.value = "重算中…";
  try {
    const o = await app.saveConfig({
      red_line: cfg.red_line,
      yellow_line: cfg.yellow_line,
      absence_warn_ratio: cfg.absence_pct / 100,
    });
    message.value = `已重算：红色 ${o.dist.red} 人，黄色 ${o.dist.yellow} 人`;
    ElMessage.success("规则已生效");
  } catch (e: any) {
    message.value = `保存失败：${e?.message || ""}`;
  } finally {
    saving.value = false;
  }
}

async function exportCSV() {
  try {
    const data = await api.students({ limit: 300 });
    const head = ["学号", "姓名", "班级", "风险分", "等级", "趋势", "主因", "缺勤", "作业未交", "期中均分"];
    const rows = data.rows.map((r) => [
      r.id,
      r.name,
      r.class_name,
      r.score,
      r.level_label,
      r.delta,
      r.top_factor,
      r.absent,
      r.missed_hw,
      r.mid_avg,
    ]);
    const csv = "\ufeff" + [head, ...rows].map((r) => r.map((x) => `"${x}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `学业预警名单_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
    ElMessage.success(`已导出 ${rows.length} 条`);
  } catch (e: any) {
    ElMessage.error(e?.message || "导出失败");
  }
}
</script>

<template>
  <!-- 对话是主入口：进来就是整页 AI 问答，规则与全校看板按键前往 -->
  <ChatHome v-if="chat.homeMode === 'chat'" role="admin" :sid="null" />

  <template v-else>
    <DashNav />

    <div class="view-actions">
      <span class="badge" style="background: #fdf1de; color: #b45309">规则版本 v1.2</span>
      <button class="btn" @click="exportCSV">导出预警名单</button>
      <button class="btn" @click="downloadDoc('/api/export/daily-report')">每日预警日报</button>
      <button class="btn primary" @click="downloadDoc('/api/export/semester')">学期汇报 PPT</button>
    </div>

    <!-- 每日预警日报：定时任务与对话共用同一份聚合，这里展示它说了什么 -->
    <div v-if="daily" class="card">
      <div class="card-head">
        <h3>每日预警日报</h3>
        <div class="head-side">
          <span class="tiny muted">每天 08:00 自动生成 · 本次 {{ daily.generated_at }}</span>
          <button class="btn" @click="downloadDoc('/api/export/daily-report')">Word</button>
        </div>
      </div>
      <p style="margin: 2px 0 10px; font-size: 13.5px">{{ daily.summary }}</p>
      <div class="report-strip">
        <span v-for="x in daily.red_top" :key="x.name" class="rs-item">
          <b>{{ x.name }}</b> {{ x.class_name }} · {{ x.score }} 分
        </span>
      </div>
    </div>

  <StatGrid :items="stats" />

  <div class="two-col">
    <div class="card">
      <div class="card-head">
        <h3>风险等级分布</h3>
        <span class="hint">数据截至第 {{ app.week }} 教学周</span>
      </div>
      <div v-if="overview">
        <DistDonut :dist="overview.dist" />
      </div>
      <div v-else class="skeleton" style="height: 160px"></div>
    </div>

    <div class="card">
      <div class="card-head">
        <h3>最普遍的风险因素</h3>
        <span class="hint">全校人均摊到的分数</span>
      </div>
      <FactorBars v-if="pressure.length" :items="pressure" mode="pressure" />
    </div>
  </div>

  <div class="card mt">
    <div class="card-head">
      <h3>班级风险对比</h3>
      <span class="hint">柱长为班级人数，红色段为预警人数</span>
    </div>
    <div v-if="overview">
      <ClassCompare :by-class="overview.by_class" />
    </div>
    <div v-else class="skeleton" style="height: 180px"></div>
  </div>

  <div class="card mt">
    <div class="card-head">
      <h3>预警规则配置</h3>
      <span class="hint">修改后立即重算全校，可用于“一校一规”</span>
    </div>

    <div class="three-col">
      <div class="field">
        <label>红色预警线（风险分 ≥）</label>
        <el-input-number v-model="cfg.red_line" :min="1" :max="100" :step="1" style="width: 100%" />
        <div class="hint">当前 {{ overview?.dist.red ?? "-" }} 人</div>
      </div>
      <div class="field">
        <label>黄色关注线（风险分 ≥）</label>
        <el-input-number v-model="cfg.yellow_line" :min="0" :max="99" :step="1" style="width: 100%" />
        <div class="hint">当前 {{ overview?.dist.yellow ?? "-" }} 人</div>
      </div>
      <div class="field">
        <label>缺勤率硬性触发线（%）</label>
        <el-input-number v-model="cfg.absence_pct" :min="5" :max="80" :step="5" style="width: 100%" />
        <div class="hint">超过直接抬升等级</div>
      </div>
    </div>

    <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap">
      <button class="btn primary" :disabled="saving" @click="save">
        {{ saving ? "重算中…" : "保存并重算" }}
      </button>
      <span class="tiny muted">{{ message }}</span>
    </div>
  </div>

  <div class="card mt">
    <div class="card-head">
      <h3>学生账号 · 批量开通</h3>
      <span class="hint">
        每行一条：学号,姓名,班级（班级可省，初始密码默认 0000）
      </span>
    </div>

    <div class="import-grid">
      <div class="import-left">
        <div class="import-tools">
          <label class="btn file-btn">
            选择 CSV / TXT
            <input type="file" accept=".csv,.txt" @change="pickFile" />
          </label>
          <button class="btn" @click="fillSample">填入示例</button>
          <span v-if="fileName" class="file-name">{{ fileName }}</span>
        </div>
        <textarea
          v-model="importText"
          class="import-area"
          spellcheck="false"
          placeholder="20240001,许雨桐,计科2401&#10;20240002,胡若飞,计科2401&#10;20240003,,计科2402,0000"
        ></textarea>
        <div class="import-actions">
          <button class="btn primary" :disabled="importing" @click="runImport">
            {{ importing ? "开通中…" : "批量开通 / 重置为初始密码" }}
          </button>
          <span class="tiny muted">
            学号必须存在于学情库；已开通的学号会被重置为初始密码 0000。
          </span>
        </div>

        <div v-if="importResult" class="import-result">
          <span class="ok">新增 {{ importResult.created }}</span>
          <span class="warn">重置 {{ importResult.reset }}</span>
          <span v-if="importResult.failed_count" class="bad">失败 {{ importResult.failed_count }}</span>
          <ul v-if="importResult.failed_count">
            <li v-for="f in importResult.failed" :key="f.line + f.sid">
              第 {{ f.line }} 行 · {{ f.sid || "空学号" }}：{{ f.reason }}
            </li>
          </ul>
        </div>
      </div>

      <div class="import-right">
        <div class="acc-stats">
          <div><b>{{ accStats.student_accounts ?? 0 }}</b><span>已开通学生账号</span></div>
          <div><b>{{ accStats.student_changed ?? 0 }}</b><span>已改过密码</span></div>
          <div><b>{{ accStats.student_total ?? 0 }}</b><span>学情库学生</span></div>
        </div>
        <div class="acc-list">
          <div v-if="!accounts.length" class="tiny muted empty">
            还没有单独开通的账号，学生首次登录时也会自动开通。
          </div>
          <div v-for="a in accounts.slice(0, 8)" :key="a.sid" class="acc-row">
            <span class="mono">{{ a.sid }}</span>
            <span class="acc-name">{{ a.name }}</span>
            <span class="tiny muted">{{ a.class_name }}</span>
            <span class="acc-flag" :class="{ used: !a.is_default }">
              {{ a.is_default ? "初始密码" : "已改密" }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="card mt">
    <div class="card-head">
      <h3>课程与教师 · 导入</h3>
      <span class="hint">学生端「我的任课老师」直接读这里</span>
    </div>

    <div class="import-grid">
      <div class="import-left">
        <div class="import-tools">
          <label class="btn file-btn">
            选择 CSV / TXT
            <input type="file" accept=".csv,.txt" @change="pickCourseFile" />
          </label>
          <button class="btn" @click="fillCourseSample">填入当前课程</button>
          <span v-if="courseFileName" class="file-name">{{ courseFileName }}</span>
        </div>
        <textarea
          v-model="courseText"
          class="import-area"
          spellcheck="false"
          placeholder="课程代码,课程名称,学分,类型,任课教师,上课时间,教师邮箱,教师电话,办公室,答疑时间&#10;CS201,数据结构,4,必修,周立群,周一 1-2 节,zhoulq@cs.univ.edu.cn,138-0013-8001,信息楼 A503,周二 14:00-16:00&#10;CS301,数据库原理,3,必修,赵敏,周四 3-4 节,zhaomin@cs.univ.edu.cn,138-0013-8099,信息楼 B401,周五 10:00-12:00"
        ></textarea>
        <div class="import-actions">
          <button class="btn primary" :disabled="courseImporting" @click="runCourseImport">
            {{ courseImporting ? "导入中…" : "导入课程与教师" }}
          </button>
          <span class="tiny muted">
            代码已存在则更新任课教师与联系方式；新代码会在学生端作为「待开课」展示，不参与预警计算。
          </span>
        </div>

        <div v-if="courseResult" class="import-result">
          <span class="ok">更新 {{ courseResult.updated }} 门</span>
          <span class="ok">新增 {{ courseResult.added }} 门</span>
          <span v-if="courseResult.failed.length" class="bad">
            失败 {{ courseResult.failed.length }}
          </span>
          <ul v-if="courseResult.failed.length">
            <li v-for="f in courseResult.failed" :key="f.line">
              第 {{ f.line }} 行 · {{ f.text }}：{{ f.reason }}
            </li>
          </ul>
          <div v-if="!courseResult.persistent" class="tiny warn">
            当前环境不可写盘，本次导入只在本次运行内有效。
          </div>
        </div>
      </div>

      <div class="import-right">
        <div class="acc-stats" style="grid-template-columns: repeat(2, 1fr)">
          <div>
            <b>{{ curriculum?.courses.length ?? 0 }}</b><span>课程</span>
          </div>
          <div>
            <b>{{ curriculum?.teachers.length ?? 0 }}</b><span>任课教师</span>
          </div>
        </div>
        <div class="tiny muted" style="margin: -6px 0 8px">
          最近更新 {{ curriculum?.updated_at || "内置数据" }}
        </div>
        <div class="acc-list">
          <div v-if="!curriculum?.courses.length" class="tiny muted empty">还没有课程数据。</div>
          <div v-for="c in curriculum?.courses" :key="c.code" class="course-row">
            <div class="course-row-top">
              <span class="mono">{{ c.code }}</span>
              <span class="acc-name">{{ c.name }}</span>
              <span class="tiny muted">{{ c.teacher }}</span>
            </div>
            <div class="tiny muted course-row-meta">
              {{ c.teacher_profile?.email || "未填邮箱" }} ·
              {{ c.teacher_profile?.phone || "未填电话" }}
              <template v-if="c.teacher_profile?.office"> · {{ c.teacher_profile.office }}</template>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <p class="tiny muted" style="margin: 14px 2px 0">
    规则配置对全校立即生效，可用于演示不同学校的预警线差异。当前接入 {{ app.schools.length }} 所学校的校规知识库。
  </p>
  </template>
</template>

<style scoped>
.import-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
  gap: 16px;
}
.import-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.file-btn {
  position: relative;
  overflow: hidden;
  cursor: pointer;
}
.file-btn input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}
.file-name {
  font-size: 11.5px;
  color: var(--muted);
}
.import-area {
  width: 100%;
  min-height: 132px;
  resize: vertical;
  border: 1px solid var(--line-strong);
  border-radius: 9px;
  padding: 10px 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text);
  background: #fcfcfd;
  outline: none;
}
.import-area:focus {
  border-color: var(--brand);
  box-shadow: 0 0 0 3px rgba(29, 78, 216, 0.1);
}
.import-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 10px;
}
.import-result {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
  margin-top: 12px;
  padding: 9px 11px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: #fbf7ef;
  font-size: 12.5px;
}
.import-result .ok {
  color: var(--green);
}
.import-result .warn {
  color: var(--amber);
}
.import-result .bad {
  color: var(--red);
}
.import-result ul {
  margin: 0;
  padding-left: 18px;
  width: 100%;
  color: var(--red);
  font-size: 11.5px;
  line-height: 1.7;
}
.acc-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-bottom: 10px;
}
.acc-stats > div {
  border: 1px solid var(--line);
  border-radius: 9px;
  padding: 8px 10px;
  background: #fbf7ef;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.acc-stats b {
  font-size: 17px;
  color: var(--text);
}
.acc-stats span {
  font-size: 11px;
  color: var(--muted);
}
.acc-list {
  border: 1px solid var(--line);
  border-radius: 9px;
  max-height: 190px;
  overflow: auto;
  background: #fff;
}
.acc-list .empty {
  padding: 14px;
}
.acc-row {
  display: grid;
  grid-template-columns: 84px 1fr auto auto;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-bottom: 1px solid #f1f3f5;
  font-size: 12px;
}
.acc-row:last-child {
  border-bottom: 0;
}

/* 课程与教师清单 */
.course-row {
  padding: 8px 10px;
  border-bottom: 1px solid #f1f3f5;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.course-row:last-child {
  border-bottom: 0;
}
.course-row-top {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  min-width: 0;
}
.course-row-top .acc-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.course-row-meta {
  line-height: 1.5;
  word-break: break-all;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--text);
}
.acc-name {
  color: var(--text-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.acc-flag {
  font-size: 10.5px;
  padding: 1px 6px;
  border-radius: 4px;
  background: #fef3c7;
  color: #92400e;
}
.acc-flag.used {
  background: var(--green-soft);
  color: var(--green);
}

@media (max-width: 1000px) {
  .import-grid {
    grid-template-columns: 1fr;
  }
}
</style>
