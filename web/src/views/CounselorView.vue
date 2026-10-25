<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { api } from "@/api/client";
import LetterDialog from "@/components/LetterDialog.vue";
import StatGrid from "@/components/StatGrid.vue";
import StudentDrawer from "@/components/StudentDrawer.vue";
import { useNarrow } from "@/composables/useViewport";
import { useAppStore } from "@/stores/app";
import type { Citation, RosterRow } from "@/types";

const app = useAppStore();
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
  <Teleport to="#top-actions">
    <div class="top-filters">
      <!--
        这里刻意用原生 select 而不是 el-select：
        跨组件 Teleport 里有状态组件时，视图重渲染会让 Vue 拿上一次的 vnode 去 patch，
        而那个 vnode 的 component 已经被置空，压缩构建下会抛
        "Cannot read properties of null (reading 'emitsOptions')"。原生元素没有这个问题。
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
  </Teleport>

  <StatGrid :items="stats" />

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
        </div>
        <div class="m-side">
          <span class="score-chip" :class="r.level">{{ r.score }}</span>
          <span
            :class="{
              'trend-up': r.direction === 'up',
              'trend-down': r.direction === 'down',
              'trend-flat': r.direction === 'flat',
            }"
          >
            {{ r.direction === "up" ? "↑" : r.direction === "down" ? "↓" : "→" }}
            {{ Math.abs(r.delta).toFixed(0) }}
          </span>
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
        <el-table-column label="学生" min-width="116">
          <template #default="{ row }">
            <div class="stu-cell">
              <b>{{ row.name }}</b>
              <span class="tiny muted">{{ row.id }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="class_name" label="班级" width="96" />
        <el-table-column label="风险分" width="74">
          <template #default="{ row }">
            <span class="score-chip" :class="row.level">{{ row.score }}</span>
          </template>
        </el-table-column>
        <el-table-column label="等级" width="58">
          <template #default="{ row }">
            <span class="level-pill" :class="row.level" style="font-size: 11px">
              {{ row.level === "red" ? "红" : row.level === "yellow" ? "黄" : "绿" }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="趋势" width="62">
          <template #default="{ row }">
            <span
              :class="{
                'trend-up': row.direction === 'up',
                'trend-down': row.direction === 'down',
                'trend-flat': row.direction === 'flat',
              }"
            >
              {{ row.direction === "up" ? "↑" : row.direction === "down" ? "↓" : "→" }}
              {{ Math.abs(row.delta).toFixed(0) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="top_factor" label="主因" min-width="88">
          <template #default="{ row }">
            <span class="muted">{{ row.top_factor }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="absent" label="缺勤" width="60" align="right" />
        <el-table-column prop="missed_hw" label="作业未交" width="78" align="right" />
        <el-table-column prop="mid_avg" label="期中均分" width="78" align="right" />
        <el-table-column label="" width="70">
          <template #default>
            <span class="tiny nowrap" style="color: var(--brand)">查看 →</span>
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
  line-height: 1.35;
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
  border-bottom: 1px solid #f1f2f4;
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
</style>
