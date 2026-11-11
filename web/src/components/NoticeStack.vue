<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { NoticeItem } from "@/types";

/**
 * 进端口时的消息栈（替代 Element Plus 的 ElNotification）。
 *
 * 为什么不用 ElNotification：它是命令式逐个挂到 body 上的，每条的位置由
 * JS 按 offsetHeight 算好写死 top。折叠展开会让卡片高度变化，写死的 top
 * 不会跟着重排，展开的那条立刻压到下面那条身上。这里改成一条 flex 竖排，
 * 谁展开谁把下面的推开，天然不会重叠。
 *
 * 折叠规则：默认只露标题一行，鼠标移上去展开发全文；卡片的宽度、字号、
 * 内边距都沿用原来通知的度量，展开后就是原来的样子，只是占屏高度小很多。
 * 展开/收起用 grid-template-rows 0fr→1fr 过渡——正文高度不定，
 * 用 max-height 猜一个值会让短消息"走一半就停"、长消息"被截断"。
 */
interface StackNotice {
  key: string;
  /** 橙色感叹号（旷课、新的异议）；其余是灰色 i */
  warn: boolean;
  n: NoticeItem;
}

const props = defineProps<{ items: StackNotice[] }>();
const emit = defineEmits<{ (e: "close", key: string): void }>();

/**
 * 位置：贴着顶部那几条通栏（顶栏 + 初始密码/模型未接的黄条）的下沿再留一点，
 * 不压住铃铛、姓名胶囊、"修改密码/退出"，也不盖住黄条右边的"立即修改"。
 * 各端高度不一样（门户首屏顶栏是压扁版，内页是常规版，黄条还不一定存在），
 * 所以不写死像素，量实际底边取最大；换页/缩放/条子出现消失时重新量。
 */
const stackEl = ref<HTMLElement | null>(null);
const CHROME = [".topbar", ".llm-banner", ".pwd-banner"];
let barObserver: ResizeObserver | null = null;
let mo: MutationObserver | null = null;
let queued = 0;

/** 每帧最多量一次：body 上的 DOM 变动很密（聊天流式输出），不能每次都量 */
function schedule() {
  if (queued) return;
  queued = requestAnimationFrame(() => {
    queued = 0;
    place();
    watchBar();
  });
}

function place() {
  const el = stackEl.value;
  if (!el) return;
  let bottom = 54; // 兜底：连顶栏都还没渲染时，落在原来按钮行之下
  for (const sel of CHROME) {
    const node = document.querySelector<HTMLElement>(sel);
    if (node) bottom = Math.max(bottom, node.getBoundingClientRect().bottom);
  }
  el.style.setProperty("--ntf-top", `${Math.max(12, Math.round(bottom + 12))}px`);
}

function watchBar() {
  barObserver?.disconnect();
  barObserver = null;
  if (typeof ResizeObserver === "undefined") return;
  barObserver = new ResizeObserver(() => place());
  for (const sel of CHROME) {
    const node = document.querySelector<HTMLElement>(sel);
    if (node) barObserver.observe(node);
  }
}

onMounted(() => {
  place();
  watchBar();
  window.addEventListener("resize", place);
  window.addEventListener("orientationchange", place);
  // 黄条是 v-if 的，改密码/重连模型后才出现，出现时要重新量一次
  if (typeof MutationObserver !== "undefined") {
    mo = new MutationObserver(() => schedule());
    mo.observe(document.body, { childList: true, subtree: true });
  }
});

onBeforeUnmount(() => {
  if (queued) cancelAnimationFrame(queued);
  queued = 0;
  barObserver?.disconnect();
  barObserver = null;
  mo?.disconnect();
  mo = null;
  window.removeEventListener("resize", place);
  window.removeEventListener("orientationchange", place);
});

// 消息进栈/出栈后布局可能再变，补量一次保证不重叠
watch(
  () => props.items.length,
  () =>
    requestAnimationFrame(() => {
      place();
      watchBar();
    }),
  { flush: "post" },
);
</script>

