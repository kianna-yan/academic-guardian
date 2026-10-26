<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAppStore } from "@/stores/app";
import { useAuthStore, HOME_OF } from "@/stores/auth";
import type { Role } from "@/types";

const app = useAppStore();
const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

interface Entry {
  key: Role;
  name: string;
  sub: string;
  accountLabel: string;
  placeholder: string;
  icon: string;
}

const ENTRIES: Entry[] = [
  {
    key: "student",
    name: "学生端",
    sub: "查自己的预警等级与补救路径",
    accountLabel: "学号",
    placeholder: "请输入 8 位学号",
    icon: "学",
  },
  {
    key: "counselor",
    name: "辅导员端",
    sub: "风险名单、谈话要点与跟进记录",
    accountLabel: "工号",
    placeholder: "请输入辅导员工号",
    icon: "辅",
  },
  {
    key: "admin",
    name: "教务端",
    sub: "规则配置、账号开通与全校看板",
    accountLabel: "账号",
    placeholder: "请输入教务账号",
    icon: "教",
  },
  {
    key: "parent",
    name: "家长端",
    sub: "了解孩子在校情况与配合方式",
    accountLabel: "孩子学号",
    placeholder: "请输入孩子的学号",
    icon: "家",
  },
];

const active = ref<Role>("student");
const form = reactive({ account: "", password: "" });
const error = ref("");
const sending = ref(false);
const showPwd = ref(false);

const entry = computed(() => ENTRIES.find((e) => e.key === active.value)!);
const demoStudent = computed(() => app.meta?.demo?.student || "20240067");
const demoParent = computed(() => app.meta?.demo?.parent || demoStudent.value);

/** 切换入口时清空密码，避免把学生密码带进教务端 */
watch(active, () => {
  form.password = "";
  error.value = "";
});

onMounted(() => {
  // 从被拦截的地址过来时，提示一下而不是默默跳走
  const blocked = route.query.blocked;
  if (typeof blocked === "string" && blocked) {
    error.value = "当前账号没有该端的权限，请用对应账号登录";
  }
});

async function submit() {
  error.value = "";
  if (!form.account.trim()) {
    error.value = `请输入${entry.value.accountLabel}`;
    return;
  }
  if (!form.password.trim()) {
    error.value = "请输入密码";
    return;
  }
  sending.value = true;
  try {
    const res = await auth.login(active.value, form.account.trim(), form.password.trim());
    // 四个端入口固定，按身份直接进自己的端；不再回跳带 query 的地址
    await router.push(HOME_OF[res.profile.role]);
  } catch (e: any) {
    error.value = e?.message || "登录失败";
  } finally {
    sending.value = false;
  }
}

function fill(kind: "student" | "counselor" | "admin" | "parent") {
  if (kind === "student") {
    active.value = "student";
    form.account = demoStudent.value;
    form.password = "0000";
  } else if (kind === "parent") {
    active.value = "parent";
    form.account = demoParent.value;
    form.password = "3333";
  } else if (kind === "counselor") {
    active.value = "counselor";
    form.account = "2024014589";
    form.password = "1111";
  } else {
    active.value = "admin";
    form.account = "1234567899";
    form.password = "2222";
  }
  error.value = "";
}
</script>

