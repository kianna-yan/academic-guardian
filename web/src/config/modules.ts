import type { Role } from "@/types";

/** 侧栏的一个模块入口 */
export interface NavItem {
  key: string;
  label: string;
  /** 路由 + 可选锚点，例如 /student#grade */
  to: string;
  /** 一句话说明这个区域是干什么的，鼠标悬停可见 */
  hint?: string;
  /** AI 对话入口：不走路由，切回对话主界面 */
  chat?: boolean;
  /** 徽标：待打卡的节数由页面自己写进 store，这里只标记位置 */
  badge?: "checkin";
}

export interface NavGroup {
  key: string;
  label: string;
  /** 区域说明，显示在组标题右侧 */
  caption?: string;
  items: NavItem[];
}

/**
 * 模块分区：按"什么时候用"分组，而不是按开发顺序罗列。
 * - 学生端：学习空间（每节课都在用）→ 我的成长（看得见）→ 学业档案（看结果）→ AI 顾问（随时问）
 * - 其他端：各自的业务区域，锚点对应页面里的区块
 */
export const MODULES: Record<Role, NavGroup[]> = {
  student: [
    {
      key: "learn",
      label: "学习空间",
      caption: "每节课后",
      items: [
        { key: "schedule", label: "我的课表", to: "/student/schedule", hint: "这周哪几节、在哪上、记过没有" },
        { key: "checkin", label: "课后打卡", to: "/student/checkin", hint: "10 秒记一句：听懂没有、从哪儿开始没懂", badge: "checkin" },
        { key: "track", label: "学习轨迹", to: "/student/track", hint: "每门课一条线，断在哪一眼看见" },
      ],
    },
    {
      key: "growth",
      label: "我的成长",
      caption: "看得见",
      items: [
        { key: "tree", label: "我的智慧树", to: "/student/tree", hint: "一颗果实一门课，颜色看学科、光环看风险" },
        { key: "simulate", label: "成绩分配试算", to: "/student/simulate", hint: "每一项你自己调，实时看会不会挂" },
      ],
    },
    {
      key: "archive",
      label: "学业档案",
      caption: "看结果",
      items: [
        { key: "overview", label: "学情总览", to: "/student", hint: "风险分、六因素归因、行动清单" },
        { key: "grade", label: "成绩走势", to: "/student#grade", hint: "五个学期 + 本学期测评" },
        { key: "records", label: "考勤与作业", to: "/student#records", hint: "逐日考勤、作业截止、任课老师" },
        { key: "appeal", label: "复核与异议", to: "/student#appeal", hint: "记录不对可以提复核" },
      ],
    },
    {
      key: "ai",
      label: "AI 顾问",
      caption: "随时问",
      items: [{ key: "chat", label: "学业对话", to: "/student", chat: true, hint: "基于你自己的数据回答，数字都由引擎算" }],
    },
  ],
  counselor: [
    {
      key: "work",
      label: "班级工作台",
      caption: "本周先做",
      items: [
        { key: "roster", label: "风险名单", to: "/counselor#roster", hint: "按风险排序，一人一句先做哪件事" },
      ],
    },
    {
      key: "ai",
      label: "AI 顾问",
      items: [{ key: "chat", label: "辅导员对话", to: "/counselor", chat: true, hint: "批量问、点名问都行" }],
    },
  ],
  admin: [
    {
      key: "board",
      label: "全局看板",
      caption: "教务视角",
      items: [
        { key: "overview", label: "全校概览", to: "/admin#board", hint: "预警分布、班级对比、风险因素排行" },
        { key: "rules", label: "规则配置", to: "/admin#rules", hint: "红黄线阈值，一拖全校重算" },
      ],
    },
    {
      key: "manage",
      label: "教务维护",
      items: [
        { key: "accounts", label: "学生账号", to: "/admin#accounts", hint: "批量开通、重置初始密码" },
        { key: "curriculum", label: "课程与教师", to: "/admin#curriculum", hint: "导入任课教师与联系方式" },
      ],
    },
  ],
  teacher: [
    {
      key: "class",
      label: "课堂",
      caption: "任课视角",
      items: [
        { key: "view", label: "课堂学情", to: "/teacher#classroom", hint: "分数分布、出勤、作业、待办" },
      ],
    },
  ],
  parent: [
    {
      key: "child",
      label: "孩子情况",
      items: [
        { key: "overview", label: "状态解读", to: "/parent#overview", hint: "学校已做什么、家里可以怎么配合" },
      ],
    },
  ],
};

/** 端名，给侧栏顶部用 */
export const ROLE_LABEL: Record<Role, string> = {
  student: "学生端",
  counselor: "辅导员端",
  admin: "教务端",
  parent: "家长端",
  teacher: "教师端",
};
