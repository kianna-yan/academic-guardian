<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessageBox } from "element-plus/es/components/message-box/index";
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
    sub: "规则配置、账号开通与名单导出",
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
  {
    key: "teacher",
    name: "教师端",
    sub: "任课视角的课堂学情与风险研判",
    accountLabel: "工号",
    placeholder: "请输入任课教师工号",
    icon: "师",
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
const demoTeacher = computed(() => app.meta?.demo?.teacher || "2024014501");

/**
 * 端口示例表：五个端一张表列全，跟登录接口里的 DEFAULT_PASSWORD 一一对应
 * （0000 学生 / 1111 辅导员 / 2222 教务 / 3333 家长 / 4444 教师）。
 * 叫「示例」而不是「初始密码」——这张表是给人看着登录用的，不是账号的真实初始密码说明。
 * 家长端账号直接用孩子的真实学号，写「孩子学号」四个字等于让人自己猜。
 */
const HINTS = computed<{ key: Role; icon: string; name: string; account: string; password: string }[]>(() => [
  { key: "student", icon: "学", name: "学生端", account: demoStudent.value, password: "0000" },
  { key: "counselor", icon: "辅", name: "辅导员端", account: "2024014589", password: "1111" },
  { key: "admin", icon: "教", name: "教务端", account: "1234567899", password: "2222" },
  { key: "parent", icon: "家", name: "家长端", account: demoParent.value, password: "3333" },
  { key: "teacher", icon: "师", name: "教师端", account: demoTeacher.value, password: "4444" },
]);

/** 忘记密码：演示环境没有短信/邮箱通道，给出真实可走的两条路 */
function forgot() {
  void ElMessageBox.alert(
    `演示环境不发短信也不发邮件，找回只能走人工：\n\n` +
      `· 学生 / 家长：联系辅导员（工号 2024014589）或教务老师重置\n` +
      `· 辅导员 / 教师：联系教务处（账号 1234567899）重置\n\n` +
      `重置后回到初始密码，登录进来在右上角「修改密码」改掉即可。\n` +
      `只是想先看看系统：点下方「端口示例」任意一行，账号和密码会自动填好。`,
    "忘记密码怎么办",
    { confirmButtonText: "知道了", customStyle: { whiteSpace: "pre-line", lineHeight: "1.7" } },
  );
}

/**
 * 切换入口：清掉上一端的密码，避免把学生密码带进教务端。
 * 必须写成显式函数而不是 watch(active)——下拉表里的「点一行自动填入」也是先改 active 再填值，
 * 用 watch 的话清空动作会排在填值之后，把刚填好的密码又抹掉（演示时表现为「请输入密码」）。
 */
function switchRole(key: Role) {
  if (key === active.value) return;
  active.value = key;
  form.password = "";
  error.value = "";
}

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

function fill(kind: "student" | "counselor" | "admin" | "parent" | "teacher") {
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
  } else if (kind === "teacher") {
    active.value = "teacher";
    form.account = demoTeacher.value;
    form.password = "4444";
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

        <h1>五个入口，各看各的</h1>
        <p class="lead">
          学生自查、辅导员跟进、教务定规则、家长知情、任课教师盯课堂。每个端用各自的账号登录，
          看到的范围和可执行的动作都不同，数据不出角色边界。
        </p>

        <ul class="points">
          <li><b>学生端</b> 用学号登录，只看自己的风险构成与补救建议</li>
          <li><b>辅导员端</b> 看本班名单排序、谈话要点与跟进记录</li>
          <li><b>教务端</b> 配置预警线、批量开通学生账号、导出全校名单</li>
          <li><b>家长端</b> 用孩子学号登录，只看孩子的状态与配合方式</li>
          <li><b>教师端</b> 用工号登录，看自己课上学生的考勤、作业与风险</li>
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
            @click="switchRole(e.key)"
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

          <div class="field">
            <div class="field-head">
              <span>密码</span>
              <button type="button" class="forgot" @click="forgot">忘记密码？</button>
            </div>
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
          </div>

          <p v-if="error" class="err">{{ error }}</p>

          <button class="submit" type="submit" :disabled="sending">
            {{ sending ? "登录中…" : `登录${entry.name}` }}
          </button>
        </form>

        <div class="hint-box">
          <div class="hint-head">
            <b>端口示例</b>
            <span>首次登录后请及时修改，右上角可改</span>
          </div>
          <div class="hint-cols" aria-hidden="true">
            <span></span>
            <span>端口</span>
            <span>账号</span>
            <span class="ta-r">密码</span>
          </div>
          <ul class="hint-list">
            <li v-for="h in HINTS" :key="h.key">
              <button
                class="hint-row"
                :class="{ on: active === h.key }"
                type="button"
                :title="`点击填入${h.name}的示例账号与密码`"
                @click="fill(h.key)"
              >
                <span class="hr-ico">{{ h.icon }}</span>
                <span class="hr-name">{{ h.name }}</span>
                <span class="hr-acc">{{ h.account }}</span>
                <span class="hr-pwd">{{ h.password }}</span>
              </button>
            </li>
          </ul>
          <p class="hint-foot">
            点任意一行自动填入示例账号与密码，直接登录即可 · 演示学号 <b>{{ demoStudent }}</b>
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
  /* 五个端口一行排齐：写死 4 列会让教师端掉到第二行，看着像多余的第 5 项 */
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 4px;
  background: #f8f5ee;
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 4px;
}
.tab {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 7px 2px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: var(--muted);
  font-size: 11.5px;
  white-space: nowrap;
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
/* 密码行：左边标题，右边「忘记密码？」
   做成标题行内的小按钮，不额外占一行，也不挤占输入框高度 */
.field-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.field-head > span {
  font-size: 12px;
  color: var(--text-2);
}
.forgot {
  border: 0;
  background: transparent;
  padding: 0;
  font-size: 11.5px;
  color: var(--brand);
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.forgot:hover {
  color: #92400e;
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
.hint-cols {
  margin-top: 10px;
  padding: 0 9px 4px;
  display: grid;
  grid-template-columns: 16px 58px minmax(0, 1fr) 58px;
  gap: 8px;
  align-items: center;
  font-size: 10.5px;
  letter-spacing: 0.02em;
  color: var(--muted);
}
.hint-cols .ta-r {
  text-align: right;
}
.hint-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 5px;
}
.hint-row {
  width: 100%;
  display: grid;
  grid-template-columns: 16px 58px minmax(0, 1fr) 58px;
  gap: 8px;
  align-items: center;
  padding: 6px 9px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fbf7ef;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.14s, background 0.14s;
}
.hint-row:hover {
  border-color: #f0d9b5;
  background: #fdf4e6;
}
/* 当前选中的端口高亮，和上面的 tab 呼应 */
.hint-row.on {
  border-color: var(--brand);
  background: #e3ece7;
}
.hr-ico {
  width: 16px;
  height: 16px;
  border-radius: 5px;
  display: grid;
  place-items: center;
  font-size: 9.5px;
  background: #f0e6d6;
  color: var(--muted);
}
.hint-row.on .hr-ico {
  background: var(--brand-soft);
  color: var(--brand);
}
.hr-name {
  font-size: 12.5px;
  color: var(--text);
  white-space: nowrap;
}
.hr-acc {
  font-size: 12px;
  color: var(--text-2);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.hr-pwd {
  justify-self: end;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--brand);
  font-variant-numeric: tabular-nums;
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
  .tab {
    font-size: 11px;
    padding: 6px 0;
  }
  .hint-cols,
  .hint-row {
    grid-template-columns: 14px 50px minmax(0, 1fr) 44px;
    gap: 6px;
  }
}
</style>
