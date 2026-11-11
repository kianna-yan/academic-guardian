import { createRouter, createWebHistory } from "vue-router";
import { SHARE_CODE } from "@/api/client";
import { useAuthStore, HOME_OF } from "@/stores/auth";
import type { Role } from "@/types";

/** 线上按 sharecode 放行，跳转时补回参数，避免被网关拦成 403 */
function withShare(path: string) {
  if (!SHARE_CODE) return path;
  if (path.includes("sharecode=")) return path;
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}sharecode=${encodeURIComponent(SHARE_CODE)}`;
}

type ViewLoader = () => Promise<any>;

/**
 * 看板版块 = 独立页面。
 *
 * 以前侧栏用「同页锚点」跳到看板的某一块（/student#grade），首屏因此要同时背着
 * 门户和整块看板。现在门户上的每个节点就是一条独立路由：点进去只渲染那一块，
 * 其他版块不挂载、不露出来。同一个视图组件复用，只是把 `meta.section` 传下去。
 */
interface SectionRoute {
  path: string;
  name: string;
  role: Role;
  section: string;
  title: string;
  sub: string;
  view: ViewLoader;
}

const SECTIONS: SectionRoute[] = [
  {
    path: "/student/overview",
    name: "student-overview",
    role: "student",
    section: "overview",
    title: "学情总览",
    sub: "风险分、六因素归因与这周的行动清单",
    view: () => import("@/views/StudentView.vue"),
  },
  {
    path: "/student/grade",
    name: "student-grade",
    role: "student",
    section: "grade",
    title: "成绩走势",
    sub: "五个学期一条线，外加本学期每门课的测评",
    view: () => import("@/views/StudentView.vue"),
  },
  {
    path: "/student/records",
    name: "student-records",
    role: "student",
    section: "records",
    title: "考勤与作业",
    sub: "逐日考勤、作业截止与任课老师联系方式",
    view: () => import("@/views/StudentView.vue"),
  },
  {
    path: "/student/appeal",
    name: "student-appeal",
    role: "student",
    section: "appeal",
    title: "复核与异议",
    sub: "记录不对可以提复核，十秒一条，人工核实",
    view: () => import("@/views/StudentView.vue"),
  },
  {
    path: "/counselor/roster",
    name: "counselor-roster",
    role: "counselor",
    section: "roster",
    title: "风险名单",
    sub: "按风险分排序，点一行看画像与这周先做什么",
    view: () => import("@/views/CounselorView.vue"),
  },
  {
    path: "/counselor/forest",
    name: "counselor-forest",
    role: "counselor",
    section: "forest",
    title: "智慧森林",
    sub: "每个学生一棵树：颜色一眼看出班级整体长势",
    view: () => import("@/views/CounselorView.vue"),
  },
  {
    path: "/admin/board",
    name: "admin-board",
    role: "admin",
    section: "board",
    title: "全校概览",
    sub: "预警分布、班级对比、风险因素排行",
    view: () => import("@/views/AdminView.vue"),
  },
  {
    path: "/admin/rules",
    name: "admin-rules",
    role: "admin",
    section: "rules",
    title: "规则配置",
    sub: "红黄线一拖，全校当场重算",
    view: () => import("@/views/AdminView.vue"),
  },
  {
    path: "/admin/accounts",
    name: "admin-accounts",
    role: "admin",
    section: "accounts",
    title: "学生账号",
    sub: "批量开通、重置初始密码",
    view: () => import("@/views/AdminView.vue"),
  },
  {
    path: "/admin/curriculum",
    name: "admin-curriculum",
    role: "admin",
    section: "curriculum",
    title: "课程与教师",
    sub: "导入任课教师与联系方式",
    view: () => import("@/views/AdminView.vue"),
  },
  {
    path: "/teacher/classroom",
    name: "teacher-classroom",
    role: "teacher",
    section: "classroom",
    title: "课堂学情",
    sub: "分数分布、出勤、作业与待办，只覆盖我教的课",
    view: () => import("@/views/TeacherView.vue"),
  },
  {
    path: "/parent/overview",
    name: "parent-overview",
    role: "parent",
    section: "overview",
    title: "状态解读",
    sub: "学校已做什么、家里可以怎么配合",
    view: () => import("@/views/ParentView.vue"),
  },
];

/**
 * 旧地址里的锚点仍然有人收藏着（/student#grade 之类）。
 * 门户改版后版块是独立页面，这里把老链接原地改写成对应的新路由，不让书签失效。
 */
const HASH_ALIAS: Record<string, string> = {
  "/student#overview": "/student/overview",
  "/student#risk": "/student/overview",
  "/student#grade": "/student/grade",
  "/student#records": "/student/records",
  "/student#appeal": "/student/appeal",
  "/counselor#roster": "/counselor/roster",
  "/counselor#forest": "/counselor/forest",
  "/admin#board": "/admin/board",
  "/admin#rules": "/admin/rules",
  "/admin#accounts": "/admin/accounts",
  "/admin#curriculum": "/admin/curriculum",
  "/teacher#classroom": "/teacher/classroom",
  "/parent#overview": "/parent/overview",
};

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/student" },
    {
      path: "/login",
      name: "login",
      component: () => import("@/views/LoginView.vue"),
      meta: { title: "登录", public: true },
    },
    // ---- 五个端的门户首屏：整页只有画布，看板一律收进节点里 ----
    {
      path: "/student",
      name: "student",
      component: () => import("@/views/StudentView.vue"),
      meta: { title: "学习空间", sub: "五个入口之外的东西，点开节点才出现", role: "student", home: true },
    },
    {
      path: "/student/schedule",
      name: "student-schedule",
      component: () => import("@/views/ScheduleView.vue"),
      meta: { title: "我的课表", sub: "这周上什么、在哪上、哪一节还没记", role: "student" },
    },
    {
      path: "/student/checkin",
      name: "student-checkin",
      component: () => import("@/views/CheckinView.vue"),
      meta: { title: "课后打卡", sub: "每节课后 10 秒：听懂没有、从哪儿开始没懂", role: "student" },
    },
    {
      path: "/student/track",
      name: "student-track",
      component: () => import("@/views/TrackView.vue"),
      meta: { title: "学习轨迹", sub: "每门课一条线：断在哪、后来接上没有", role: "student" },
    },
    {
      path: "/student/tree",
      name: "student-tree",
      component: () => import("@/views/TreeView.vue"),
      meta: { title: "我的智慧树", sub: "浇水＝到课（树干），施肥＝作业（果实）", role: "student" },
    },
    {
      path: "/student/simulate",
      name: "student-simulate",
      component: () => import("@/views/SimulatorView.vue"),
      meta: { title: "成绩分配试算", sub: "每一项你自己定，最后看这门课会不会挂", role: "student" },
    },
    {
      path: "/counselor",
      name: "counselor",
      component: () => import("@/views/CounselorView.vue"),
      meta: { title: "辅导员工作台", sub: "风险名单、智慧森林与家校沟通，点节点进入", role: "counselor", home: true },
    },
    {
      path: "/admin",
      name: "admin",
      component: () => import("@/views/AdminView.vue"),
      meta: { title: "教务总控台", sub: "全局看板、规则配置与账号维护，点节点进入", role: "admin", home: true },
    },
    {
      path: "/parent",
      name: "parent",
      component: () => import("@/views/ParentView.vue"),
      meta: { title: "孩子这一学期", sub: "状态解读、家校沟通与 AI 对话，点节点进入", role: "parent", home: true },
    },
    {
      path: "/teacher",
      name: "teacher",
      component: () => import("@/views/TeacherView.vue"),
      meta: { title: "课堂观察窗", sub: "课堂学情、教学资源与 AI 对话，点节点进入", role: "teacher", home: true },
    },
    // ---- 看板版块：每条一个独立页面，由 portal 节点直接跳 ----
    ...SECTIONS.map((s) => ({
      path: s.path,
      name: s.name,
      component: s.view,
      meta: { title: s.title, sub: s.sub, role: s.role, section: s.section },
    })),
    {
      path: "/teacher/resources",
      name: "teacher-resources",
      component: () => import("@/views/ResourceView.vue"),
      meta: { title: "教学资源", sub: "上传历年真题与网课给学生", role: "teacher" },
    },
    {
      path: "/student/resources",
      name: "student-resources",
      component: () => import("@/views/ResourceView.vue"),
      meta: { title: "学习资源", sub: "老师上传的真题与网课", role: "student" },
    },
    {
      path: "/messages",
      name: "messages",
      component: () => import("@/views/MessageView.vue"),
      meta: { title: "家校沟通", sub: "家长与辅导员直接对话，双向实时可见", roles: ["parent", "counselor"] },
    },
    { path: "/:pathMatch(.*)*", redirect: "/student" },
  ],
  scrollBehavior(to) {
    // 版块是独立页面，进页面永远回到顶部（老锚点已由 HASH_ALIAS 改写成路由）
    if (to.hash) return false;
    return { top: 0 };
  },
});

/**
 * 每次打开链接都先落在登录首页（/login 那张"五个入口，各看各的"）。
 *
 * 以前：token 存在 localStorage，关掉页面再打开会接着上次那一页进来。
 * 现在：这一轮页面加载的第一次导航一律改写到 /login——登录页上有
 * 「继续进入」按钮，已登录的人一下点回去，不会真的重新输密码。
 *
 * 只影响"整页加载"这一下。登录之后在应用里点来点去是 SPA 内跳转，
 * 不会再经过这里，所以不会把人反复弹回登录页。
 */
let bootNav = true;
/** 本次导航就是"落地到登录页"，别因为身上还有 token 把它弹回端口 */
let landingLogin = false;

router.beforeEach(async (to) => {
  if (bootNav) {
    bootNav = false;
    landingLogin = true;
    if (to.name !== "login") return withShare("/login");
  }

  // 老书签 /student#grade 这类地址，先改写成对应的独立页面
  const alias = HASH_ALIAS[`${to.path}${to.hash}`];
  if (alias) return withShare(alias);

  const auth = useAuthStore();

  if (to.meta?.public) {
    if (to.name === "login" && auth.token && !landingLogin) {
      if (!auth.profile) await auth.hydrate();
      if (auth.profile) return withShare(HOME_OF[auth.profile.role]);
    }
    return true;
  }

  if (!auth.token) {
    // 不带 next 回跳：五个端的入口是固定的，登录后按身份直接进自己的端，
    // 免得把带 query 的地址再套进 query（会出现 /login?next=/student?sharecode=…&sharecode=…）
    return withShare("/login");
  }

  if (!auth.profile) await auth.hydrate();
  if (!auth.profile) return withShare("/login");

  const need = to.meta?.role as Role | undefined;
  if (need && need !== auth.profile.role) {
    // 越界的地址直接送回自己的端，并给出提示（由目标页读取 query 提示）
    return withShare(`${HOME_OF[auth.profile.role]}?blocked=${encodeURIComponent(String(to.name))}`);
  }
  // 多角色限制：家校沟通 parent / counselor 都可进，其他角色挡回自己端
  const allowed = to.meta?.roles as string[] | undefined;
  if (allowed && allowed.length && !allowed.includes(auth.profile.role)) {
    return withShare(`${HOME_OF[auth.profile.role]}?blocked=${encodeURIComponent(String(to.name))}`);
  }
  return true;
});

router.afterEach((to) => {
  // 落地这一趟走完就撤掉豁免：之后再主动去 /login（比如退出登录）照旧按原规则走
  landingLogin = false;
  const title = (to.meta?.title as string) || "学业护航";
  document.title = `${title} · 学业护航`;
  // 视图区自身滚动，路由切换后回到顶部。
  // 用双层 rAF 等组件挂载完毕，并强制 .view 重排一次，
  // 否则从对话抽屉（overflow:hidden）切回普通页时浏览器不会立即刷新滚动状态。
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const view = document.querySelector(".view") as HTMLElement | null;
      if (!view) return;
      void view.offsetHeight;
      view.scrollTo({ top: 0 });
    });
  });
});

export default router;
