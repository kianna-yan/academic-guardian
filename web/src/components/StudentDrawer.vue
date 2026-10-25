<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { api } from "@/api/client";
import ActionList from "@/components/ActionList.vue";
import FactorBars from "@/components/FactorBars.vue";
import RiskRing from "@/components/RiskRing.vue";
import type { StudentDetail } from "@/types";

const props = defineProps<{ modelValue: boolean; sid: string | null }>();
const emit = defineEmits<{
  (e: "update:modelValue", v: boolean): void;
  (e: "letter", type: "student" | "counselor"): void;
}>();

const detail = ref<StudentDetail | null>(null);
const loading = ref(false);
const error = ref("");
const note = ref("");
const saving = ref(false);
const savedTip = ref("");

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit("update:modelValue", v),
});

async function load(sid: string) {
  loading.value = true;
  error.value = "";
  try {
    detail.value = await api.student(sid);
  } catch (e: any) {
    error.value = e?.message || "加载失败";
  } finally {
    loading.value = false;
  }
}

watch(
  () => [props.modelValue, props.sid] as const,
  ([open, sid]) => {
    if (open && sid) load(sid);
  },
  { immediate: true },
);

async function addNote() {
  const text = note.value.trim();
  if (!text || !props.sid) return;
  saving.value = true;
  try {
    await api.addIntervention(props.sid, { title: text.slice(0, 30), note: text, status: "已记录" });
    note.value = "";
    savedTip.value = "已保存";
    await load(props.sid);
    setTimeout(() => (savedTip.value = ""), 1800);
  } catch (e: any) {
    error.value = e?.message || "保存失败";
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <el-drawer v-model="visible" title="学生详情" size="520px" :append-to-body="true">
    <div v-if="loading" class="empty"><span class="spinner"></span></div>

    <div v-else-if="error" class="empty">{{ error }}</div>

    <div v-else-if="detail">
      <div class="drawer-head">
        <RiskRing :score="detail.risk.score" :level="detail.risk.level" :size="132" />
        <div class="drawer-id">
          <h3>
            {{ detail.student.name }}
            <span class="level-pill" :class="detail.risk.level">{{ detail.risk.level_label }}</span>
          </h3>
          <div class="tiny muted">
            {{ detail.student.class_name }} · {{ detail.student.major }} · 辅导员
            {{ detail.student.advisor }}
          </div>
          <div class="tiny" style="margin-top: 6px">
            较上学期
            <b>{{ detail.risk.trend.delta > 0 ? "+" : "" }}{{ detail.risk.trend.delta.toFixed(0) }}</b>
            分（{{ detail.risk.trend.label }}）
          </div>
        </div>
      </div>

      <h3 class="sec">风险构成</h3>
      <FactorBars :items="detail.risk.factors" />

      <h3 class="sec">关键事实</h3>
      <ul class="facts">
        <li>
          缺勤 {{ detail.risk.raw.absent }} / {{ detail.risk.raw.sessions }} 次，作业
          {{ detail.risk.raw.hw_submitted }}/{{ detail.risk.raw.hw_assigned }}
        </li>
        <li>
          期中加权均分 {{ detail.risk.raw.mid_avg }}，班级均分 {{ detail.risk.raw.cohort_avg }}
        </li>
        <li>
          上学期 GPA {{ detail.student.history.gpa }}，累计挂科
          {{ detail.student.history.failed_credits }} 学分
        </li>
        <li>
          平台每周登录 {{ detail.student.engagement.weekly_logins }} 次，{{
            detail.student.engagement.days_since_active
          }}
          天未活跃
        </li>
      </ul>

      <h3 class="sec">建议先做的三件事</h3>
      <ActionList :actions="detail.actions" :limit="3" :show-priority="false" />

      <h3 class="sec">跟踪记录</h3>
      <div v-if="detail.interventions.length" class="iv-list">
        <div v-for="i in detail.interventions" :key="i.id" class="iv-item">
          <b>{{ i.title }}</b> · {{ i.status }} · {{ i.created_at }}
          <span v-if="i.note" class="muted"> · {{ i.note }}</span>
        </div>
      </div>
      <div v-else class="tiny muted">暂无记录</div>

      <div class="iv-form">
        <el-input
          v-model="note"
          placeholder="记录一次谈话/联系，例如：已约周三下午面谈"
          @keyup.enter="addNote"
        />
        <button class="btn sm" :disabled="saving || !note.trim()" @click="addNote">
          {{ savedTip || "添加记录" }}
        </button>
      </div>
    </div>

    <template #footer>
      <div class="drawer-foot">
        <button class="btn" @click="emit('letter', 'counselor')">生成谈话要点</button>
        <button class="btn primary" @click="emit('letter', 'student')">生成告知函</button>
      </div>
    </template>
  </el-drawer>
</template>

<style scoped>
.drawer-head {
  display: flex;
  gap: 18px;
  align-items: center;
  margin-bottom: 6px;
}
.drawer-id {
  min-width: 0;
}
.drawer-id h3 {
  margin: 0 0 4px;
  font-size: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.sec {
  font-size: 13.5px;
  margin: 18px 0 8px;
}
.facts {
  margin: 0;
  padding-left: 18px;
  font-size: 12.5px;
  color: var(--text-2);
}
.facts li {
  margin: 4px 0;
}
.iv-list {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 4px 10px;
}
.iv-item {
  font-size: 12px;
  padding: 5px 0;
  border-bottom: 1px dashed var(--line);
}
.iv-item:last-child {
  border-bottom: 0;
}
.iv-form {
  display: flex;
  gap: 8px;
  margin-top: 10px;
  align-items: center;
}
.drawer-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
