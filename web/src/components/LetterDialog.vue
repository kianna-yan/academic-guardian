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
  <!--
    告知函/谈话要点常常是「在学生详情抽屉里点出来的」。
    抽屉和弹窗都是 Element Plus 的浮层，z-index 由内部计数器分配，抽屉先开就占到
    了更高的一层，于是文书被抽屉压住一半——正好压掉最该看的那几行字。
    这里给弹窗自己的遮罩挂一个 class，用样式把它顶到最上层（见文件末尾的全局样式）。
  -->
  <el-dialog
    v-model="visible"
    :title="title || '文书预览'"
    width="min(720px, 92vw)"
    align-center
    append-to-body
    modal-class="letter-modal"
    class="letter-dialog"
  >
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

<style>
/*
 * 文书预览必须压在所有东西上面：学生详情抽屉（在它下面开的）、右上角消息卡片
 * （2400）、AI 抽屉（2200）。遮罩上的 z-index 是 Element Plus 写成内联样式的，
 * 只有 !important 能盖过内联值，所以这里必须带上。
 */
.el-overlay.letter-modal {
  z-index: 3200 !important;
}
</style>
