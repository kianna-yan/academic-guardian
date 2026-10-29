<script setup lang="ts">
import { computed, ref } from "vue";
import { ElMessage } from "element-plus/es/components/message/index";
import { useChatStore } from "@/stores/chat";
import type { ClassroomStudent } from "@/types";

/**
 * 教师版学生档案。
 * 和辅导员抽屉刻意不一样：这里只有「这名学生在我这门课上」发生过的事。
 * 老师不在系统里写谈话记录、不安排帮扶、不发告知函——那越界了，
 * 老师能做的只有两件：课上怎么对待他，以及要不要反馈给辅导员。
 */
const props = defineProps<{
  modelValue: boolean;
  stu: ClassroomStudent | null;
}>();
const emit = defineEmits<{ (e: "update:modelValue", v: boolean): void }>();

const chat = useChatStore();
const showAllAtt = ref(false);
const showAllHw = ref(false);

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit("update:modelValue", v),
});

const s = computed(() => props.stu);

/** 异常考勤排前面：老师打开抽屉就是为了看「他为什么没来」 */
const attRows = computed(() => {
  const rows = s.value?.attendance || [];
  const bad = rows.filter((r) => r.status !== "present");
  const ok = rows.filter((r) => r.status === "present");
  return [...bad, ...ok];
});
const badAtt = computed(() => (s.value?.attendance || []).filter((r) => r.status !== "present"));
const attShown = computed(() => (showAllAtt.value ? attRows.value : attRows.value.slice(0, 8)));

const hwRows = computed(() => s.value?.homework || []);
const hwShown = computed(() => (showAllHw.value ? hwRows.value : hwRows.value.slice(0, 5)));

const gapText = computed(() => {
  const g = s.value?.gap ?? 0;
  return `${g > 0 ? "+" : ""}${g}`;
});

/** 给学生的课堂反馈：老师说话的口气，短、具体、留一步 */
const feedback = computed(() => {
  const v = s.value;
  if (!v) return "";
  const bits: string[] = [];
  bits.push(`${v.name}同学：`);
  bits.push(`${v.course}这门课，你期中 ${v.midterm} 分，课堂均分 ${v.cohort_avg} 分（第 ${v.rank}/${v.rank_total} 名）。`);
  if (v.absent > 0) {
    bits.push(`本学期已上 ${v.sessions_held} 次课，缺勤 ${v.absent} 次${v.late ? `、迟到 ${v.late} 次` : ""}。`);
  }
  if (v.hw_missing > 0) {
    bits.push(`作业交了 ${v.hw_submitted}/${v.hw_assigned} 次，还差 ${v.hw_missing} 次，先把欠的交上来，这部分分数最好拿。`);
  }
  if (v.gap <= -10) {
    bits.push(`你现在比课堂均分低 ${Math.abs(v.gap)} 分，属于跟得吃力的那一档，课后可以来问我。`);
  } else if (v.gap >= 10) {
    bits.push(`你的成绩在班里比较靠前，如果还有余力，可以考虑把这门课往深里做一做。`);
  }
  bits.push(`下节课我会讲评这部分，有问题课上直接提。`);
  return bits.join("\n");
});

/** 反馈辅导员：只说事实，不评价人，方便导员直接转述 */
const toCounselor = computed(() => {
  const v = s.value;
  if (!v) return "";
  return [
    `辅导员你好，反馈一名学生在你班上的课堂情况：`,
    `${v.name}（${v.class_name}，学号 ${v.id}），本学期修我的《${v.course}》。`,
    `课堂事实：期中 ${v.midterm} 分（课堂均分 ${v.cohort_avg}，第 ${v.rank}/${v.rank_total} 名），`
      + `缺勤 ${v.absent} 次、迟到 ${v.late} 次，作业 ${v.hw_submitted}/${v.hw_assigned}。`,
    v.absent_streak >= 2 ? `其中连续缺勤 ${v.absent_streak} 次，可能不是临时有事。` : "",
    `系统风险分 ${v.score}（${v.level_label}），主因「${v.top_factor}」。`,
    `我这边会在课上多提问、作业单独提醒；如果需要面谈，麻烦你安排。`,
  ]
    .filter(Boolean)
    .join("\n");
});

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success("已复制，可直接粘贴到微信或邮件");
  } catch {
    ElMessage.warning("浏览器不允许自动复制，请手动选中文本");
  }
}

