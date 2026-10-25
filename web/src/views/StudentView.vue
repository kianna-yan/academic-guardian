<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { api } from "@/api/client";
import ActionList from "@/components/ActionList.vue";
import FactorBars from "@/components/FactorBars.vue";
import RiskRing from "@/components/RiskRing.vue";
import { useAppStore } from "@/stores/app";
import type { Course, StudentDetail } from "@/types";

const app = useAppStore();
const detail = ref<StudentDetail | null>(null);
const loading = ref(true);
const error = ref("");
const appeal = reactive({ open: false, text: "", sending: false });

const sid = computed(() => app.meta?.demo?.student || "");

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

watch(() => app.meta, (m) => m && load(), { immediate: true });

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

async function submitAppeal() {
  if (!appeal.text.trim() || !sid.value) return;
  appeal.sending = true;
  try {
    await api.addIntervention(sid.value, {
      title: `复核申请：${appeal.text.trim().slice(0, 20)}`,
      note: appeal.text.trim(),
      status: "待人工复核",
    });
    appeal.text = "";
    appeal.open = false;
    ElMessage.success("已提交，辅导员会在 3 个工作日内人工核实");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.message || "提交失败");
  } finally {
    appeal.sending = false;
  }
}
</script>

<template>
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

<style scoped>
.note-line {
  margin: 14px 0 0;
  padding-top: 12px;
  border-top: 1px dashed var(--line);
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
