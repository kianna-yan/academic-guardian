<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessageBox } from "element-plus/es/components/message-box/index";
import { useAppStore } from "@/stores/app";
import { useAuthStore, HOME_OF } from "@/stores/auth";
import type { Role } from "@/types";
import skyBg from "@/assets/login-sky.webp";

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

/**
 * 背景上的几颗星：只做点缀，刻意避开左栏文案与右侧登录卡。
 * 位置用百分比，换屏宽时按比例跟着走；尺寸/周期用 px、s。
 * 周期取 6s 和 3s（互为约数），相位用负延迟错开，才是此起彼伏地闪，
 * 而不是几颗一起亮、一起灭。
 */
const SKY_STARS = [
  { x: "10.5%", y: "3.4%", size: 18, dur: 6, delay: -1.6, peak: 0.92 }, // 左上主星
  { x: "31.4%", y: "8.4%", size: 14, dur: 6, delay: -3.4, peak: 0.8 },
  { x: "46.4%", y: "2.2%", size: 10, dur: 3, delay: -1.2, peak: 0.62 },
  { x: "67.9%", y: "3%", size: 15, dur: 6, delay: -4.8, peak: 0.75 }, // 登录卡正上方
  { x: "1.1%", y: "36%", size: 10, dur: 6, delay: -2.4, peak: 0.52 }, // 左页边
  // 再补三颗：高低错开、大小不一，让天顶看起来是随手撒的，而不是排过队。
  // 位置都避开了标题与正文的实字范围：左侧那颗压在天际线上方，
  // 中间那颗落在标题右侧的空白里，右边那颗贴着登录卡的左肩。
  { x: "6.4%", y: "4.4%", size: 12, dur: 6, delay: -0.9, peak: 0.62 }, // 左上角，比邻居低一头
  { x: "40.2%", y: "12.6%", size: 9, dur: 3, delay: -2.7, peak: 0.5 }, // 标题右侧的碎星
  { x: "48.4%", y: "6.1%", size: 14, dur: 6, delay: -4.2, peak: 0.68 }, // 登录卡左肩，位置更高
];

const bgStyle = computed(() => ({ "--sky": `url(${skyBg})` }));

