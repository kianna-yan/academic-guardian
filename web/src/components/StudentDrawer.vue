<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { api, downloadDoc } from "@/api/client";
import ActionList from "@/components/ActionList.vue";
import FactorBars from "@/components/FactorBars.vue";
import GradeTrend from "@/components/GradeTrend.vue";
import RiskRing from "@/components/RiskRing.vue";
import { useChatStore } from "@/stores/chat";
import type { StudentDetail } from "@/types";

const props = defineProps<{ modelValue: boolean; sid: string | null }>();
const emit = defineEmits<{
  (e: "update:modelValue", v: boolean): void;
  (e: "letter", type: "student" | "counselor"): void;
}>();

const chat = useChatStore();

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

/* 看完图直接追问：点名该生的走势，把图变成对话的开头 */
function askTrend() {
  if (!props.sid || !detail.value) return;
  const name = detail.value.student.name;
  chat.ask("counselor", props.sid, `${name} 的成绩走势说明什么？该重点关注哪门课？`);
}

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
          <!-- 文书导出：告知函/通知书/家长信，落成 Word 打印归档 -->
          <div class="drawer-exports">
            <button class="chip" @click="downloadDoc(`/api/export/letter/${sid}?type=counselor`)">谈话要点</button>
            <button class="chip" @click="downloadDoc(`/api/export/letter/${sid}?type=student`)">告知函</button>
            <button class="chip" @click="downloadDoc(`/api/export/notice/${sid}`)">通知书</button>
            <button class="chip" @click="downloadDoc(`/api/export/letter/${sid}?type=parent`)">家长信</button>
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

      <h3 class="sec">
        成绩走势
        <button
          v-if="detail.grade_trend && detail.grade_trend.terms.length"
          class="ask-ai"
          @click="askTrend"
        >问 AI：这条线说明什么？</button>
      </h3>
      <div v-if="detail.grade_trend && detail.grade_trend.terms.length" class="sec-body">
        <GradeTrend :trend="detail.grade_trend" :height="196" />
        <div v-if="detail.grade_trend.courses.length" class="mini-list">
          <div
            v-for="c in detail.grade_trend.courses.slice(0, 6)"
            :key="c.code"
            class="mini-row"
          >
            <span class="mini-name">{{ c.name }}</span>
            <span class="mini-pts">
              {{ c.points.map((p) => p.score).join(" → ") }}
            </span>
            <span class="mini-d" :class="c.trend">
              {{ c.delta > 0 ? "+" : "" }}{{ c.delta }}
            </span>
          </div>
        </div>
      </div>
      <div v-else class="tiny muted">暂无成绩历史</div>

      <h3 class="sec">这次要解决的是什么</h3>
      <div v-if="detail.advice" class="dx">
          <span class="dx-pill">{{ detail.advice.pattern_label }}</span>
          <p class="dx-note">{{ detail.advice.diagnosis }}</p>
          <ul class="dx-ev">
            <li v-for="e in detail.advice.evidence" :key="e">{{ e }}</li>
          </ul>
          <p class="dx-tip"><b>谈话切入：</b>{{ detail.advice.counselor_tip }}</p>
          <ol v-if="detail.advice.first_steps.length" class="dx-steps">
            <li v-for="s in detail.advice.first_steps" :key="s">{{ s }}</li>
          </ol>
      </div>

      <h3 class="sec">可以立刻安排的事</h3>
      <ActionList :actions="detail.actions" :limit="3" :show-priority="true" />

      <template v-if="detail.advice">
        <h3 class="sec">可以转介的资源</h3>
        <div class="sup-list">
          <div v-for="s in detail.advice.support" :key="s.kind" class="sup-item">
            <b>{{ s.kind }}</b>
            <span class="tiny muted">{{ s.text }}</span>
            <span v-if="s.contact" class="tiny sup-contact">{{ s.contact }}</span>
          </div>
        </div>

        <h3 class="sec">复查节点</h3>
        <div class="tiny watch">
          <b>{{ detail.advice.watch.when }}</b> · {{ detail.advice.watch.what }}
        </div>
      </template>

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
  display: flex;
  align-items: center;
  gap: 8px;
}
.ask-ai {
  border: 1px solid #f0d9b5;
  background: #fdf1de;
  color: #4338ca;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 9px;
  border-radius: 99px;
  cursor: pointer;
  white-space: nowrap;
}
.ask-ai:hover {
  background: #f8e8cc;
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
}.drawer-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
/* 归因卡片：先说性质，再摆证据 */
.dx {
  border: 1px solid var(--line);
  border-left: 3px solid var(--brand);
  border-radius: 8px;
  padding: 10px 12px;
  background: color-mix(in srgb, var(--brand) 4%, transparent);
}
.dx-pill {
  display: inline-block;
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 999px;
  color: var(--brand);
  background: color-mix(in srgb, var(--brand) 14%, transparent);
  margin-bottom: 6px;
}
.dx-note {
  margin: 0 0 8px;
  font-size: 12.5px;
  line-height: 1.65;
  color: var(--text-1);
}
.dx-ev {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  color: var(--text-2);
}
.dx-ev li {
  margin: 3px 0;
  line-height: 1.6;
}
.dx-tip {
  margin: 9px 0 0;
  padding-top: 8px;
  border-top: 1px dashed var(--line);
  font-size: 12px;
  line-height: 1.65;
  color: var(--text-2);
}
.dx-steps {
  margin: 8px 0 0;
  padding-left: 17px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-2);
}
.sup-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}.sup-item {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
  align-items: baseline;
  font-size: 12.5px;
  padding: 6px 10px;
  border: 1px solid var(--line);
  border-radius: 7px;
}
.sup-contact {
  color: var(--brand);
  margin-left: auto;
}
.watch {
  padding: 7px 10px;
  border-radius: 7px;
  border: 1px dashed var(--line);
}
/* 成绩走势：上面图，下面每门课的分数序列 */
.sec-body {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px 12px 8px;
}
.mini-list {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed var(--line);
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.mini-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto 42px;
  gap: 8px;
  align-items: center;
  font-size: 11.5px;
}
.mini-name {
  color: var(--text-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mini-pts {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.mini-d {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.mini-d.up {
  color: var(--green);
}
.mini-d.down {
  color: var(--red);
}
.mini-d.flat {
  color: var(--muted);
}
/* 文书导出胶囊：点名下载，打印归档 */
.drawer-exports {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.drawer-exports .chip {
  cursor: pointer;
}
</style>
