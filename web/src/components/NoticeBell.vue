<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { ElMessage } from "element-plus/es/components/message/index";
import { ElMessageBox } from "element-plus/es/components/message-box/index";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useNoticeStore } from "@/stores/notices";
import type { AppealItem, TodoItem } from "@/types";

/**
 * 右上角铃铛：通知 / 待办 / 异议 三个 tab。
 *
 * 家校沟通原来也藏在这里的一个 tab 里，入口太隐蔽——现已提升为
 * 左侧棕色导航栏的一级入口（家长端、辅导员端各一个「家校沟通」
 * 菜单项，带未读红点），点进去是整页对话界面。这里不再重复放一份。
 */
const auth = useAuthStore();
const notices = useNoticeStore();
/** 面板 + 铃铛的整体容器：判定「点的是不是框外」以它为准 */
const wrapRef = ref<HTMLElement | null>(null);

const KIND_ICON: Record<string, string> = {
  absent: "🚫",
  homework: "📝",
  risk: "🔔",
  appeal_new: "🙋",
  appeal_reply: "📮",
  talk: "💬",
  attendance: "🚫",
  appeal: "🙋",
  message: "✉️",
};

const role = computed(() => auth.profile?.role || "");
const isStaff = computed(() => role.value === "counselor" || role.value === "admin");
const appeals = ref<AppealItem[]>([]);

async function loadAppeals() {
  if (!isStaff.value) return;
  try {
    appeals.value = (await api.appeals()).items || [];
  } catch {
    /* 忽略 */
  }
}
void loadAppeals();

const pendingAppeals = computed(() => appeals.value.filter((a) => a.status === "pending"));

function toggle() {
  notices.panelOpen = !notices.panelOpen;
  if (notices.panelOpen) {
    void loadAppeals();
  }
}

/**
 * 点面板外面任意位置就关掉。
 *
 * 用 pointerdown 而不是 click：在面板里拖选一段文字、松手落在框外时，
 * click 的目标会算到公共祖先上，会被误判成「点了外面」，选字选到一半面板就没了。
 * 铃铛本身也在 wrap 里，所以点它不会进这里，仍由 toggle 负责开关。
 */
const SELF_LAYERS = ".el-overlay, .el-message-box, .el-popper, .el-message, .el-notification";

function onDocPointerDown(e: PointerEvent) {
  if (!notices.panelOpen) return;
  const target = e.target as Element | null;
  if (!target) return;
  if (wrapRef.value?.contains(target)) return;
  // 二次确认弹窗、提示条都挂在 body 上，点它们不算「点框外」
  if (target.closest?.(SELF_LAYERS)) return;
  notices.panelOpen = false;
}

function onDocKeydown(e: KeyboardEvent) {
  if (e.key === "Escape" && notices.panelOpen) notices.panelOpen = false;
}

/** 只在面板打开时挂监听，关掉就摘，避免整页一直挂着两个 document 监听 */
function bindOutside(open: boolean) {
  if (open) {
    document.addEventListener("pointerdown", onDocPointerDown, true);
    document.addEventListener("keydown", onDocKeydown);
  } else {
    document.removeEventListener("pointerdown", onDocPointerDown, true);
    document.removeEventListener("keydown", onDocKeydown);
  }
}

watch(() => notices.panelOpen, bindOutside);
onBeforeUnmount(() => bindOutside(false));

function openNotice(id: string) {
  void notices.markRead([id]);
}

function markAll() {
  void notices.markRead(notices.unread.map((n) => n.id));
}

/**
 * 勾选待办：打勾只表示「这件事我做完了」，条目不删除，会留在列表下方。
 * 必须读 checkbox 自己的 checked，不能读 t.done——@change 触发时 t.done 还是旧值。
 * 取消勾选就退回未完成（勾错了不用重新生成一条）。
 */
function checkTodo(t: TodoItem, ev: Event) {
  const on = (ev.target as HTMLInputElement).checked;
  if (on) void notices.finishTodo(t.id);
  else void notices.reopenTodo(t.id);
}

/** 右上角叉号：确认不要了才删除这条待办 */
async function dropTodo(id: string) {
  try {
    await notices.removeTodo(id);
    ElMessage.success("已删除该待办");
  } catch {
    ElMessage.error("删除失败，请稍后重试");
  }
}