function starStyle(s: (typeof SKY_STARS)[number]) {
  return {
    left: s.x,
    top: s.y,
    "--sz": `${s.size}px`,
    "--d": `${s.dur}s`,
    "--dl": `${s.delay}s`,
    "--op": `${s.peak}`,
  };
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
    <!-- 背景插画与星空跟内容一起铺在这块"舞台"上：滚轮动的时候整张画跟着走，
         而不是钉在视口里让文字从画上滑过去 -->
    <div class="login-stage">
      <div class="login-bg" aria-hidden="true" :style="bgStyle"></div>
      <div class="login-sky" aria-hidden="true">
        <i v-for="(s, i) in SKY_STARS" :key="i" class="st" :style="starStyle(s)"></i>
      </div>

      <div class="login-shell">
        <!-- 左：品牌与说明 -->
        <section class="login-intro">
          <div class="brand-row">
            <div class="brand">
              <div class="brand-mark">护</div>
              <div class="brand-text">
                <strong>学业护航</strong>
                <span>Academic Guardian</span>
              </div>
            </div>

            <!-- 学年/周次/人数挪到品牌这一行：原来压在左栏底部，正好盖在小女孩脸上 -->
            <div class="login-meta">
              <span>{{ app.meta?.term || "2024-2025 学年" }}</span>
              <span v-if="app.meta?.week">第 {{ app.meta.week }} 教学周</span>
              <span>{{ app.meta?.student_count || 240 }} 名学生</span>
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
  </div>
</template>

<style scoped>
.login-page {
  position: relative;
  /* 固定一屏高、内部自己滚：窗口矮的时候（小笔记本、125% 缩放）整页能拖到底 */
  height: 100vh;
  height: 100dvh;
  background: #f6efe4;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior-y: contain;
}
/* 舞台 = 滚动的全部内容：至少一屏高，内容更高时跟着一起长，
   插画铺在它上面，所以滚轮一动，画和字是同一张纸，一起走 */
.login-stage {
  position: relative;
  min-height: 100%;
  display: flex;
  /* 顶部对齐而不是垂直居中：左栏文案整体上移，才能收在小女孩头顶之上；
     居中时内容会被往下压 80px，正好压到她的头发上 */
  align-items: flex-start;
  justify-content: center;
  padding: clamp(28px, 5vh, 52px) 20px 24px;
}
/* 背景：星空草坪插画（小女孩躺在左下角），左上方压一层极淡的米色给文案留白。
   贴住舞台而不是视口：整页滚动时插画跟着一起卷，画面才是一整张，
   同时永远按底部对齐——窗口再矮，小女孩也稳稳坐在草地尽头，不会骑到文字上 */
.login-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  background:
    radial-gradient(
      760px 420px at 26% 20%,
      rgba(251, 246, 236, 0.92) 0%,
      rgba(251, 246, 236, 0.72) 46%,
      rgba(251, 246, 236, 0) 78%
    ),
    var(--sky) no-repeat center bottom;
  background-size: auto, cover;
}
/* 星空层：几颗实心四角星，只做点缀，不接鼠标事件；同样长在画上，跟着一起滚 */
.login-sky {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  --star: url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Cpath fill='black' stroke='black' stroke-width='8' stroke-linejoin='round' d='M50 2C54 30 70 46 98 50 70 54 54 70 50 98 46 70 30 54 2 50 30 46 46 30 50 2Z'/%3E%3C/svg%3E");
}
.st {
  position: absolute;
  width: var(--sz);
  height: var(--sz);
  margin: calc(var(--sz) / -2) 0 0 calc(var(--sz) / -2);
  background-color: #c88a6d;
  -webkit-mask-image: var(--star);
  mask-image: var(--star);
  -webkit-mask-size: 100% 100%;
  mask-size: 100% 100%;
  -webkit-mask-repeat: no-repeat;
  mask-repeat: no-repeat;
  animation: star-twinkle var(--d) ease-in-out infinite;
  animation-delay: var(--dl);
  opacity: var(--op);
}
@keyframes star-twinkle {
  0%,
  100% {
    opacity: calc(var(--op) * 0.26);
    transform: scale(0.92);
  }
  50% {
    opacity: var(--op);
    transform: scale(1);
  }
}
@media (prefers-reduced-motion: reduce) {
  .st {
    animation: none;
    opacity: calc(var(--op) * 0.55);
  }
}
.login-shell {
  position: relative;
  z-index: 2;
  width: min(1080px, 100%);
  display: grid;
  grid-template-columns: 1.05fr 0.95fr;
  gap: 40px;
  /* 左栏与登录卡顶对齐：卡片本身就比左栏高，居中会把文案整体往下压 100px */
  align-items: start;
}

/* 左侧 */
/* 品牌与学年信息同一行：信息靠右，左边留给 logo，谁都不占小女孩的位置 */
.brand-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
}
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
  margin: 20px 0 10px;
  font-size: 30px;
  line-height: 1.25;
  color: var(--text);
}
.lead {
  margin: 0;
  color: var(--text-2);
  font-size: 13.5px;
  line-height: 1.72;
  max-width: 44em;
}
.points {
  margin: 16px 0 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
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
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.login-meta span {
  font-size: 11.5px;
  color: var(--muted);
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 3px 9px;
  white-space: nowrap;
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
  /* 小屏是单列长页，插画按 cover 铺开会把草地和人物拉得很大，压住正文；
     这里退回纯色渐变，星星也一并收掉 */
  .login-bg {
    background:
      radial-gradient(680px 320px at 12% 12%, #fdebd6 0%, transparent 60%),
      radial-gradient(620px 300px at 88% 88%, #fdf3e3 0%, transparent 62%);
  }
  .login-sky {
    display: none;
  }
}
@media (max-width: 480px) {
  .login-stage {
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
