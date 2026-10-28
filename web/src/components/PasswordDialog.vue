<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus/es/components/message/index";
import { useAuthStore } from "@/stores/auth";

const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{ (e: "update:modelValue", v: boolean): void }>();

const auth = useAuthStore();
const form = reactive({ old: "", next: "", confirm: "" });
const error = ref("");
const sending = ref(false);

const open = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit("update:modelValue", v),
});

const roleName = computed(() => {
  const map: Record<string, string> = { student: "学生", counselor: "辅导员", admin: "教务", parent: "家长" };
  return map[auth.profile?.role || ""] || "";
});

watch(open, (v) => {
  if (v) {
    form.old = "";
    form.next = "";
    form.confirm = "";
    error.value = "";
  }
});

async function submit() {
  error.value = "";
  if (!form.old.trim()) {
    error.value = "请输入原密码";
    return;
  }
  if (form.next.trim().length < 4) {
    error.value = "新密码至少 4 位";
    return;
  }
  if (form.next !== form.confirm) {
    error.value = "两次输入的新密码不一致";
    return;
  }
  sending.value = true;
  try {
    await auth.changePassword(form.old.trim(), form.next.trim());
    open.value = false;
    ElMessage.success("密码已修改，下次请用新密码登录");
  } catch (e: any) {
    error.value = e?.message || "修改失败";
  } finally {
    sending.value = false;
  }
}
</script>

<template>
  <el-dialog v-model="open" title="修改密码" width="420px" :close-on-click-modal="false">
    <div class="pwd-tip">
      当前登录：<b>{{ auth.profile?.name }}</b> · {{ roleName }}端（{{ auth.profile?.account }}）
      <span v-if="auth.mustChange">，仍在使用初始密码</span>
    </div>

    <label class="f">
      <span>原密码</span>
      <input v-model="form.old" type="password" placeholder="请输入原密码" autocomplete="current-password" />
    </label>
    <label class="f">
      <span>新密码</span>
      <input v-model="form.next" type="password" placeholder="至少 4 位" autocomplete="new-password" />
    </label>
    <label class="f">
      <span>确认新密码</span>
      <input v-model="form.confirm" type="password" placeholder="再输入一次" autocomplete="new-password" />
    </label>

    <p v-if="error" class="err">{{ error }}</p>
    <p class="note">密码只保存哈希，管理员也无法查看明文；忘记密码需由教务端重置。</p>

    <template #footer>
      <button class="btn" @click="open = false">取消</button>
      <button class="btn primary" :disabled="sending" @click="submit">
        {{ sending ? "提交中…" : "确认修改" }}
      </button>
    </template>
  </el-dialog>
</template>

<style scoped>
.pwd-tip {
  font-size: 12.5px;
  color: var(--muted);
  background: #fbf7ef;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 14px;
}
.pwd-tip b {
  color: var(--text);
}
.f {
  display: block;
  margin-bottom: 12px;
}
.f span {
  display: block;
  font-size: 12px;
  color: var(--text-2);
  margin-bottom: 6px;
}
.f input {
  width: 100%;
  height: 38px;
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  padding: 0 11px;
  font-size: 13.5px;
  color: var(--text);
  outline: none;
}
.f input:focus {
  border-color: var(--brand);
  box-shadow: 0 0 0 3px rgba(29, 78, 216, 0.1);
}
.err {
  margin: 4px 0 0;
  font-size: 12.5px;
  color: var(--red);
}
.note {
  margin: 10px 0 0;
  font-size: 11.5px;
  color: var(--muted);
  line-height: 1.6;
}
</style>
