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
    {
      path: "/student",
      name: "student",
      component: () => import("@/views/StudentView.vue"),
      meta: { title: "学情总览", sub: "看清自己的学业状态，并拿到可执行的补救路径", role: "student" },
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
      meta: { title: "我的智慧树", sub: "一颗果实一门课：颜色看学科，光环看风险", role: "student" },
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
      meta: { title: "辅导员端", sub: "按风险排序的名单、谈话要点与跟踪记录", role: "counselor" },
    },
    {
      path: "/admin",
      name: "admin",
      component: () => import("@/views/AdminView.vue"),
      meta: { title: "教务端", sub: "规则配置、账号开通、全校看板与名单导出", role: "admin" },
    },
    {
      path: "/parent",
      name: "parent",
      component: () => import("@/views/ParentView.vue"),
      meta: { title: "家长端", sub: "了解孩子在校情况，与学校形成合力", role: "parent" },
    },
    {
      path: "/teacher",
      name: "teacher",
      component: () => import("@/views/TeacherView.vue"),
      meta: { title: "教师端", sub: "任课视角的课堂学情与风险研判", role: "teacher" },
    },
    { path: "/:pathMatch(.*)*", redirect: "/student" },
  ],
  scrollBehavior(to) {
    // 锚点由 afterEach 处理（滚动容器是 .view，不是 window）
    if (to.hash) return false;
    return { top: 0 };
  },
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();

  if (to.meta?.public) {
    if (to.name === "login" && auth.token) {
      if (!auth.profile) await auth.hydrate();
      if (auth.profile) return withShare(HOME_OF[auth.profile.role]);
    }
    return true;
  }

  if (!auth.token) {
    // 不带 next 回跳：四个端的入口是固定的，登录后按身份直接进自己的端，
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
  return true;
});

router.afterEach((to) => {
  const title = (to.meta?.title as string) || "学业护航";
  document.title = `${title} · 学业护航`;
  // 视图区自身滚动，路由切换后回到顶部；带锚点则滚到对应区块
  requestAnimationFrame(() => {
    if (to.hash) {
      const el = document.querySelector(to.hash);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
    }
    document.querySelector(".view")?.scrollTo({ top: 0 });
  });
});

export default router;
