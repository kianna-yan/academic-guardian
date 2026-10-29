<script setup lang="ts">
import { computed } from "vue";
import { useAppStore } from "@/stores/app";
import { useAuthStore } from "@/stores/auth";

const app = useAppStore();
const auth = useAuthStore();

const term = computed(() => app.meta?.term ?? "—");
const week = computed(() => app.meta?.week ?? 0);
const updated = computed(() => app.meta?.updated_at ?? "");
const llm = computed(() => app.meta?.llm);
const roleMeta = computed(() => app.meta?.roles.find((r) => r.key === auth.profile?.role));
const roleLabel = computed(
  () =>
    ({ student: "学生端", counselor: "辅导员端", admin: "教务端", parent: "家长端" } as Record<string, string>)[
      auth.profile?.role || ""
    ] || "",
);
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

    <!-- 一个账号只属于一个端，所以这里不再做端切换，只显示当前身份 -->
    <div class="current-role">
      <div class="current-role-head">
        <span>{{ roleLabel }}</span>
        <em v-if="auth.mustChange">初始密码</em>
      </div>
      <b>{{ auth.profile?.name }}</b>
      <small>{{ auth.profile?.account }}<template v-if="auth.profile?.class_name"> · {{ auth.profile?.class_name }}</template></small>
      <p v-if="roleMeta" class="current-role-desc">{{ roleMeta.desc }}</p>
    </div>

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
        <li>教务成绩库</li>
        <li>课堂考勤</li>
        <li>作业平台</li>
        <li>学习行为日志</li>
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
  margin: 2px 2px 16px;
  padding: 12px;
  border: 1px solid rgba(214, 187, 152, 0.28);
  border-radius: 10px;
  background: rgba(214, 187, 152, 0.10);
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
  margin-top: 6px;
  font-size: 14px;
  color: #eadfcd;
}
.current-role small {
  display: block;
  margin-top: 2px;
  font-size: 11.5px;
  color: #b09b85;
}
.current-role-desc {
  margin: 8px 0 0;
  font-size: 11.5px;
  line-height: 1.6;
  color: #b09b85;
}
</style>
