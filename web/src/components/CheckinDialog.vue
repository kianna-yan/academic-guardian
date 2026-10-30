<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus/es/components/message/index";
import { api } from "@/api/client";
import type { CheckinRecord, Understand } from "@/types";

/**
 * 课后 10 秒记录。
 * 只问三件事：这节课听懂没有 / 从什么时候开始没听懂 / 之后打算怎么办。
 * 三个问题都是点选，最慢 10 秒能填完——填得动，轨迹才连得起来。
 */
const props = defineProps<{
  modelValue: boolean;
  sid: string;
  lesson: {
    course: string;
    name: string;
    teacher?: string;
    room?: string;
    date: string;
    week: number;
    weekday_label: string;
    period: string;
  } | null;
  record?: CheckinRecord | null;
  points?: string[];
  plans?: Record<string, string>;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", v: boolean): void;
  (e: "saved", row: CheckinRecord): void;
}>();

const open = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit("update:modelValue", v),
});

const STATE_OPTIONS: { key: Understand; label: string; sub: string }[] = [
  { key: "full", label: "听懂了", sub: "跟得上，没留问题" },
  { key: "fuzzy", label: "有点模糊", sub: "知道在讲什么，但接不上" },
  { key: "lost", label: "没听懂", sub: "从中间就掉队了" },
];

const BREAK_OPTIONS = [
  { key: "start", label: "从上课一开始就没跟上" },
  { key: "first15", label: "前 15 分钟还行，之后就懵了" },
  { key: "middle", label: "讲到中间（约第 45 分钟）开始" },
  { key: "secondhalf", label: "后半节课（约第 60 分钟）开始" },
  { key: "minute", label: "我记得具体是第几分钟" },
];

const PLAN_OPTIONS = [
  { key: "replay", label: "看回放 / 微课" },
  { key: "peer", label: "问同学要笔记" },
  { key: "teacher", label: "下次答疑问老师" },
  { key: "self", label: "自己重看书" },
  { key: "none", label: "先放一放" },
];

const form = reactive({
  understand: "fuzzy" as Understand,
  break_at: "middle",
  break_minute: 45,
  point: "",
  plan: "replay",
  note: "",
});
const saving = ref(false);

watch(
  () => [props.modelValue, props.lesson?.date, props.lesson?.period],
  ([v]) => {
    if (!v || !props.lesson) return;
    const r = props.record;
    form.understand = (r?.state as Understand) || "fuzzy";
    form.break_at = r?.minute_from ? minuteToKey(r.minute_from) : "middle";
    form.break_minute = r?.minute_from || 45;
    form.point = r?.point || "";
    form.plan = r?.plan || "replay";
    form.note = r?.note || "";
  },
  { immediate: true },
);

function minuteToKey(m: number) {
  if (m <= 0) return "start";
  if (m <= 15) return "first15";
  if (m <= 45) return "middle";
  if (m <= 60) return "secondhalf";
  return "minute";
}

const needBreak = computed(() => form.understand !== "full");

function pickPoint(p: string) {
  form.point = form.point === p ? "" : p;
}

/** 填的过程中就把这句话拼出来，学生能看到系统到底记了什么 */
const preview = computed(() => {
  const l = props.lesson;
  if (!l) return "";
  if (form.understand === "full") return `《${l.name}》第 ${l.week} 周 ${l.weekday_label} ${l.period}：这节课跟上了。`;
  const minute =
    form.break_at === "minute"
      ? form.break_minute
      : { start: 0, first15: 15, middle: 45, secondhalf: 60 }[form.break_at] ?? 0;
  const head = `《${l.name}》第 ${l.week} 周 ${l.weekday_label} ${l.period}：`;
  const state = form.understand === "lost" ? "没听懂" : "有点模糊";
  const from = minute <= 0 ? "从一开始" : `从第 ${minute} 分钟起`;
  const where = form.point ? `，卡在「${form.point}」` : "";
  return `${head}${state}，${from}${where}。`;
});

