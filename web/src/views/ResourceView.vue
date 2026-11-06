<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  api,
  downloadTeacherResource,
  uploadTeacherResource,
} from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import type { TeacherResource } from "@/types";

/**
 * 教师资源页：历年真题 / 网课资源。
 *
 * - 教师端：上传、删除、看自己已上传的全部
 * - 学生端：浏览所有老师上传的资源，点击下载
 * 入口在侧栏「课堂」分组下（教师端）和「学习空间」分组下（学生端）。
 *
 * 资源按 kind 分两栏：exam = 历年期末真题，tutorial = 网课视频/讲义。
 */
const auth = useAuthStore();
const isTeacher = computed(() => auth.profile?.role === "teacher");
const teacherName = computed(() => auth.profile?.advisor || auth.profile?.name || "");

const loading = ref(false);
const items = ref<TeacherResource[]>([]);
const tab = ref<"exam" | "tutorial">("exam");

// 上传表单
const uploading = ref(false);
const uploadForm = ref<{
  file: File | null;
  course: string;
  class_name: string;
  note: string;
}>({ file: null, course: "", class_name: "", note: "" });

const filterByTab = computed(() => items.value.filter((i) => i.kind === tab.value));

async function load() {
  loading.value = true;
  try {
    const res = await api.teacherResources();
    items.value = res.items || [];
  } catch (e: any) {
    ElMessage.error(e?.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

function onFile(e: Event) {
  const target = e.target as HTMLInputElement;
  if (target.files && target.files.length) {
    uploadForm.value.file = target.files[0];
  }
}

async function submit() {
  const f = uploadForm.value;
  if (!f.file) {
    ElMessage.warning("请先选择文件");
    return;
  }
  uploading.value = true;
  try {
    const res = await uploadTeacherResource(f.file, {
      kind: tab.value,
      course: f.course,
      class_name: f.class_name,
      note: f.note,
    });
    const kb = res.kb || res.item?.kb;
    if (kb?.ok) {
      ElMessage.success(`已上传，并加入 AI 知识库（${kb.sections ?? 0} 段正文可被检索）`);
    } else if (kb?.note) {
      ElMessage.warning(`已上传，但没有进知识库：${kb.note}`);
    } else {
      ElMessage.success("已上传");
    }
    uploadForm.value = { file: null, course: "", class_name: "", note: "" };
    // 清掉 file input 的展示
    const inp = document.getElementById("res-file") as HTMLInputElement | null;
    if (inp) inp.value = "";
    await load();
  } catch (e: any) {
    ElMessage.error(e?.message || "上传失败");
  } finally {
    uploading.value = false;
  }
}

async function remove(it: TeacherResource) {
  try {
    await ElMessageBox.confirm(`确定删除《${it.filename}》？`, "删除资源", {
      type: "warning",
    });
  } catch {
    return;
  }
  try {
    await api.deleteTeacherResource(it.id);
    ElMessage.success("已删除");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.message || "删除失败");
  }
}

function fmtSize(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

onMounted(load);
</script>

<template>
  <div class="res-page">
    <div class="res-head">
      <div class="res-tabs">
        <button class="rt" :class="{ on: tab === 'exam' }" @click="tab = 'exam'">
          📄 历年期末真题
        </button>
        <button class="rt" :class="{ on: tab === 'tutorial' }" @click="tab = 'tutorial'">
          🎬 网课资源
        </button>
      </div>
      <span class="res-sub muted">
        {{ tab === "exam" ? "老师上传历年期末试卷与参考答案，学生可下载复习" : "老师上传网课视频/讲义，学生可在线学习" }}
      </span>
    </div>

    <!-- 教师上传表单 -->
    <section v-if="isTeacher" class="card upload-card">
      <div class="card-head">
        <h3>上传{{ tab === "exam" ? "真题" : "网课" }}</h3>
        <span class="hint">支持 PDF/Word/PPT/图片/视频/压缩包，单个文件 ≤ 50 MB</span>
      </div>
      <div class="up-form">
        <label class="up-file">
          <input id="res-file" type="file" @change="onFile" />
          <span class="up-file-btn">选择文件</span>
          <span class="up-file-name">{{ uploadForm.file?.name || "未选择" }}</span>
        </label>
        <input v-model="uploadForm.course" class="up-input" placeholder="所属课程（如：高等数学）" />
        <input v-model="uploadForm.class_name" class="up-input" placeholder="适用班级（如：计科2024-01，留空表示全部）" />
        <input v-model="uploadForm.note" class="up-input" placeholder="说明（如：2023 秋期末 A 卷）" />
        <button class="btn primary" :disabled="uploading || !uploadForm.file" @click="submit">
          {{ uploading ? "上传中…" : "上传" }}
        </button>
      </div>
    </section>

    <section class="card">
      <div class="card-head">
        <h3>{{ tab === "exam" ? "历年真题" : "网课资源" }}（{{ filterByTab.length }}）</h3>
        <button v-if="!loading" class="btn sm" @click="load">刷新</button>
      </div>

      <div v-if="loading" class="empty"><span class="spinner"></span> 加载中…</div>
      <div v-else-if="!filterByTab.length" class="empty">
        {{ isTeacher ? "还没有上传资源，从上方上传第一份" : "老师还没有上传资源，请稍后再来" }}
      </div>

      <ul v-else class="res-list">
        <li v-for="it in filterByTab" :key="it.id" class="res-row">
          <div class="res-main">
            <b>{{ it.filename }}</b>
            <span class="tiny muted">
              {{ fmtSize(it.size) }}
              <template v-if="it.course"> · {{ it.course }}</template>
              <template v-if="it.class_name"> · {{ it.class_name }}</template>
              <template v-if="isTeacher"> · 上传于 {{ it.created_at }}</template>
              <template v-else> · {{ it.teacher }}老师 · {{ it.created_at }}</template>
            </span>
            <span v-if="it.note" class="tiny res-note">{{ it.note }}</span>
            <span v-if="isTeacher && it.kb?.ok" class="kb-tag">
              已入 AI 知识库 · {{ it.kb.sections || 0 }} 段
            </span>
            <span
              v-else-if="isTeacher && it.kb && !it.kb.ok"
              class="kb-tag off"
              :title="it.kb.note"
            >
              未入库 · {{ it.kb.note }}
            </span>
          </div>
          <div class="res-side">
            <button class="btn sm" @click="downloadTeacherResource(it.id)">下载</button>
            <button v-if="isTeacher" class="btn sm danger" @click="remove(it)">删除</button>
          </div>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.res-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.res-head {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.res-tabs {
  display: flex;
  gap: 6px;
}
.rt {
  padding: 8px 16px;
  border: 1px solid var(--line);
  background: #fff;
  color: var(--text-2);
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.15s;
}
.rt:hover {
  border-color: var(--brand);
}
.rt.on {
  background: var(--brand);
  border-color: var(--brand);
  color: #fff;
  font-weight: 600;
}
.res-sub {
  font-size: 12px;
}

.upload-card {
  background: linear-gradient(180deg, #fdf8ef 0%, #fff 100%);
}
.up-form {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) 1fr 1fr 1fr auto;
  gap: 10px;
  align-items: center;
}
.up-file {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}
.up-file input {
  position: absolute;
  width: 0;
  height: 0;
  opacity: 0;
}
.up-file-btn {
  padding: 0 14px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--line-strong);
  border-radius: 7px;
  background: #fff;
  color: var(--text-2);
  font-size: 13px;
  flex: none;
}
.up-file-btn:hover {
  border-color: var(--brand);
  color: var(--brand);
}
.up-file-name {
  font-size: 12.5px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.up-input {
  height: 34px;
  border: 1px solid var(--line);
  border-radius: 7px;
  padding: 0 10px;
  font-size: 13px;
  color: var(--text);
  background: #fff;
  outline: none;
  min-width: 0;
}
.up-input:focus {
  border-color: var(--brand);
}
.btn.primary {
  height: 34px;
  padding: 0 22px;
}
.btn.sm {
  height: 30px;
  padding: 0 14px;
}
.btn.sm.danger {
  border: 1px solid #fecaca;
  color: #9c231c;
  background: #fff;
}
.btn.sm.danger:hover {
  background: #f9e8e5;
}

.res-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.res-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 11px 0;
  border-bottom: 1px solid #f0e7d8;
}
.res-row:last-child {
  border-bottom: 0;
}
.res-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.res-main b {
  font-size: 13.5px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.res-note {
  color: var(--brand);
}
.kb-tag {
  align-self: flex-start;
  margin-top: 2px;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 11px;
  line-height: 1.7;
  color: #0f6e56;
  background: #e1f5ee;
  border: 1px solid #9fe1cb;
}
.kb-tag.off {
  color: #854f0b;
  background: #faeeda;
  border-color: #fac775;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.res-side {
  display: flex;
  gap: 6px;
  flex: none;
}

@media (max-width: 1080px) {
  .up-form {
    grid-template-columns: 1fr;
  }
}
</style>