async function resolve(id: string, action: "accept" | "reject") {
  const verdict = action === "accept" ? "同意更正" : "维持原记录";
  let reply = "";
  try {
    const { value } = await ElMessageBox.prompt(
      `处理意见（将回执给学生，默认「${verdict}」）`,
      action === "accept" ? "同意异议" : "维持原记录",
      {
        confirmButtonText: "确定",
        cancelButtonText: "取消",
        inputPlaceholder: "例如：已与任课老师核实，该次记录确有出入",
      },
    );
    reply = (value || "").trim();
  } catch {
    return;
  }
  try {
    await api.resolveAppeal(id, { action, reply });
    ElMessage.success(`已处理：${verdict}`);
    await loadAppeals();
    void notices.refresh(true);
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "处理失败");
  }
}

function appealLabel(a: AppealItem) {
  return a.kind === "homework" ? "作业缺交" : "旷课";
}
function statusLabel(s: string) {
  return s === "pending" ? "待处理" : s === "accepted" ? "已同意" : "已驳回";
}
</script>

<template>
  <div ref="wrapRef" class="bell-wrap">
    <button class="bell" :class="{ active: notices.panelOpen }" title="消息中心" @click="toggle">
      <span class="bell-icon">🔔</span>
      <span v-if="notices.unreadCount" class="badge">
        {{ notices.unreadCount > 99 ? "99+" : notices.unreadCount }}
      </span>
    </button>

    <div v-if="notices.panelOpen" class="panel">
      <div class="panel-head">
        <div class="tabs">
          <button class="tab" :class="{ on: notices.tab === 'notice' }" @click="notices.tab = 'notice'">
            通知 <em v-if="notices.unreadCount">{{ notices.unreadCount }}</em>
          </button>
          <button class="tab" :class="{ on: notices.tab === 'todo' }" @click="notices.tab = 'todo'">
            待办 <em v-if="notices.todoCount">{{ notices.todoCount }}</em>
          </button>
          <button
            v-if="isStaff && pendingAppeals.length"
            class="tab"
            :class="{ on: notices.tab === 'appeals' }"
            @click="notices.tab = 'appeals'"
          >
            异议 <em>{{ pendingAppeals.length }}</em>
          </button>
        </div>
        <button v-if="notices.tab === 'notice' && notices.unreadCount" class="link tiny" @click="markAll">
          全部已读
        </button>
      </div>

      <div class="panel-body">
        <!-- 通知 -->
        <template v-if="notices.tab === 'notice'">
          <div v-if="!notices.unread.length" class="empty">没有未读消息，都处理完了。</div>
          <div v-for="n in notices.unread" :key="n.id" class="item" @click="openNotice(n.id)">
            <span class="ico">{{ KIND_ICON[n.kind] || "📌" }}</span>
            <div class="item-main">
              <b>{{ n.title }}</b>
              <p>{{ n.text }}</p>
              <span class="tiny muted">{{ n.ts }}</span>
            </div>
          </div>
        </template>

        <!-- 待办：勾选只打勾，点右侧叉号才删除 -->
        <template v-else-if="notices.tab === 'todo'">
          <div v-if="!notices.todoList.length" class="empty">待办都清完了，暂时没有要跟进的事。</div>
          <div v-for="t in notices.todoList" :key="t.id" class="item todo" :class="{ done: t.done }">
            <label class="todo-check" :title="t.done ? '取消勾选' : '标记为已完成'">
              <input :checked="t.done" type="checkbox" @change="checkTodo(t, $event)" />
            </label>
            <div class="item-main">
              <b>{{ t.title }}</b>
              <p>{{ t.detail }}</p>
              <span class="tiny muted">{{ t.ts }}</span>
            </div>
            <button class="todo-x" title="删除这条待办" @click.stop="dropTodo(t.id)">✕</button>
          </div>
          <div v-if="notices.doneTodoCount" class="todo-foot">
            已勾选 {{ notices.doneTodoCount }} 条 · 点右侧 ✕ 才会从列表删除
          </div>
        </template>

        <!-- 异议（导员/教务） -->
        <template v-else-if="notices.tab === 'appeals'">
          <div v-if="!appeals.length" class="empty">还没有学生提交异议。</div>
          <div v-for="a in appeals" :key="a.id" class="item appeal">
            <span class="ico">{{ a.status === "pending" ? "🙋" : a.status === "accepted" ? "✅" : "🚫" }}</span>
            <div class="item-main">
              <b>{{ a.name }}（{{ a.class_name }}）对{{ appealLabel(a) }}提出异议</b>
              <p>《{{ a.course }}》：{{ a.reason }}</p>
              <span class="tiny muted">{{ a.ts }} · {{ statusLabel(a.status) }}</span>
              <div v-if="a.status === 'pending'" class="appeal-actions">
                <button class="btn ok" @click="resolve(a.id, 'accept')">同意更正</button>
                <button class="btn no" @click="resolve(a.id, 'reject')">维持原记录</button>
              </div>
              <p v-else-if="a.reply" class="tiny reply">回复：{{ a.reply }}</p>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bell-wrap {
  position: relative;
}
.bell {
  position: relative;
  width: 34px;
  height: 34px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #fff;
  cursor: pointer;
  display: grid;
  place-items: center;
  font-size: 15px;
}
.bell.active,
.bell:hover {
  background: var(--brand-soft);
}
.badge {
  position: absolute;
  top: -5px;
  right: -6px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 999px;
  background: #dc2626;
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  display: grid;
  place-items: center;
  line-height: 1;
}
.panel {
  position: absolute;
  right: 0;
  top: 42px;
  width: 380px;
  max-width: calc(100vw - 32px);
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 12px;
  box-shadow: var(--shadow);
  z-index: 60;
  overflow: hidden;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px 0;
  border-bottom: 1px solid var(--line);
}
.tabs {
  display: flex;
  gap: 2px;
}
.tab {
  border: 0;
  background: transparent;
  padding: 8px 10px;
  font-size: 13px;
  color: var(--text-2);
  cursor: pointer;
  border-bottom: 2px solid transparent;
}
.tab.on {
  color: var(--brand);
  border-bottom-color: var(--brand);
  font-weight: 600;
}
.tab em {
  font-style: normal;
  margin-left: 2px;
  padding: 0 5px;
  border-radius: 999px;
  background: #dc2626;
  color: #fff;
  font-size: 10px;
}
.panel-body {
  max-height: 420px;
  overflow: auto;
  padding: 6px;
}
.item {
  display: flex;
  gap: 10px;
  padding: 10px;
  border-radius: 10px;
  cursor: pointer;
  align-items: flex-start;
}
.item:hover {
  background: var(--brand-soft);
}
.item .ico {
  font-size: 18px;
  line-height: 1.4;
}
.item-main {
  flex: 1;
  min-width: 0;
}
.item-main b {
  font-size: 13px;
  color: var(--text);
  display: block;
  line-height: 1.35;
}
.item-main p {
  margin: 3px 0;
  font-size: 12px;
  color: var(--text-2);
  line-height: 1.5;
  word-break: break-all;
}
.item.todo {
  cursor: default;
  position: relative;
}
.item.todo .todo-check {
  flex: 0 0 auto;
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  cursor: pointer;
}
.item.todo .todo-check:hover {
  background: #fff;
}
.item.todo input {
  width: 15px;
  height: 15px;
  margin: 0;
  accent-color: var(--brand);
  cursor: pointer;
}
/* 勾完的整条淡下去，但还留在原位下方，看得见「我做过什么」 */
.item.todo.done {
  opacity: 0.62;
}
.item.todo.done .item-main b {
  text-decoration: line-through;
  color: var(--muted);
}
/* 右上角叉号：点它才真删 */
.todo-x {
  flex: 0 0 auto;
  width: 24px;
  height: 24px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
  display: grid;
  place-items: center;
}
.todo-x:hover {
  background: #fee2e2;
  color: #dc2626;
}
.todo-foot {
  padding: 4px 12px 8px;
  text-align: right;
  font-size: 11.5px;
  color: var(--muted);
}
.item.appeal {
  cursor: default;
}
.appeal-actions {
  display: flex;
  gap: 8px;
  margin-top: 6px;
}
.btn {
  padding: 4px 12px;
  border-radius: 8px;
  border: 1px solid var(--line);
  background: #fff;
  font-size: 12px;
  cursor: pointer;
}
.btn.ok {
  background: var(--brand);
  border-color: var(--brand);
  color: #fff;
}
.btn.no {
  color: var(--text-2);
}
.reply {
  margin-top: 4px;
  color: var(--muted);
}
.empty {
  padding: 28px 0;
  text-align: center;
  font-size: 12.5px;
  color: var(--muted);
}
</style>