function askAI() {
  const v = s.value;
  if (!v) return;
  visible.value = false;
  chat.ask("teacher", null, `${v.name} 在我课上的情况怎么样？下一步该怎么帮他？`);
}
</script>

<template>
  <el-drawer v-model="visible" title="课堂档案（仅本课程）" size="520px" :append-to-body="true">
    <div v-if="!s" class="empty">选择一名学生</div>

    <template v-else>
      <div class="ts-head">
        <div class="ts-avatar">{{ s.name.slice(0, 1) }}</div>
        <div class="ts-id">
          <h3>
            {{ s.name }}
            <span class="level-pill" :class="s.level">{{ s.level_label }}</span>
          </h3>
          <div class="tiny muted">{{ s.class_name }} · {{ s.id }} · 风险分 {{ s.score }}</div>
          <div class="tiny muted">主因：{{ s.top_factor || "—" }}</div>
        </div>
      </div>

      <div class="ts-facts">
        <div class="f">
          <b>{{ s.midterm ?? "—" }}</b>
          <span>期中 · 课堂排名 {{ s.rank }}/{{ s.rank_total }}</span>
        </div>
        <div class="f">
          <b :class="{ bad: s.gap <= -10, good: s.gap >= 10 }">{{ gapText }}</b>
          <span>与课堂均分 {{ s.cohort_avg }} 之差</span>
        </div>
        <div class="f">
          <b :class="{ bad: s.absent > 2 }">{{ s.absent }}</b>
          <span>缺勤 / {{ s.sessions_held }} 次课</span>
        </div>
        <div class="f">
          <b :class="{ bad: s.hw_missing > 0 }">{{ s.hw_submitted }}/{{ s.hw_assigned }}</b>
          <span>作业提交</span>
        </div>
      </div>

      <p v-if="s.absent_streak >= 2" class="ts-warn">
        连续缺勤 {{ s.absent_streak }} 次 —— 连着不来通常不是临时有事，建议课前单独问一句。
      </p>

      <h3 class="sec">
        考勤明细
        <span class="tiny muted">异常 {{ badAtt.length }} 条 / 共 {{ attRows.length }} 条</span>
      </h3>
      <div class="att-list">
        <div
          v-for="(a, i) in attShown"
          :key="i"
          class="att-row"
          :data-st="a.status"
        >
          <span class="att-week">第{{ a.week }}周 {{ a.weekday }}</span>
          <span class="att-period">{{ a.period }}</span>
          <span class="att-date">{{ a.date }}</span>
          <span class="att-st">{{
            a.status === "absent" ? "旷课" : a.status === "late" ? "迟到" : "到课"
          }}</span>
        </div>
        <button
          v-if="attRows.length > 8"
          class="more"
          @click="showAllAtt = !showAllAtt"
        >{{ showAllAtt ? "收起" : `展开全部 ${attRows.length} 条` }}</button>
      </div>

      <h3 class="sec">
        作业明细
        <span class="tiny muted">未交 {{ s.hw_missing }} 次</span>
      </h3>
      <div class="hw-list">
        <div v-for="h in hwShown" :key="h.id" class="hw-row" :data-st="h.status">
          <b>{{ h.title }}</b>
          <span class="tiny muted">截止 {{ h.due }}</span>
          <span class="hw-st">{{
            h.status === "submitted" ? "已交" : h.status === "late" ? "迟交" : "未交"
          }}</span>
        </div>
        <button v-if="hwRows.length > 5" class="more" @click="showAllHw = !showAllHw">
          {{ showAllHw ? "收起" : `展开全部 ${hwRows.length} 次` }}
        </button>
      </div>

      <h3 class="sec">可以做的两件事</h3>
      <div class="act">
        <div class="act-head">
          <b>① 给学生一段课堂反馈</b>
          <button class="chip" @click="copy(feedback)">复制</button>
        </div>
        <pre class="txt">{{ feedback }}</pre>
      </div>
      <div class="act">
        <div class="act-head">
          <b>② 反馈给辅导员</b>
          <button class="chip" @click="copy(toCounselor)">复制</button>
        </div>
        <pre class="txt">{{ toCounselor }}</pre>
        <p class="tiny muted">
          任课教师不安排谈话、不出具告知函——那属于辅导员与教务的职责，这里只做事实反馈。
        </p>
      </div>

      <div class="ts-foot">
        <button class="btn primary" @click="askAI">问 AI：这名学生下一步怎么帮？</button>
      </div>
    </template>
  </el-drawer>