<template>
  <Teleport to="body">
    <div ref="stackEl" class="ntf-stack" :class="{ empty: !items.length }">
      <div
        v-for="(row, i) in items"
        :key="row.key"
        class="ntf"
        :style="{ animationDelay: `${i * 70}ms` }"
      >
        <div class="ntf-top">
          <span class="ntf-ic" :class="{ warn: row.warn }" aria-hidden="true">
            <svg v-if="row.warn" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="11" fill="#e6a23c" />
              <rect x="10.85" y="5.5" width="2.3" height="9.2" rx="1.15" fill="#fff" />
              <circle cx="12" cy="17.9" r="1.6" fill="#fff" />
            </svg>
            <svg v-else viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="11" fill="#b9bdc7" />
              <rect x="10.85" y="10.2" width="2.3" height="8.2" rx="1.15" fill="#fff" />
              <circle cx="12" cy="6.7" r="1.6" fill="#fff" />
            </svg>
          </span>
          <b class="ntf-ttl">{{ row.n.title }}</b>
          <button class="ntf-x" title="不再提示这一条" @click.stop="emit('close', row.key)">
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path
                d="M3.6 3.6l8.8 8.8M12.4 3.6l-8.8 8.8"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
            </svg>
          </button>
        </div>

        <div class="ntf-fold">
          <div class="ntf-in">
            <p class="ntf-txt">{{ row.n.text }}</p>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.ntf-stack {
  position: fixed;
  /* 顶栏下沿 + 12px，由 place() 实测写进 --ntf-top；兜底 64px */
  top: var(--ntf-top, 64px);
  right: 16px;
  z-index: 2400;
  width: 330px;
  max-width: calc(100vw - 32px);
  display: flex;
  flex-direction: column;
  gap: 10px;
  /* 只有卡片本身吃鼠标，空隙让给页面 */
  pointer-events: none;
}
.ntf-stack.empty {
  display: none;
}

.ntf {
  pointer-events: auto;
  padding: 12px 14px 12px 16px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--card);
  box-shadow:
    0 1px 2px rgba(35, 38, 31, 0.06),
    0 8px 22px -12px rgba(35, 38, 31, 0.28);
  animation: ntf-in 0.34s cubic-bezier(0.22, 0.61, 0.36, 1) both;
  transition:
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}
.ntf:hover {
  border-color: var(--line-strong);
  box-shadow:
    0 2px 4px rgba(35, 38, 31, 0.08),
    0 16px 32px -16px rgba(35, 38, 31, 0.34);
}
@keyframes ntf-in {
  from {
    opacity: 0;
    transform: translateX(22px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

.ntf-top {
  display: flex;
  align-items: center;
  gap: 10px;
}
.ntf-ic {
  flex: 0 0 auto;
  width: 20px;
  height: 20px;
  display: block;
}
.ntf-ic svg {
  display: block;
  width: 20px;
  height: 20px;
}
/* 标题：折叠态只这一行。15px 而不是 16px——330px 宽里「考勤提醒：本学期已旷课 19 次」
   这种 16 字标题会顶到叉号上；小 1px 换回右侧一点呼吸，肉眼看不出差别 */
.ntf-ttl {
  flex: 1;
  min-width: 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--text);
  letter-spacing: 0.1px;
}
.ntf-x {
  flex: 0 0 auto;
  width: 22px;
  height: 22px;
  margin-left: 4px;
  padding: 0;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #a8aca1;
  cursor: pointer;
  transition:
    background 0.16s ease,
    color 0.16s ease;
}
.ntf-x svg {
  width: 13px;
  height: 13px;
}
.ntf-x:hover {
  background: var(--paper-2);
  color: var(--text);
}

/* 折叠区：0fr → 1fr，高度按内容自然撑开，不猜 max-height */
.ntf-fold {
  display: grid;
  grid-template-rows: 0fr;
  opacity: 0;
  transition:
    grid-template-rows 0.3s cubic-bezier(0.22, 0.61, 0.36, 1),
    opacity 0.22s ease;
}
.ntf:hover .ntf-fold,
.ntf:focus-within .ntf-fold {
  grid-template-rows: 1fr;
  opacity: 1;
}
.ntf-in {
  overflow: hidden;
}
/* 展开的正文：字距、字号、行高都照着原来的通知来 */
.ntf-txt {
  margin: 8px 0 0;
  font-size: 14px;
  line-height: 1.62;
  color: var(--text-2);
  word-break: break-word;
}

/* 触屏没有 hover，退化成点一下展开/收起 */
@media (hover: none) {
  .ntf-fold {
    transition: none;
  }
}
</style>
