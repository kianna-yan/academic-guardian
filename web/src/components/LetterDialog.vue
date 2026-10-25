<script setup lang="ts">
import { computed, ref } from "vue";
import CitationList from "@/components/CitationList.vue";
import MarkdownBody from "@/components/MarkdownBody.vue";
import type { Citation } from "@/types";

const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    title?: string;
    subject?: string;
    body?: string;
    citations?: Citation[];
  }>(),
  { title: "", subject: "", body: "", citations: () => [] },
);

const emit = defineEmits<{ (e: "update:modelValue", v: boolean): void }>();
const copied = ref(false);

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit("update:modelValue", v),
});

async function copy() {
  try {
    await navigator.clipboard.writeText(props.body || "");
    copied.value = true;
    setTimeout(() => (copied.value = false), 1800);
  } catch {
    copied.value = false;
  }
}
</script>

<template>
  <el-dialog v-model="visible" :title="title || '文书预览'" width="min(720px, 92vw)" align-center>
    <p v-if="subject" class="dlg-sub">{{ subject }}</p>
    <MarkdownBody :text="body" />
    <CitationList :citations="citations" />
    <template #footer>
      <button class="btn" @click="copy">{{ copied ? "已复制" : "复制正文" }}</button>
      <button class="btn primary" @click="visible = false">完成</button>
    </template>
  </el-dialog>
</template>

<style scoped>
.dlg-sub {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--muted);
}
</style>
