<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import CitationList from "@/components/CitationList.vue";
import MarkdownBody from "@/components/MarkdownBody.vue";
import TraceSteps from "@/components/TraceSteps.vue";
import { useChatStore } from "@/stores/chat";
import type { Role } from "@/types";

const props = defineProps<{ role: Role; sid: string | null }>();
defineEmits<{ (e: "close"): void }>();

const chat = useChatStore();
const draft = ref("");
const body = ref<HTMLElement | null>(null);

const HEAD: Record<Role, [string, string]> = {
  student: ["学业助手", "基于你的学情数据回答，不猜不编"],
  counselor: ["辅导员助手", "可以问名单、原因、谈话建议"],
  admin: ["教务助手", "全校统计与规则问题"],
  parent: ["家校助手", "用通俗的话说明情况"],
};

const PLACEHOLDER: Record<Role, string> = {
  student: "问点什么，比如：我的风险分为什么这么高？",
  counselor: "比如：本班谁的风险上升最快？",
  admin: "比如：全校风险分布如何？",
  parent: "比如：孩子这学期情况怎么样？",
};

const head = computed(() => HEAD[props.role] ?? HEAD.student);
const placeholder = computed(() => PLACEHOLDER[props.role] ?? PLACEHOLDER.student);

function scrollToBottom() {
  nextTick(() => {
    if (body.value) body.value.scrollTop = body.value.scrollHeight;
  });
}

// 流式输出时文本逐字增长，靠深度监听把视口钉在底部
watch(() => chat.messages, scrollToBottom, { deep: true });
watch(() => props.role, scrollToBottom);

// 面板被收起或页面切走时，把还在跑的流掐掉，否则请求会悬挂并往已卸载的视图里写数据
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
</script>

<template>
  <aside class="chat" :class="{ open: chat.open }">
    <header class="chat-head">
      <div>
        <strong>{{ head[0] }}</strong>
        <span>{{ head[1] }}</span>
      </div>
      <button class="chat-close" title="收起" @click="$emit('close')">×</button>
    </header>

    <div ref="body" class="chat-body">
      <div v-for="m in chat.messages" :key="m.id" class="msg" :class="{ user: m.from === 'user' }">
        <div class="bubble">
          <template v-if="m.from === 'user'">{{ m.text }}</template>
          <template v-else>
            <MarkdownBody v-if="m.text" :text="m.text" />
            <span v-if="m.pending && m.text" class="typing-caret"></span>
            <span v-else-if="m.pending" class="spinner"></span>
            <div v-if="m.error" class="chat-error">{{ m.error }}</div>
            <div v-if="m.intent && m.intent !== 'why'" class="chat-intent">
              意图识别：{{ m.intent }}
            </div>
          </template>
        </div>

        <template v-if="m.from === 'assistant'">
          <CitationList :citations="m.citations" :max-chars="90" />
          <TraceSteps :trace="m.trace" :pending="m.pending" :elapsed="m.elapsed" />
        </template>
      </div>
    </div>

    <div class="chat-suggest">
      <button v-for="s in chat.suggestions" :key="s" class="chip" @click="send(s)">{{ s }}</button>
    </div>

    <form class="chat-form" @submit.prevent="submit">
      <input v-model="draft" :placeholder="placeholder" :disabled="chat.streaming" autocomplete="off" />
      <button type="submit" :disabled="chat.streaming || !draft.trim()">
        {{ chat.streaming ? "…" : "发送" }}
      </button>
    </form>
  </aside>
</template>

<style scoped>
.chat-close {
  border: 0;
  background: transparent;
  font-size: 20px;
  line-height: 1;
  color: var(--muted);
  padding: 2px 6px;
  border-radius: 6px;
}
.chat-close:hover {
  background: #f3f4f6;
}
.chat-error {
  color: #b91c1c;
  font-size: 12px;
  margin-top: 4px;
}
.chat-intent {
  font-size: 10.5px;
  color: #94a3b8;
  margin-top: 6px;
}
</style>