<template>
  <div class="login-page">
    <div class="login-bg" aria-hidden="true"></div>

    <div class="login-shell">
      <!-- 左：品牌与说明 -->
      <section class="login-intro">
        <div class="brand">
          <div class="brand-mark">护</div>
          <div class="brand-text">
            <strong>学业护航</strong>
            <span>Academic Guardian</span>
          </div>
        </div>

        <h1>四个入口，各看各的</h1>
        <p class="lead">
          学生自查、辅导员跟进、教务定规则、家长知情。每个端用各自的账号登录，
          看到的范围和可执行的动作都不同，数据不出角色边界。
        </p>

        <ul class="points">
          <li><b>学生端</b> 用学号登录，只看自己的风险构成与补救建议</li>
          <li><b>辅导员端</b> 看本班名单排序、谈话要点与跟进记录</li>
          <li><b>教务端</b> 配置预警线、批量开通学生账号、导出全校名单</li>
          <li><b>家长端</b> 用孩子学号登录，只看孩子的状态与配合方式</li>
        </ul>

        <div class="login-meta">
          <span>{{ app.meta?.term || "2024-2025 学年" }}</span>
          <span v-if="app.meta?.week">第 {{ app.meta.week }} 教学周</span>
          <span>{{ app.meta?.student_count || 240 }} 名学生</span>
        </div>
      </section>

      <!-- 右：登录表单 -->
      <section class="login-card">
        <div class="tabs" role="tablist">
          <button
            v-for="e in ENTRIES"
            :key="e.key"
            class="tab"
            :class="{ active: active === e.key }"
            role="tab"
            :aria-selected="active === e.key"
            @click="active = e.key"
          >
            <span class="tab-icon">{{ e.icon }}</span>
            <span>{{ e.name }}</span>
          </button>
        </div>

        <h2>{{ entry.name }}</h2>
        <p class="sub">{{ entry.sub }}</p>

        <form @submit.prevent="submit">
          <label class="field">
            <span>{{ entry.accountLabel }}</span>
            <input
              v-model="form.account"
              :placeholder="entry.placeholder"
              autocomplete="username"
              inputmode="numeric"
            />
          </label>

          <label class="field">
            <span>密码</span>
            <div class="pwd">
              <input
                v-model="form.password"
                :type="showPwd ? 'text' : 'password'"
                placeholder="请输入密码"
                autocomplete="current-password"
              />
              <button type="button" class="eye" @click="showPwd = !showPwd">
                {{ showPwd ? "隐藏" : "显示" }}
              </button>
            </div>
          </label>

          <p v-if="error" class="err">{{ error }}</p>

          <button class="submit" type="submit" :disabled="sending">
            {{ sending ? "登录中…" : `登录${entry.name}` }}
          </button>
        </form>

        <div class="hint-box">
          <div class="hint-head">
            <b>初始密码</b>
            <span>首次登录后请及时修改，右上角可改</span>
          </div>
          <div class="hint-grid">
            <button class="hint-item" type="button" @click="fill('student')">
              <span>学生</span>
              <em>学号 / 0000</em>
            </button>
            <button class="hint-item" type="button" @click="fill('counselor')">
              <span>辅导员</span>
              <em>2024014589 / 1111</em>
            </button>
            <button class="hint-item" type="button" @click="fill('admin')">
              <span>教务</span>
              <em>1234567899 / 2222</em>
            </button>
            <button class="hint-item" type="button" @click="fill('parent')">
              <span>家长</span>
              <em>孩子学号 / 3333</em>
            </button>
          </div>
          <p class="hint-foot">
            演示学号 <b>{{ demoStudent }}</b>（点上面任意一项可自动填入，直接登录即可）
          </p>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px 20px;
  background: #f6efe4;
  overflow: hidden;
}
.login-bg {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(680px 320px at 12% 12%, #fdebd6 0%, transparent 60%),
    radial-gradient(620px 300px at 88% 88%, #fdf3e3 0%, transparent 62%);
}
.login-shell {
  position: relative;
  width: min(1080px, 100%);
  display: grid;
  grid-template-columns: 1.05fr 0.95fr;
  gap: 40px;
  align-items: center;
}

/* 左侧 */
.login-intro .brand {
  display: flex;
  align-items: center;
  gap: 12px;
}
.brand-mark {
  width: 40px;
  height: 40px;
  border-radius: 11px;
  background: var(--brand);
  color: #fff;
  display: grid;
  place-items: center;
  font-weight: 700;
  font-size: 18px;
}
.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}
.brand-text strong {
  font-size: 16px;
  color: var(--text);
}
.brand-text span {
  font-size: 11px;
  color: var(--muted);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.login-intro h1 {
  margin: 26px 0 12px;
  font-size: 30px;
  line-height: 1.25;
  color: var(--text);
}
.lead {
  margin: 0;
  color: var(--text-2);
  font-size: 14px;
  line-height: 1.75;
  max-width: 44em;
}
.points {
  margin: 22px 0 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 10px;
}
.points li {
  position: relative;
  padding-left: 18px;
  font-size: 13px;
  color: var(--text-2);
  line-height: 1.7;
}
.points li::before {
  content: "";
  position: absolute;
  left: 0;
  top: 9px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand);
  opacity: 0.55;
}
.points b {
  color: var(--text);
}
.login-meta {
  margin-top: 24px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.login-meta span {
  font-size: 12px;
  color: var(--muted);
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 4px 10px;
}

/* 右侧卡片 */
.login-card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 16px;
  box-shadow: 0 12px 32px rgba(59, 46, 36, 0.08);
  padding: 22px 24px 20px;
}
.tabs {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
  background: #faf6ee;
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 4px;
}
.tab {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 8px 4px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.tab-icon {
  width: 22px;
  height: 22px;
  border-radius: 7px;
  display: grid;
  place-items: center;
  font-size: 11px;
  background: #f0e6d6;
  color: var(--muted);
}
.tab.active {
  background: #fff;
  color: var(--brand);
  box-shadow: var(--shadow);
}
.tab.active .tab-icon {
  background: var(--brand-soft);
  color: var(--brand);
}

.login-card h2 {
  margin: 18px 0 4px;
  font-size: 19px;
  color: var(--text);
}
.login-card .sub {
  margin: 0 0 16px;
  font-size: 12.5px;
  color: var(--muted);
}

.field {
  display: block;
  margin-bottom: 12px;
}
.field > span {
  display: block;
  font-size: 12px;
  color: var(--text-2);
  margin-bottom: 6px;
}
.field input {
  width: 100%;
  height: 40px;
  border: 1px solid var(--line-strong);
  border-radius: 9px;
  background: #fff;
  color: var(--text);
  font-size: 14px;
  padding: 0 12px;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.field input:focus {
  border-color: var(--brand);
  box-shadow: 0 0 0 3px rgba(29, 78, 216, 0.12);
}
.pwd {
  position: relative;
}
.pwd input {
  padding-right: 58px;
}
.eye {
  position: absolute;
  right: 6px;
  top: 6px;
  height: 28px;
  padding: 0 8px;
  border: 0;
  border-radius: 7px;
  background: #f6efe4;
  color: var(--muted);
  font-size: 11.5px;
  cursor: pointer;
}
.err {
  margin: 2px 0 10px;
  font-size: 12.5px;
  color: var(--red);
  background: var(--red-soft);
  border: 1px solid #fecaca;
  border-radius: 8px;
  padding: 8px 10px;
}
.submit {
  width: 100%;
  height: 42px;
  margin-top: 4px;
  border: 0;
  border-radius: 10px;
  background: var(--brand);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: filter 0.15s;
}
.submit:hover {
  filter: brightness(1.06);
}
.submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.hint-box {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px dashed var(--line);
}
.hint-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}
.hint-head b {
  font-size: 12.5px;
  color: var(--text);
}
.hint-head span {
  font-size: 11.5px;
  color: var(--muted);
}
.hint-grid {
  margin-top: 10px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.hint-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: #fbf7ef;
  cursor: pointer;
  text-align: left;
}
.hint-item:hover {
  border-color: #f0d9b5;
  background: #fdf4e6;
}
.hint-item span {
  font-size: 11.5px;
  color: var(--muted);
}
.hint-item em {
  font-style: normal;
  font-size: 12.5px;
  color: var(--text);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.hint-foot {
  margin: 10px 0 0;
  font-size: 11.5px;
  color: var(--muted);
}

@media (max-width: 900px) {
  .login-shell {
    grid-template-columns: 1fr;
    gap: 22px;
  }
  .login-intro h1 {
    font-size: 24px;
    margin-top: 18px;
  }
  .points {
    display: none;
  }
}
@media (max-width: 480px) {
  .login-page {
    padding: 18px 14px;
  }
  .login-card {
    padding: 18px 16px 16px;
  }
  .hint-grid {
    grid-template-columns: 1fr;
  }
}
</style>
