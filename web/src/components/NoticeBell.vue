<script setup lang="ts">
import { computed, ref } from "vue";
import { ElMessage } from "element-plus/es/components/message/index";
import { ElMessageBox } from "element-plus/es/components/message-box/index";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useNoticeStore } from "@/stores/notices";
import type { AppealItem } from "@/types";

const auth = useAuthStore();
const notices = useNoticeStore();

const KIND_ICON: Record<string, string> = {
  absent: "🚫",
  homework: "📝",
  risk: "🔔",
  appeal_new: "🙋",
  appeal_reply: "📮",
  talk: "💬",
  attendance: "🚫",
  appeal: "🙋",
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
  if (notices.panelOpen) void loadAppeals();
}

function openNotice(id: string) {
  void notices.markRead([id]);
}

function markAll() {
  void notices.markRead(notices.unread.map((n) => n.id));
}

function checkTodo(t: { id: string; done: boolean }) {
  if (t.done) void notices.finishTodo(t.id);
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
  <div class="bell-wrap">
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

        <!-- 待办 -->
        <template v-else-if="notices.tab === 'todo'">
          <div v-if="!notices.todos.length" class="empty">暂无待办事项。</div>
          <label v-for="t in notices.todos" :key="t.id" class="item todo" :class="{ done: t.done }">
            <input :checked="t.done" type="checkbox" @change="checkTodo(t)" />
            <div class="item-main">
              <b>{{ t.title }}</b>
              <p>{{ t.detail }}</p>
              <span class="tiny muted">{{ t.ts }}</span>
            </div>
          </label>
        </template>

        <!-- 异议（导员/教务） -->
        <template v-else>
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
}
.item.todo input {
  margin-top: 3px;
  accent-color: var(--brand);
}
.item.todo.done .item-main b {
  text-decoration: line-through;
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
