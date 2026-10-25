import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/student" },
    {
      path: "/student",
      name: "student",
      component: () => import("@/views/StudentView.vue"),
      meta: { title: "学生端", sub: "看清自己的学业状态，并拿到可执行的补救路径" },
    },
    {
      path: "/counselor",
      name: "counselor",
      component: () => import("@/views/CounselorView.vue"),
      meta: { title: "辅导员端", sub: "按风险排序的名单、谈话要点与跟踪记录" },
    },
    {
      path: "/admin",
      name: "admin",
      component: () => import("@/views/AdminView.vue"),
      meta: { title: "教务端", sub: "规则配置、全校看板与预警名单导出" },
    },
    {
      path: "/parent",
      name: "parent",
      component: () => import("@/views/ParentView.vue"),
      meta: { title: "家长端", sub: "了解孩子在校情况，与学校形成合力" },
    },
    { path: "/:pathMatch(.*)*", redirect: "/student" },
  ],
  scrollBehavior() {
    return { top: 0 };
  },
});

router.afterEach((to) => {
  const title = (to.meta?.title as string) || "学业护航";
  document.title = `${title} · 学业护航`;
  // 视图区自身滚动，路由切换后回到顶部
  requestAnimationFrame(() => {
    document.querySelector(".view")?.scrollTo({ top: 0 });
  });
});

export default router;