</template>

<style scoped>
.ts-head {
  display: flex;
  gap: 14px;
  align-items: center;
  margin-bottom: 14px;
}
.ts-avatar {
  width: 54px;
  height: 54px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  font-size: 22px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, #d97706, #b45309);
  flex: none;
}
.ts-id h3 {
  margin: 0 0 3px;
  font-size: 17px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.ts-facts {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-bottom: 12px;
}
.ts-facts .f {
  background: #faf6ee;
  border-radius: 9px;
  padding: 8px 6px;
  text-align: center;
}
.ts-facts .f b {
  display: block;
  font-size: 17px;
  color: var(--text);
  font-variant-numeric: tabular-nums;
}
.ts-facts .f b.bad {
  color: var(--red);
}
.ts-facts .f b.good {
  color: var(--green);
}
.ts-facts .f span {
  font-size: 10.5px;
  color: var(--muted);
  line-height: 1.3;
  display: block;
  margin-top: 2px;
}
.ts-warn {
  background: var(--red-soft);
  border: 1px solid #fca5a5;
  color: #9f1239;
  border-radius: 9px;
  padding: 8px 10px;
  font-size: 12.5px;
  margin: 0 0 10px;
}
.sec {
  font-size: 13.5px;
  margin: 18px 0 8px;
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.att-list,
.hw-list {
  border: 1px solid var(--line);
  border-radius: 10px;
  overflow: hidden;
}
.att-row {
  display: grid;
  grid-template-columns: 96px 62px 1fr 44px;
  gap: 6px;
  padding: 6px 10px;
  font-size: 12.5px;
  border-bottom: 1px solid #f4ece0;
  align-items: center;
}
.att-row:last-child {
  border-bottom: 0;
}
.att-row[data-st="absent"] {
  background: #fef2f2;
}
.att-row[data-st="late"] {
  background: #fffbeb;
}
.att-week {
  font-weight: 500;
}
.att-date,
.att-period {
  color: var(--muted);
  font-size: 11.5px;
}
.att-st {
  text-align: right;
  font-size: 11.5px;
}
.att-row[data-st="absent"] .att-st {
  color: var(--red);
  font-weight: 600;
}
.att-row[data-st="late"] .att-st {
  color: var(--brand);
}
.att-row[data-st="present"] .att-st {
  color: var(--green);
}
.hw-row {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 7px 10px;
  border-bottom: 1px solid #f4ece0;
  position: relative;
}
.hw-row:last-child {
  border-bottom: 0;
}
.hw-row b {
  font-size: 12.5px;
  font-weight: 500;
  padding-right: 44px;
}
.hw-st {
  position: absolute;
  right: 10px;
  top: 9px;
  font-size: 11.5px;
}
.hw-row[data-st="missing"] .hw-st {
  color: var(--red);
  font-weight: 600;
}
.hw-row[data-st="late"] .hw-st {
  color: var(--brand);
}
.hw-row[data-st="submitted"] .hw-st {
  color: var(--green);
}
.hw-row[data-st="missing"] {
  background: #fef7f7;
}
.more {
  width: 100%;
  border: 0;
  background: #faf6ee;
  color: var(--brand);
  font-size: 12px;
  padding: 7px;
  cursor: pointer;
}
.act {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 10px;
  background: #fffdf9;
}
.act-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  font-size: 12.5px;
}
.act .txt {
  margin: 0;
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-2);
  background: #faf6ee;
  border-radius: 8px;
  padding: 9px 10px;
}
.ts-foot {
  margin: 18px 0 8px;
}
.ts-foot .btn {
  width: 100%;
}
</style>
