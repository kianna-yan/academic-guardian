<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import { useAppStore } from "@/stores/app";

const app = useAppStore();
const route = useRoute();

const roles = computed(() => app.meta?.roles ?? []);
const term = computed(() => app.meta?.term ?? "—");
const week = computed(() => app.meta?.week ?? 0);
const updated = computed(() => app.meta?.updated_at ?? "");
const llm = computed(() => app.meta?.llm);
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

    <nav class="role-nav">
      <router-link
        v-for="r in roles"
        :key="r.key"
        :to="{ name: r.key, query: route.query }"
        class="role-btn"
        :class="{ active: route.name === r.key }"
      >
        <span>{{ r.name }}</span>
        <em>{{ r.desc }}</em>
      </router-link>
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
      <span v-if="updated">数据更新于 {{ updated }}</span>
    </div>
  </aside>
</template>
