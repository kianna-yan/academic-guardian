<script setup lang="ts">
import { computed } from "vue";
import MarkdownIt from "markdown-it";

const props = defineProps<{ text: string }>();

const md = new MarkdownIt({ html: false, breaks: true, linkify: true });
const html = computed(() => md.render(props.text || ""));
</script>

<template>
  <div class="md" v-html="html"></div>
</template>
