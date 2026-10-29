<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import AgentBriefing from "@/components/AgentBriefing.vue";
import CitationList from "@/components/CitationList.vue";
import MarkdownBody from "@/components/MarkdownBody.vue";
import TraceSteps from "@/components/TraceSteps.vue";
import { useChatStore } from "@/stores/chat";
import type { Role } from "@/types";

const props = defineProps<{ role: Role; sid: string | null }>();

const chat = useChatStore();
const draft = ref("");
const stream = ref<HTMLElement | null>(null);

/** 每个端的整页对话：标题、副标题、以及「去看板」按键文案 */
const HOME: Record<Role, { title: string; sub: string; dash: string }> = {
  student: {
    title: "学业助手",
    sub: "基于你的学情数据回答，不猜不编",
    dash: "我的学情档案",
  },
  counselor: {
    title: "辅导员助手",
    sub: "名单、原因、谈话建议，问我就行",
    dash: "预警名单 · 台账",
  },
  admin: {
    title: "教务助手",
    sub: "全校统计与规则问题",
    dash: "规则 · 全校看板",
  },
  parent: {
    title: "家校助手",
    sub: "用通俗的话说明孩子的情况",
    dash: "孩子的学情报告",
  },
  teacher: {
    title: "教学助手",
    sub: "你课上学生的考勤、作业与风险",
    dash: "课堂学情看板",
  },
};

const PLACEHOLDER: Record<Role, string> = {
  student: "问点什么，比如：我的风险分为什么这么高？",
  counselor: "比如：本班谁的风险上升最快？",
  admin: "比如：全校风险分布如何？",
  parent: "比如：孩子这学期情况怎么样？",
  teacher: "比如：我课上的学生？谁的风险最高？",
};

const home = computed(() => HOME[props.role] ?? HOME.student);
const placeholder = computed(() => PLACEHOLDER[props.role] ?? PLACEHOLDER.student);

function goDash() {
  chat.homeMode = "dash";
}

function scrollToBottom() {
  nextTick(() => {
    if (stream.value) stream.value.scrollTop = stream.value.scrollHeight;
  });
}

// 流式输出时文本逐字增长，靠深度监听把视口钉在底部
watch(() => chat.messages, scrollToBottom, { deep: true });
watch(() => props.role, scrollToBottom);

// 页面切走时把还在跑的流掐掉，否则请求会悬挂并往已卸载的视图里写数据
onBeforeUnmount(() => chat.abort());

function send(text: string) {
  const content = (text ?? "").trim();
  if (!content) return;
  draft.value = "";
  chat.send(props.role, props.sid, content);
  scrollToBottom();
}

function submit() {
  send(draft.value);
}

// 意图是一个内部枚举值，直接贴 "unknown" 给用户看没意义。
// 这里翻成人话：用户想知道的是「系统怎么理解我这句话的、去哪找的答案」。
const INTENT_LABEL: Record<string, string> = {
  risk: "查风险分",
  roster: "查名单",
  policy: "查校规条款",
  attendance: "查考勤",
  homework: "查作业",
  overview: "查全校统计",
  advice: "生成干预建议",
  contact: "查任课教师",
  letter: "生成家长信",
  report: "生成日报",
  unknown: "关键词没命中，交给模型判断",
  llm_route: "模型直接作答",
  llm_tool: "模型自己决定取哪些数据",
};

function intentLabel(v: string): string {
  return INTENT_LABEL[v] ?? v;
}
</script>

<template>
  <section class="chat-home">
    <header class="chat-home-head">
      <span class="ch-avatar" aria-hidden="true">AI</span>
      <div class="ch-title">
        <strong>{{ home.title }}</strong>
        <span>{{ home.sub }}</span>
      </div>
      <button class="ch-go-dash" @click="goDash">
        📊 {{ home.dash }}
      </button>
    </header>

    <div ref="stream" class="chat-stream">
      <div class="chat-col">
        <!-- AI 先开口：进页面的主动简报，追问点击即发 -->
        <AgentBriefing :role="role" />

        <div v-for="m in chat.messages" :key="m.id" class="msg" :class="{ user: m.from === 'user' }">
          <div class="bubble">
            <template v-if="m.from === 'user'">{{ m.text }}</template>
            <template v-else>
              <!-- 思考链：智能体在说谁、走哪条路，边想边显示 -->
              <div v-if="m.thoughts.length" class="thoughts" :class="{ done: !m.pending }">
                <div v-for="(t, i) in m.thoughts" :key="i" class="thought-line">
                  <span class="thought-ico">{{ m.pending && i === m.thoughts.length - 1 ? "…" : "✓" }}</span>
                  {{ t }}
                </div>
              </div>
              <MarkdownBody v-if="m.text" :text="m.text" />
              <span v-if="m.pending && m.text" class="typing-caret"></span>
              <span v-else-if="m.pending && !m.thoughts.length" class="spinner"></span>
              <div v-if="m.error" class="chat-error">{{ m.error }}</div>
              <div v-if="m.intent && m.intent !== 'why'" class="chat-intent">
                意图识别：{{ intentLabel(m.intent) }}
              </div>
            </template>
          </div>

          <template v-if="m.from === 'assistant'">
            <CitationList :citations="m.citations" :max-chars="90" />
            <TraceSteps :trace="m.trace" :pending="m.pending" :elapsed="m.elapsed" />
          </template>
        </div>
      </div>
    </div>

    <div class="chat-home-foot">
      <div class="chat-col">
        <div v-if="chat.suggestions.length" class="ch-suggest">
          <button v-for="s in chat.suggestions" :key="s" class="chip" @click="send(s)">{{ s }}</button>
        </div>
        <form class="ch-draft" @submit.prevent="submit">
          <input
            v-model="draft"
            :placeholder="placeholder"
            :disabled="chat.streaming"
            autocomplete="off"
            data-test="chat-input"
          />
          <button type="submit" :disabled="chat.streaming || !draft.trim()" data-test="chat-send">
            {{ chat.streaming ? "…" : "发送" }}
          </button>
        </form>
      </div>
    </div>
  </section>
</template>

<style scoped>
.chat-error {
  color: #b91c1c;
  font-size: 12px;
  margin-top: 4px;
}
.chat-intent {
  font-size: 10.5px;
  color: #b09b85;
  margin-top: 6px;
}
.ch-suggest {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
/* 思考链：进行中小字灰色，结束后收成一行高度不抢主体 */
.thoughts {
  margin: 0 0 8px;
  padding: 6px 9px;
  border-left: 2px solid #f0d9b5;
  background: #fbf7ef;
  border-radius: 0 6px 6px 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.thoughts.done {
  opacity: 0.72;
}
.thought-line {
  font-size: 11.5px;
  line-height: 1.55;
  color: #a58c72;
}
.thought-ico {
  color: #b45309;
  margin-right: 4px;
  font-size: 10px;
}
</style>
