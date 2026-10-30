<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus/es/components/message/index";
import { api, downloadDoc } from "@/api/client";
import ChatHome from "@/components/ChatHome.vue";
import DashNav from "@/components/DashNav.vue";
import LetterDialog from "@/components/LetterDialog.vue";
import RegionBand from "@/components/RegionBand.vue";
import StatGrid from "@/components/StatGrid.vue";
import StudentDrawer from "@/components/StudentDrawer.vue";
import TrendSpark from "@/components/TrendSpark.vue";
import { useNarrow } from "@/composables/useViewport";
import { useAppStore } from "@/stores/app";
import { useChatStore } from "@/stores/chat";
import type { Citation, RosterRow } from "@/types";

const app = useAppStore();
const chat = useChatStore();
// 手机屏只留关键列，其余列在抽屉里看
const narrow = useNarrow();

const rows = ref<RosterRow[]>([]);
const total = ref(0);
const loading = ref(false);
const filters = reactive({ class_name: "", level: "" });

const drawer = reactive({ open: false, sid: "" });
const dialog = reactive({
  open: false,
  title: "",
  subject: "",
  body: "",
  citations: [] as Citation[],
});

const stats = computed(() => {
  const red = rows.value.filter((r) => r.level === "red").length;
  const yellow = rows.value.filter((r) => r.level === "yellow").length;
  const rising = rows.value.filter((r) => r.direction === "up" && r.level !== "green").length;
  const avg = rows.value.length
    ? (rows.value.reduce((a, b) => a + b.score, 0) / rows.value.length).toFixed(1)
    : "0";
  return [
    { value: red, label: "红色预警 · 本周需谈话", tone: "red" as const },
    { value: yellow, label: "黄色关注 · 持续观察", tone: "amber" as const },
    { value: rising, label: "风险较上学期上升", tone: "" as const },
    { value: avg, label: "平均风险分", tone: "" as const },
  ];
});

async function load() {
  loading.value = true;
  try {
    const res = await api.students({
      class_name: filters.class_name || undefined,
      level: filters.level || undefined,
      limit: 300,
    });
    rows.value = res.rows;
    total.value = res.total;
  } catch (e: any) {
    ElMessage.error(e?.message || "名单加载失败");
  } finally {
    loading.value = false;
  }
}

watch(() => [filters.class_name, filters.level], load);
onMounted(load);

/* 名单里的成绩走势：只给方向和名次，具体分数点进抽屉看 */
function gtTitle(row: RosterRow) {
  const pts = (row.trend_points || []).map((v) => v.toFixed(1)).join(" → ");
  return `${row.trend_label}｜班级第 ${row.trend_rank} / ${row.trend_rank_total} 名\n${pts}\n大一上 → 大三上（期中），前四项为学期总评`;
}

function openStudent(row: RosterRow) {
  drawer.sid = row.id;
  drawer.open = true;
}

async function openReport() {
  const cls = filters.class_name || app.classes[0];
  if (!cls) return;
  try {
    const r = await api.report(cls);
    dialog.title = r.title;
    dialog.subject = r.subject;
    dialog.body = r.body;
    dialog.citations = r.citations || [];
    dialog.open = true;
  } catch (e: any) {
    ElMessage.error(e?.message || "生成失败");
  }
}

async function openLetter(type: "student" | "counselor") {
  if (!drawer.sid) return;
  try {
    const l = await api.letter(drawer.sid, type);
    dialog.title = l.title;
    dialog.subject = l.subject;
    dialog.body = l.body;
    dialog.citations = l.citations || [];
    dialog.open = true;
  } catch (e: any) {
    ElMessage.error(e?.message || "生成失败");
  }
}
</script>

