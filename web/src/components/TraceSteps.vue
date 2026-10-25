<script setup lang="ts">
import { computed } from "vue";
import type { ChatTrace } from "@/types";

const props = defineProps<{ trace: ChatTrace[]; pending?: boolean; elapsed?: number }>();

/** 工具名 → 人话。Agent 的"思考过程"必须让人看得懂，否则轨迹没有意义。 */
const LABEL: Record<string, string> = {
  risk_score: "查风险评分",
  interventions: "取干预建议",
  retrieve_policy: "检索校规库",
  roster: "查风险名单",
  campus_overview: "统计全校数据",
  llm_polish: "大模型润色",
};

const steps = computed(() =>
  (props.trace || []).map((t) => ({
    label: LABEL[t.tool] || t.tool,
    ms: t.ms,
    args: t.args,
  })),
);
</script>

<template>
  <div v-if="steps.length || pending" class="trace">
    <span
      v-for="(s, i) in steps"
      :key="`${s.label}-${i}`"
      class="trace-step"
      :title="JSON.stringify(s.args)"
    >
      <i class="dot"></i>{{ s.label }}<em v-if="s.ms >= 1">{{ Math.round(s.ms) }}ms</em>
    </span>
    <span v-if="pending" class="trace-step running"><i class="dot"></i>正在处理</span>
    <span v-if="elapsed !== undefined && elapsed > 0" class="trace-total">{{ elapsed }} ms</span>
  </div>
</template>

<style scoped>
.trace-step em {
  font-style: normal;
  color: #94a3b8;
  font-size: 10px;
  margin-left: 2px;
}
</style>
