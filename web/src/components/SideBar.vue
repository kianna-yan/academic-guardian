<script setup lang="ts">
import { computed, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import { MODULES, ROLE_LABEL } from "@/config/modules";
import { useAppStore } from "@/stores/app";
import { useAuthStore } from "@/stores/auth";
import { useChatStore } from "@/stores/chat";
import type { NavItem } from "@/config/modules";

/**
 * 侧栏：身份 → 模块分区 → 学期与数据源 → 状态。
 * 模块按"什么时候用"分区（学习空间 / 学业档案 / AI 顾问），
 * 而不是把所有功能平铺成一行菜单——学生进来先看到的是"每节课都在用的三件事"。
 */
const app = useAppStore();
const auth = useAuthStore();
const chat = useChatStore();
const route = useRoute();
const router = useRouter();

const term = computed(() => app.meta?.term ?? "—");
const week = computed(() => app.meta?.week ?? 0);
const updated = computed(() => app.meta?.updated_at ?? "");
const llm = computed(() => app.meta?.llm);
const role = computed(() => auth.profile?.role ?? "student");
const roleLabel = computed(() => ROLE_LABEL[role.value] || "");
const groups = computed(() => MODULES[role.value] || []);
const inChat = computed(() => chat.homeMode === "chat" && route.path === "/student");

function isActive(item: NavItem) {
  if (item.chat) return inChat.value;
  if (inChat.value) return false;
  const [path, hash] = item.to.split("#");
  if (route.path !== path) return false;
  return hash ? route.hash === `#${hash}` : !route.hash;
}

function goChat() {
  chat.homeMode = "chat";
  if (route.path !== "/student") router.push("/student");
}

/**
 * 同一路由只变锚点时路由不会重新渲染，得自己滚过去；
 * 另外从「对话」模式点进学情页要先把看板切回来，否则滚不到区块。
 */
async function onNav(item: NavItem, e: MouseEvent) {
  if (item.chat) {
    e.preventDefault();
    goChat();
    return;
  }
  const [path, hash] = item.to.split("#");
  if (path === "/student" && chat.homeMode === "chat") chat.homeMode = "dash";
  if (!hash || route.path !== path) return; // 跨页面交给 router，afterEach 里滚
  e.preventDefault();
  await nextTick();
  document.querySelector(`#${hash}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  history.replaceState(null, "", `${path}#${hash}`);
}
</script>

<template>
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-mark">护</div>
      <div class="brand-text">
        <strong>学业护航</strong>
        <span>Academic Guardian</span>
      </div>
    </div>

    <div class="current-role">
      <div class="current-role-head">
        <span>{{ roleLabel }}</span>
        <em v-if="auth.mustChange">初始密码</em>
      </div>
      <b>{{ auth.profile?.name }}</b>
      <small>{{ auth.profile?.account }}<template v-if="auth.profile?.class_name"> · {{ auth.profile?.class_name }}</template></small>
    </div>

    <nav class="mod-nav">
      <div v-for="g in groups" :key="g.key" class="mod-group">
        <div class="mod-label">
          <span>{{ g.label }}</span>
          <em v-if="g.caption">{{ g.caption }}</em>
        </div>
        <template v-for="it in g.items" :key="it.key">
          <button v-if="it.chat" class="mod-item" :class="{ active: isActive(it) }" :title="it.hint" @click="goChat">
            <i class="mi-dot ai"></i>
            <span class="mi-text">{{ it.label }}</span>
            <span class="mi-tag">AI</span>
          </button>
          <router-link v-else :to="it.to" class="mod-item" :class="{ active: isActive(it) }" :title="it.hint"
            @click="onNav(it, $event)">
            <i class="mi-dot"></i>
            <span class="mi-text">{{ it.label }}</span>
          </router-link>
        </template>
      </div>
    </nav>

    <div class="side-block">
      <div class="side-label">当前学期</div>
      <div class="side-term">
        <span>{{ term }}</span>
        <em v-if="week">第 {{ week }} 周</em>
      </div>
    </div>

    <div class="side-block">
      <div class="side-label">数据源</div>
      <ul class="side-list">
        <li>教务成绩库 · 课堂考勤</li>
        <li>作业平台 · 学习行为日志</li>
        <li>课表与课后自记</li>
      </ul>
    </div>

    <div class="side-foot">
      <span class="badge" :class="{ on: llm?.enabled }">
        {{ llm?.enabled ? `大模型已接入 · ${llm.model}` : "规则引擎模式 · 可接入大模型" }}
      </span>
      <span v-if="llm?.enabled && llm.route_model && llm.route_model !== llm.model" class="badge-sub">
        取数与整理：{{ llm.route_model }}
      </span>
      <span v-if="updated">数据更新于 {{ updated }}</span>
    </div>
  </aside>
</template>

<style scoped>
.current-role {
  margin: 2px 2px 0;
  padding: 10px 12px;
  border: 1px solid rgba(214, 187, 152, 0.28);
  border-radius: 10px;
  background: rgba(214, 187, 152, 0.1);
}
.current-role-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.current-role-head span {
  font-size: 11.5px;
  color: #b09b85;
  letter-spacing: 0.04em;
}
.current-role-head em {
  font-style: normal;
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 4px;
  background: #78350f;
  color: #fcd34d;
}
.current-role b {
  display: block;
  margin-top: 5px;
  font-size: 14px;
  color: #eadfcd;
}
.current-role small {
  display: block;
  margin-top: 2px;
  font-size: 11.5px;
  color: #b09b85;
}

/* ---------------- 模块分区导航 ---------------- */
.mod-nav {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}
.mod-group {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.mod-label {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  padding: 0 2px 4px;
  border-bottom: 1px solid rgba(214, 187, 152, 0.14);
  margin-bottom: 3px;
}
.mod-label span {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 10.5px;
  letter-spacing: 1px;
  color: #a58c72;
}
.mod-label em {
  flex: none;
  font-style: normal;
  font-size: 9.5px;
  color: #7d6852;
  letter-spacing: 0.2px;
  white-space: nowrap;
}
.mod-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 9px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: #ddcbb3;
  text-align: left;
  font-size: 12.5px;
  line-height: 1.5;
  transition: background 0.14s, color 0.14s;
}
.mod-item:hover {
  background: #452f22;
  color: #fff;
}
.mod-item.active {
  background: rgba(217, 119, 6, 0.9);
  color: #fff;
  font-weight: 600;
}
.mi-dot {
  flex: none;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #6b5442;
}
.mi-dot.ai {
  background: #7c8cf0;
}
.mod-item.active .mi-dot {
  background: #fff;
}
.mi-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mi-tag {
  flex: none;
  font-size: 9px;
  letter-spacing: 0.4px;
  padding: 0 4px;
  border-radius: 3px;
  border: 1px solid rgba(124, 140, 240, 0.5);
  color: #aab4ff;
  line-height: 13px;
}
.mod-item.active .mi-tag {
  border-color: rgba(255, 255, 255, 0.5);
  color: #fff;
}

/* 手机端：侧栏变成顶部条，模块导航横向滚动 */
@media (max-width: 760px) {
  .current-role,
  .side-block,
  .side-foot {
    display: none;
  }
  .mod-nav {
    flex-direction: row;
    gap: 6px;
    flex: 1 1 auto;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  .mod-nav::-webkit-scrollbar {
    display: none;
  }
  .mod-group {
    flex-direction: row;
    gap: 6px;
    flex: none;
  }
  .mod-label {
    display: none;
  }
  .mod-item {
    width: auto;
    padding: 4px 10px;
    border-radius: 999px;
    background: #452f22;
    font-size: 12px;
    white-space: nowrap;
  }
  .mod-item.active {
    background: var(--brand);
  }
  .mi-dot,
  .mi-tag {
    display: none;
  }
}
</style>