async function save() {
  const l = props.lesson;
  if (!l || !props.sid) return;
  saving.value = true;
  try {
    const res = await api.saveCheckin(props.sid, {
      course: l.course,
      date: l.date,
      period: l.period,
      understand: form.understand,
      break_at: needBreak.value ? form.break_at : "none",
      break_minute: needBreak.value && form.break_at === "minute" ? form.break_minute : null,
      point: form.point,
      plan: needBreak.value ? form.plan : "none",
      note: form.note,
    });
    ElMessage.success("已记录，学习轨迹里能看到了");
    emit("saved", res.record);
    open.value = false;
  } catch (e: any) {
    ElMessage.error(e?.message || "记录失败");
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <el-dialog v-model="open" :width="560" :close-on-click-modal="false" align-center class="checkin-dialog">
    <template #header>
      <div class="dlg-head">
        <b>课后记录 · {{ lesson?.name }}</b>
        <span v-if="lesson">
          第 {{ lesson.week }} 周 {{ lesson.weekday_label }} {{ lesson.period }}
          <template v-if="lesson.room"> · {{ lesson.room }}</template>
          <template v-if="lesson.teacher"> · {{ lesson.teacher }}</template>
        </span>
      </div>
    </template>

    <div class="q">
      <div class="q-label">这节课听懂了吗？</div>
      <div class="state-grid">
        <button
          v-for="o in STATE_OPTIONS"
          :key="o.key"
          class="state-btn"
          :class="[o.key, { on: form.understand === o.key }]"
          @click="form.understand = o.key"
        >
          <i aria-hidden="true"></i>
          <b>{{ o.label }}</b>
          <span>{{ o.sub }}</span>
        </button>
      </div>
    </div>

    <template v-if="needBreak">
      <div class="q">
        <div class="q-label">从什么时候开始没听懂的？</div>
        <div class="opt-row">
          <button
            v-for="o in BREAK_OPTIONS"
            :key="o.key"
            class="opt"
            :class="{ on: form.break_at === o.key }"
            @click="form.break_at = o.key"
          >
            {{ o.label }}
          </button>
        </div>
        <div v-if="form.break_at === 'minute'" class="minute-row">
          第
          <el-input-number v-model="form.break_minute" :min="1" :max="90" :step="5" size="small" controls-position="right" />
          分钟
          <span class="tiny muted">（两小节按 90 分钟算）</span>
        </div>
      </div>

      <div class="q">
        <div class="q-label">卡在哪一步？<span class="tiny muted">可点选，也可以自己写</span></div>
        <div class="tag-row">
          <button
            v-for="p in points || []"
            :key="p"
            class="tag"
            :class="{ on: form.point === p }"
            @click="pickPoint(p)"
          >
            {{ p }}
          </button>
        </div>
        <el-input v-model="form.point" maxlength="40" placeholder="例如：递归的边界条件没想明白" />
      </div>

      <div class="q">
        <div class="q-label">接下来打算怎么办？</div>
        <div class="opt-row">
          <button
            v-for="o in PLAN_OPTIONS"
            :key="o.key"
            class="opt"
            :class="{ on: form.plan === o.key }"
            @click="form.plan = o.key"
          >
            {{ o.label }}
          </button>
        </div>
      </div>
    </template>

    <div class="q">
      <div class="q-label">补一句（可选）</div>
      <el-input v-model="form.note" type="textarea" :rows="2" maxlength="160" show-word-limit
        placeholder="例如：讲到第 3 章的递归调用就乱了，课件第 12 页没看懂" />
    </div>

    <div class="preview">
      <span class="pv-label">系统会记成</span>
      <b>{{ preview }}</b>
      <em>这条记录只用于你的学习轨迹，不参与风险评分——说"没听懂"不会扣分。</em>
    </div>

    <template #footer>
      <div class="dlg-foot">
        <button class="btn ghost" @click="open = false">取消</button>
        <button class="btn primary" :disabled="saving" @click="save">
          {{ saving ? "保存中…" : record ? "更新这条记录" : "记下这节课" }}
        </button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.dlg-head {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.dlg-head b {
  font-size: 15px;
  color: var(--text);
}
.dlg-head span {
  font-size: 11.5px;
  color: var(--muted);
}
.q {
  margin-bottom: 16px;
}
.q-label {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-2);
  margin-bottom: 8px;
}
.state-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.state-btn {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fff;
  text-align: left;
  transition: border-color 0.15s, background 0.15s, box-shadow 0.15s;
}
.state-btn i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #d9c9b3;
  margin-bottom: 4px;
}
.state-btn b {
  font-size: 13px;
  color: var(--text);
}
.state-btn span {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.45;
}
.state-btn:hover {
  border-color: var(--line-strong);
}
.state-btn.full.on {
  border-color: #047857;
  background: #ecfdf5;
  box-shadow: 0 0 0 2px rgba(4, 120, 87, 0.1);
}
.state-btn.full.on i {
  background: #047857;
}
.state-btn.fuzzy.on {
  border-color: #d97706;
  background: #fffbeb;
  box-shadow: 0 0 0 2px rgba(217, 119, 6, 0.12);
}
.state-btn.fuzzy.on i {
  background: #d97706;
}
.state-btn.lost.on {
  border-color: #dc2626;
  background: #fef2f2;
  box-shadow: 0 0 0 2px rgba(220, 38, 38, 0.1);
}
.state-btn.lost.on i {
  background: #dc2626;
}
.opt-row,
.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.opt {
  font-size: 12px;
  padding: 5px 11px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: #fff;
  color: var(--text-2);
}
.opt:hover {
  border-color: var(--line-strong);
}
.opt.on {
  border-color: var(--brand);
  background: var(--brand-soft);
  color: var(--brand);
  font-weight: 600;
}
.tag {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px dashed var(--line-strong);
  background: #fff;
  color: var(--text-2);
}
.tag.on {
  border-style: solid;
  border-color: var(--brand);
  background: var(--brand-soft);
  color: var(--brand);
}
.tag-row {
  margin-bottom: 8px;
}
.minute-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  font-size: 12.5px;
  color: var(--text-2);
}
.preview {
  border: 1px dashed var(--line-strong);
  border-radius: 10px;
  background: #fdfaf5;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.pv-label {
  font-size: 10.5px;
  letter-spacing: 0.5px;
  color: var(--muted);
}
.preview b {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text);
  line-height: 1.6;
}
.preview em {
  font-style: normal;
  font-size: 11px;
  color: var(--muted);
  line-height: 1.5;
}
.dlg-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
@media (max-width: 620px) {
  .state-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
