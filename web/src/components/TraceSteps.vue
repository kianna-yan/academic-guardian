<script setup lang="ts">
import { computed, ref } from "vue";
import type { ChatTrace } from "@/types";

const props = defineProps<{ trace: ChatTrace[]; pending?: boolean; elapsed?: number }>();

/** 工具名 → 人话。Agent 的"思考过程"必须让人看得懂，否则轨迹没有意义。 */
const LABEL: Record<string, string> = {
  risk_score: "查风险评分",
  interventions: "取干预建议",
  retrieve_policy: "检索校规库",
  search_policy: "检索校规库",
  roster: "查风险名单",
  campus_overview: "统计全校数据",
  grade_trend: "拉成绩走势",
  counselor_brief: "生成谈话要点",
  record_intervention: "写入干预台账",
  llm_polish: "大模型润色",
  llm_route: "模型选工具",
  vision: "看图",
  asr: "听语音",
  text: "读文本",
  recall_material: "取回上次的材料",
  get_student: "查学生档案",
  get_scores: "查成绩",
  get_class_scores: "查班级成绩",
  get_timetable: "查课表",
  get_final_forecast: "算期末目标分",
  get_todos: "查待办",
  get_curriculum: "查培养方案",
  get_letter: "取告知函",
  get_interventions: "查干预台账",
  get_class_report: "班级简报",
  get_messages: "查家校消息",
  get_appeals: "查异议进度",
  get_courses: "查课程",
  get_attendance: "查考勤",
  get_homework: "查作业",
  get_risk: "查风险分",
  get_overview: "全校统计",
  get_classroom: "查课堂学情",
  get_learning_track: "查学习轨迹",
};

const steps = computed(() =>
  (props.trace || []).map((t) => ({
    label: t.label || LABEL[t.tool] || t.tool,
    ms: t.ms,
    args: t.args,
    detail: t.detail,
  })),
);

/** 检索明细：一条消息里最多展示一次（同轮多次检索取最后一次） */
const rag = computed(() => {
  const hit = [...(props.trace || [])].reverse().find((t) => t.retrieval);
  return hit?.retrieval || null;
});

const open = ref(false);

const channelName = computed(() => {
  const c = rag.value?.channel || "";
  return (
    { hybrid: "关键词 + 语义混合", bm25: "关键词（BM25）", "bm25+local-vector": "关键词 + 本地向量" }[c] || c
  );
});
</script>

<template>
  <div class="trace-wrap">
    <div v-if="steps.length || pending" class="trace">
      <span
        v-for="(s, i) in steps"
        :key="`${s.label}-${i}`"
        class="trace-step"
        :title="s.detail || JSON.stringify(s.args)"
      >
        <i class="dot"></i>{{ s.label }}<em v-if="s.ms >= 1">{{ Math.round(s.ms) }}ms</em>
      </span>
      <span v-if="pending" class="trace-step running"><i class="dot"></i>正在处理</span>
      <span v-if="elapsed !== undefined && elapsed > 0" class="trace-total">{{ elapsed }} ms</span>
    </div>

    <!-- 检索过程：评委问「这条规定哪来的」，答案就在这儿 -->
    <div v-if="rag" class="rag">
      <button type="button" class="rag-head" @click="open = !open">
        <span class="rag-tag">RAG</span>
        <span class="rag-flow">
          <em>{{ rag.query }}</em>
          <template v-if="rag.rewritten"> → <em class="rw">{{ rag.rewritten }}</em></template>
        </span>
        <span class="rag-stat">
          {{ channelName }} · 候选 {{ rag.candidates }} → 命中 {{ rag.hits?.length || 0 }}
          <template v-if="rag.ms"> · {{ Math.round(rag.ms) }}ms</template>
        </span>
        <span class="rag-more">{{ open ? "收起" : "展开" }}</span>
      </button>
      <div v-if="open" class="rag-body">
        <div v-for="h in rag.hits" :key="h.rank" class="rag-row">
          <span class="rag-rank">#{{ h.rank }}</span>
          <span class="rag-path">{{ h.path }}</span>
          <span class="rag-score">{{ h.score }}</span>
          <span class="rag-why">{{ h.why }}</span>
        </div>
        <div v-if="!rag.hits?.length" class="rag-empty">这一问没有过阈值的条款，回答里不会出现引用。</div>
        <div v-if="rag.added_terms?.length" class="rag-terms">
          同义扩展：{{ rag.added_terms.join("、") }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.trace-wrap {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.trace-step em {
  font-style: normal;
  color: #b09b85;
  font-size: 10px;
  margin-left: 2px;
}

/* ---- 检索过程 ---- */
.rag {
  border: 1px solid #ecdfca;
  border-radius: 8px;
  background: #fdfaf4;
  overflow: hidden;
}
.rag-head {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  padding: 5px 9px;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
  font-family: inherit;
  font-size: 10.5px;
  color: #8a7458;
  flex-wrap: wrap;
}
.rag-head:hover {
  background: #f9f2e6;
}
.rag-tag {
  flex: 0 0 auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.4px;
  color: #fff;
  background: var(--brand);
  border-radius: 4px;
  padding: 1px 5px;
}
.rag-flow {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rag-flow em {
  font-style: normal;
  color: #6b563e;
}
.rag-flow em.rw {
  color: #a8814e;
}
.rag-stat {
  flex: 0 0 auto;
  color: #a08a72;
  font-variant-numeric: tabular-nums;
}
.rag-more {
  margin-left: auto;
  color: var(--brand);
  flex: 0 0 auto;
}
.rag-body {
  border-top: 1px dashed #ecdfca;
  padding: 6px 9px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.rag-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 10.5px;
  color: #7a6450;
}
.rag-rank {
  flex: 0 0 auto;
  font-family: ui-monospace, monospace;
  color: #b09b85;
}
.rag-path {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #5b4632;
}
.rag-score {
  flex: 0 0 auto;
  color: #8a6a45;
  font-variant-numeric: tabular-nums;
}
.rag-why {
  flex: 0 0 auto;
  color: #b09b85;
}
.rag-terms,
.rag-empty {
  font-size: 10px;
  color: #a08a72;
  padding-top: 2px;
}
</style>