<template>
  <!-- 对话是主入口：进来就是整页 AI 问答，预警名单按键前往 -->
  <ChatHome v-if="chat.homeMode === 'chat'" role="counselor" :sid="null" />

  <template v-else>
    <DashNav />

    <div class="view-actions">
      <button class="btn" @click="downloadDoc('/api/export/interventions')">导出干预台账 Word</button>
      <button class="btn" @click="downloadDoc('/api/export/daily-report')">今日预警日报</button>
    </div>
    <div class="top-filters">
      <!--
        这里刻意用原生 select 而不是 el-select：
        el-select 是带内部状态的组件，在“整页重渲染 + 视口切换”交替发生时会
        拿旧的 vnode 去 patch，压缩构建下抛 "Cannot read properties of null (reading 'emitsOptions')"。
        原生元素没有内部实例，重渲染多少次都只是改属性，最稳。
      -->
      <select v-model="filters.class_name" class="sel" aria-label="按班级筛选">
        <option value="">全部班级</option>
        <option v-for="c in app.classes" :key="c" :value="c">{{ c }}</option>
      </select>
      <select v-model="filters.level" class="sel" aria-label="按等级筛选">
        <option value="">全部等级</option>
        <option value="red">仅红色预警</option>
        <option value="yellow">仅黄色关注</option>
      </select>
      <button class="btn" @click="openReport">生成班级周报</button>
    </div>

  <StatGrid :items="stats" />

  <RegionBand id="roster" no="01" title="风险名单" tone="risk"
    desc="按风险分排序，点一行看画像与这周先做什么" />

  <div class="card">
    <div class="card-head">
      <h3>风险名单（共 {{ total }} 人）</h3>
      <span class="hint">按风险分降序，点击任意一行查看详情</span>
    </div>

    <!-- 手机端不用表格：列太多必然横向溢出，改成列表，点一行进抽屉。
         这里刻意用 v-show 而不是 v-if：el-table 被销毁再重建时，Element Plus 内部的列注册
         会在已卸载的实例上派发事件（控制台抛 emitsOptions 空指针），保持挂载只切显示最稳。 -->
    <div v-show="narrow" class="m-list">
      <div v-for="r in rows" :key="r.id" class="m-row" @click="openStudent(r)">
        <div class="m-main">
          <b>{{ r.name }}</b>
          <span class="tiny muted">{{ r.id }} · {{ r.class_name }} · {{ r.top_factor }}</span>
          <span class="tiny m-adv">{{ r.pattern_label }} · {{ r.advice_tag }}</span>
        </div>
        <div class="m-side">
          <TrendSpark
            :points="r.trend_points || []"
            :width="52"
            :height="20"
            :direction="r.trend_direction"
          />
          <span class="score-chip" :class="r.level">{{ r.score }}</span>
        </div>
      </div>
      <div v-if="!rows.length" class="empty">没有符合条件的学生</div>
    </div>

    <div v-show="!narrow" class="table-wrap">
      <el-table
        v-loading="loading"
        :data="rows"
        style="width: 100%"
        :row-style="{ cursor: 'pointer' }"
        @row-click="openStudent"
      >
        <!-- 学生单元格里带上三项事实，省掉三列，把宽度留给「本周先做」 -->
        <el-table-column label="学生 / 事实" min-width="182">
          <template #default="{ row }">
            <div class="stu-cell">
              <b>{{ row.name }}</b>
              <span class="tiny muted">{{ row.id }} · {{ row.class_name }}</span>
              <span class="tiny fact-line">
                缺勤 {{ row.absent }} · 未交 {{ row.missed_hw }} · 期中 {{ row.mid_avg }}
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="风险分" width="74">
          <template #default="{ row }">
            <div class="risk-cell">
              <span class="score-chip" :class="row.level">{{ row.score }}</span>
              <!-- 风险分相对上学期的变化，和「成绩走势」是两回事：一个看风险，一个看分数 -->
              <span
                class="rd"
                :class="{
                  'trend-up': row.direction === 'up',
                  'trend-down': row.direction === 'down',
                  'trend-flat': row.direction === 'flat',
                }"
              >
                {{ row.direction === "up" ? "↑" : row.direction === "down" ? "↓" : "→" }}
                {{ Math.abs(row.delta).toFixed(0) }}
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="等级" width="56">
          <template #default="{ row }">
            <span class="level-pill" :class="row.level" style="font-size: 11px">
              {{ row.level === "red" ? "红" : row.level === "yellow" ? "黄" : "绿" }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="成绩走势" width="112">
          <template #default="{ row }">
            <!-- el-table 的作用域插槽给的是 DefaultRow（索引签名），
                 不是我们声明的 RosterRow，因此需要一次显式断言才能通过类型检查 -->
            <div class="gt-cell" :title="gtTitle(row as RosterRow)">
              <TrendSpark
                :points="row.trend_points || []"
                :width="88"
                :height="24"
                :direction="row.trend_direction"
              />
              <span class="gt-meta">
                <b>{{ row.trend_rank ? `第 ${row.trend_rank} 名` : "—" }}</b>
                <span
                  v-if="row.trend_rank_delta"
                  class="gt-delta"
                  :class="row.trend_rank_delta > 0 ? 'bad' : 'good'"
                >
                  {{ row.trend_rank_delta > 0 ? "↓" : "↑" }}{{ Math.abs(row.trend_rank_delta) }}
                </span>
                <span v-else class="gt-delta flat">持平</span>
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="本周先做" min-width="204">
          <template #default="{ row }">
            <div class="adv-cell">
              <span class="pat-pill">{{ row.pattern_label }}</span>
              <span class="adv-line">{{ row.advice }}</span>
            </div>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty">没有符合条件的学生</div>
        </template>
      </el-table>
    </div>
  </div>

  <StudentDrawer v-model="drawer.open" :sid="drawer.sid" @letter="openLetter" />
  <LetterDialog
    v-model="dialog.open"
    :title="dialog.title"
    :subject="dialog.subject"
    :body="dialog.body"
    :citations="dialog.citations"
  />
  </template>
</template>

<style scoped>
/* 包一层容器：既能沿用 #top-actions 的横向排列，也让顶栏高度保持一致 */
.top-filters {
  display: contents;
}

/* 原生下拉框，外观对齐 .btn */
.sel {
  height: 34px;
  border-radius: 8px;
  border: 1px solid var(--line-strong);
  background: var(--card) no-repeat right 10px center;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'><path d='M2 4.5 6 8.5 10 4.5' fill='none' stroke='%236b7280' stroke-width='1.4' stroke-linecap='round' stroke-linejoin='round'/></svg>");
  background-size: 12px 12px;
  color: var(--text);
  font-size: 13px;
  padding: 0 30px 0 12px;
  appearance: none;
  -webkit-appearance: none;
  cursor: pointer;
}

.sel:hover {
  border-color: var(--brand);
}

.sel:focus-visible {
  outline: 2px solid var(--brand-soft);
  outline-offset: 1px;
  border-color: var(--brand);
}
.table-wrap {
  overflow-x: auto;
}
.stu-cell {
  display: flex;
  flex-direction: column;
  line-height: 1.4;
}
.fact-line {
  color: var(--text-3, var(--text-2));
  opacity: 0.85;
}
.nowrap {
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
  border-bottom: 1px solid #f0e7d8;
  cursor: pointer;
}
.m-row:last-child {
  border-bottom: 0;
}
.m-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.45;
}
.m-main b {
  font-size: 13.5px;
  font-weight: 500;
}
.m-main span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-side {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
}
.m-adv {
  color: var(--brand);
}
/* 名单上的"本周先做"：一句话建议 + 成因标签，不再是一列相同的话 */
.adv-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.pat-pill {
  align-self: flex-start;
  flex: none;
  font-size: 10.5px;
  line-height: 1.6;
  padding: 0 6px;
  border-radius: 5px;
  color: var(--brand);
  background: color-mix(in srgb, var(--brand) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--brand) 24%, transparent);
  white-space: nowrap;
}
/* 名单要能扫，建议压到两行，完整内容点进抽屉看 */
.adv-line {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 12.5px;
  color: var(--text-2);
  line-height: 1.5;
}
/* 风险分：分数 + 相对上学期的变化，两行放得下 */
.risk-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}
.rd {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
/* 成绩走势：迷你折线 + 当前名次与变化 */
.gt-cell {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.gt-meta {
  display: flex;
  align-items: baseline;
  gap: 5px;
  font-size: 10.5px;
  line-height: 1.3;
  color: var(--text-2);
}
.gt-meta b {
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
.gt-delta {
  font-size: 10.5px;
  line-height: 1.3;
  font-variant-numeric: tabular-nums;
}
.gt-delta.bad {
  color: var(--red);
}
.gt-delta.good {
  color: var(--green);
}
.gt-delta.flat {
  color: var(--muted);
}
</style>
