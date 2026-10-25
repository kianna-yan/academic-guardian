<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "@/api/client";
import ClassCompare from "@/components/ClassCompare.vue";
import DistDonut from "@/components/DistDonut.vue";
import FactorBars from "@/components/FactorBars.vue";
import StatGrid from "@/components/StatGrid.vue";
import { useAppStore } from "@/stores/app";

const app = useAppStore();
const loading = ref(true);
const saving = ref(false);
const message = ref("");

const cfg = reactive({ red_line: 55, yellow_line: 35, absence_pct: 25 });

const overview = computed(() => app.overview);

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

onMounted(load);

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
  <Teleport to="#top-actions">
    <span class="badge" style="background: #eff6ff; color: #1d4ed8">规则版本 v1.2</span>
    <button class="btn" @click="exportCSV">导出预警名单</button>
  </Teleport>

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

  <p class="tiny muted" style="margin: 14px 2px 0">
    规则配置对全校立即生效，可用于演示不同学校的预警线差异。当前接入 {{ app.schools.length }} 所学校的校规知识库。
  </p>
</template>
