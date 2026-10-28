<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus/es/components/message/index";
import { api, downloadDoc } from "@/api/client";
import ActionList from "@/components/ActionList.vue";
import ChatHome from "@/components/ChatHome.vue";
import DashNav from "@/components/DashNav.vue";
import LetterDialog from "@/components/LetterDialog.vue";
import RiskRing from "@/components/RiskRing.vue";
import { useAppStore } from "@/stores/app";
import { useAuthStore } from "@/stores/auth";
import { useChatStore } from "@/stores/chat";
import type { Citation, StudentDetail } from "@/types";

const app = useAppStore();
const auth = useAuthStore();
const chat = useChatStore();
const detail = ref<StudentDetail | null>(null);
const loading = ref(true);
const error = ref("");
const dialog = reactive({
  open: false,
  title: "",
  subject: "",
  body: "",
  citations: [] as Citation[],
});

// 家长登录时输入的就是孩子学号，这里直接用登录身份里的 sid
const sid = computed(() => auth.profile?.sid || "");

const tone = computed(() => {
  const level = detail.value?.risk.level;
  if (level === "red") return "本学期学业状态需要重点关注，学校已启动帮扶。";
  if (level === "yellow") return "本学期部分指标出现下滑，建议近期与孩子沟通一次。";
  return "本学期整体状态正常，保持现有节奏即可。";
});

const ringColor = computed(
  () => ({ red: "#dc2626", yellow: "#d97706", green: "#047857" })[detail.value?.risk.level || "green"],
);

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

watch(() => auth.profile?.sid, (v) => v && load(), { immediate: true });

async function openLetter() {
  if (!sid.value) return;
  try {
    const l = await api.letter(sid.value, "parent");
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
  <!-- 对话是主入口：进来就是整页 AI 问答，孩子的学情报告按键前往 -->
  <ChatHome v-if="chat.homeMode === 'chat'" role="parent" :sid="sid || null" />

  <template v-else>
    <DashNav />

    <div class="view-actions">
      <span class="badge" style="background: #fff7ed; color: #b45309">家长视角</span>
      <button class="btn primary" @click="openLetter">生成家长信</button>
      <button v-if="sid" class="btn" @click="downloadDoc(`/api/export/letter/${sid}?type=parent`)">
        导出家长信 Word
      </button>
    </div>

  <div v-if="loading" class="card">
    <div class="skeleton" style="height: 148px"></div>
  </div>

  <div v-else-if="error" class="card">
    <b>加载失败</b>
    <p class="tiny muted">{{ error }}</p>
  </div>

  <div v-else-if="detail">
    <div class="card" :style="{ borderLeft: `3px solid ${ringColor}` }">
      <div class="parent-head">
        <div style="min-width: 0">
          <div class="risk-title">
            <span class="risk-name">{{ detail.student.name }}</span>
            <span class="level-pill" :class="detail.risk.level">{{ detail.risk.level_label }}</span>
          </div>
          <p class="tiny muted" style="margin: 0">
            {{ detail.student.class_name }} · {{ detail.student.major }} · 辅导员
            {{ detail.student.advisor }}
          </p>
          <p style="margin: 12px 0 0; font-size: 13.5px">{{ tone }}</p>
        </div>
        <RiskRing :score="detail.risk.score" :level="detail.risk.level" :size="132" />
      </div>

      <div class="risk-facts" style="margin-top: 16px">
        <div class="fact">
          <b>{{ detail.risk.raw.absent }} 次</b><span>本学期缺勤</span>
        </div>
        <div class="fact">
          <b>{{ detail.risk.raw.hw_submitted }}/{{ detail.risk.raw.hw_assigned }}</b><span>作业提交</span>
        </div>
        <div class="fact">
          <b>{{ detail.risk.raw.mid_avg }}</b><span>期中加权均分</span>
        </div>
        <div class="fact">
          <b>{{ detail.student.credits.earned }}</b><span>已修学分</span>
        </div>
      </div>
    </div>

    <div class="two-col mt">
      <div class="card">
        <div class="card-head">
          <h3>学校正在做什么</h3>
          <span class="hint">已启动的帮扶动作</span>
        </div>
        <ActionList :actions="detail.actions" :limit="3" :show-priority="false" />
      </div>

      <div class="card">
        <div class="card-head">
          <h3>家长可以配合的</h3>
          <span class="hint">比追问成绩更有效的三件事</span>
        </div>
        <div class="action-item">
          <div class="action-no">1</div>
          <div class="action-body">
            <b>先问状态，不问分数</b>
            <p>“最近睡得怎么样、课听得懂吗”比“为什么考这么差”更容易得到真实回答。</p>
          </div>
        </div>
        <div class="action-item">
          <div class="action-no">2</div>
          <div class="action-body">
            <b>确认是否有实际困难</b>
            <p>作息颠倒、经济压力、情绪问题都会表现为缺勤和作业拖延，这类问题需要学校介入。</p>
          </div>
        </div>
        <div class="action-item">
          <div class="action-no">3</div>
          <div class="action-body">
            <b>与辅导员保持固定联系</b>
            <p>约定每两周沟通一次，比出事才联系更有效。辅导员：{{ detail.student.advisor }}。</p>
          </div>
        </div>
        <p class="tiny muted parent-note">
          学校不会仅凭系统评分作出处分，任何预警都会经过人工核实，家长和学生均可提出申诉。
        </p>
      </div>
    </div>
  </div>

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
.parent-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  flex-wrap: wrap;
}
.parent-note {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--line);
}
</style>
