<script setup lang="ts">
import { computed } from "vue";
import MarkdownIt from "markdown-it";

const props = defineProps<{ text: string }>();

const md = new MarkdownIt({ html: false, breaks: true, linkify: true });
// 导出链接（/api/export/ 开头的相对路径）自动补登录 token：
// <a> 直接触发下载不会带 Authorization 头，改走 ag_token query（后端 _bearer 已支持）；
// 新标签打开，不打断当前对话。
const defaultLink =
  md.renderer.rules.link_open ||
  ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options));
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const tok = tokens[idx];
  const href = String(tok.attrGet("href") || "");
  if (href.startsWith("/api/export/") || href.startsWith("/api/export")) {
    const token = localStorage.getItem("ag.token") || "";
    const joiner = href.includes("?") ? "&" : "?";
    tok.attrSet("href", href + joiner + "ag_token=" + encodeURIComponent(token));
    tok.attrSet("target", "_blank");
    tok.attrSet("rel", "noopener");
  }
  return defaultLink(tokens, idx, options, env, self);
};
const html = computed(() => md.render(props.text || ""));
</script>

<template>
  <div class="md" v-html="html"></div>
</template>

<style scoped>
.md :deep(a) {
  color: #b45309;
  text-decoration: underline;
  text-underline-offset: 3px;
}
</style>
