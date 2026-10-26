<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { api } from "@/api/client";
import { useChatStore } from "@/stores/chat";
import { useAuthStore } from "@/stores/auth";
import type { AgentBriefing, Role } from "@/types";

const props = defineProps<{ role: string }>();
const chat = useChatStore();
const auth = useAuthStore();

const data = ref<AgentBriefing | null>(null);
const failed = ref(false);
/** 打字机进度：greeting 显示到多少字 / 第几条 point */
const greetLen = ref(0);
const shownPoints = ref(0);

const sid = computed(() => auth.profile?.sid ?? null);

let timers: number[] = [];
function clearTimers() {
  timers.forEach((t) => window.clearTimeout(t));
  timers = [];
}

/** 打字机：一句话一句话往外蹦，像智能体在开口说话 */
function play(b: AgentBriefing) {
  clearTimers();
  greetLen.value = 0;
  shownPoints.value = 0;
  const greet = b.greeting;
  // 每帧 2 个字，60ms 一帧，语速接近真人
  for (let i = 1; i <= greet.length; i += 2) {
    timers.push(window.setTimeout(() => (greetLen.value = Math.min(i, greet.length)), (i / 2) * 60));
  }
  const greetMs = (greet.length / 2) * 60 + 150;
  b.points.forEach((_, idx) => {
    timers.push(window.setTimeout(() => (shownPoints.value = idx + 1), greetMs + idx * 320));
  });
}

async function load() {
  failed.value = false;
  try {
    const b = await api.briefing();
    data.value = b;
    play(b);
  } catch {
    failed.value = true;
  }
}

onMounted(load);
watch(() => props.role, load);
onBeforeUnmount(clearTimers);

function ask(question: string) {
  chat.ask(props.role as Role, sid.value, question);
}
</script>

<template>
  <section v-if="data" class="briefing card" :class="`t-${role}`">
    <div class="b-head">
      <span class="b-avatar" aria-hidden="true">AI</span>
      <p class="b-greet">{{ data.greeting.slice(0, greetLen) }}<span v-if="greetLen < data.greeting.length" class="caret"></span></p>
      <button class="b-refresh" title="重新生成" @click="load">↻</button>
    </div>

    <transition-group name="pt" tag="ul" class="b-points">
      <li
        v-for="(p, i) in data.points.slice(0, shownPoints)"
        :key="i"
        class="b-point"
        :class="`tone-${p.tone}`"
      >
        <span class="b-label">{{ p.label }}</span>
        <span class="b-text">{{ p.text }}</span>
      </li>
    </transition-group>

    <div v-if="shownPoints >= data.points.length" class="b-asks">
      <span class="b-ask-hint">接着问我：</span>
      <button v-for="q in data.asks" :key="q" class="chip" @click="ask(q)">{{ q }}</button>
    </div>
  </section>

  <section v-else-if="failed" class="briefing card failed">
    <button class="link" @click="load">简报加载失败，点此重试</button>
  </section>
</template>

<style scoped>
.briefing {
  position: relative;
  padding: 14px 16px 12px;
  margin-bottom: 14px;
  border: 1px solid #ecdfca;
  overflow: hidden;
}
.briefing::before {
  content: "";
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: linear-gradient(180deg, #d97706, #f2b566);
}
.b-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.b-avatar {
  flex: none;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: linear-gradient(135deg, #c2410c, #e89243);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  display: grid;
  place-items: center;
  letter-spacing: 0.5px;
}
.b-greet {
  flex: 1;
  margin: 0;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-1, #3b2e24);
  min-height: 20px;
}
.caret {
  display: inline-block;
  width: 2px;
  height: 14px;
  background: #d97706;
  margin-left: 2px;
  vertical-align: -2px;
  animation: blink 0.9s steps(2) infinite;
}
@keyframes blink {
  50% { opacity: 0; }
}
.b-refresh {
  border: 0;
  background: transparent;
  color: var(--muted, #b09b85);
  cursor: pointer;
  font-size: 15px;
  padding: 2px 6px;
  border-radius: 6px;
}
.b-refresh:hover {
  background: #f7f0e5;
  color: #7a6450;
}
.b-points {
  list-style: none;
  margin: 10px 0 0;
  padding: 0 0 0 40px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.b-point {
  display: flex;
  gap: 8px;
  align-items: baseline;
  font-size: 12.5px;
  line-height: 1.55;
}
.b-label {
  flex: none;
  font-size: 11px;
  font-weight: 600;
  color: #c2410c;
  background: #fdf1de;
  padding: 1px 7px;
  border-radius: 99px;
  white-space: nowrap;
}
.b-text {
  color: var(--text-2, #7a6450);
}
.b-point.tone-red .b-label,
.b-point.tone-down .b-label {
  color: #b91c1c;
  background: #fef2f2;
}
.b-point.tone-warn .b-label {
  color: #b45309;
  background: #fffbeb;
}
.b-point.tone-up .b-label {
  color: #047857;
  background: #ecfdf5;
}
.b-asks {
  margin: 12px 0 0 40px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.b-ask-hint {
  font-size: 11.5px;
  color: var(--muted, #b09b85);
}
.pt-enter-active {
  transition: all 0.35s ease;
}
.pt-enter-from {
  opacity: 0;
  transform: translateY(4px);
}
.failed {
  text-align: center;
  font-size: 12.5px;
}

@media (max-width: 560px) {
  .b-points,
  .b-asks {
    padding-left: 0;
    margin-left: 0;
  }
}
</style>
