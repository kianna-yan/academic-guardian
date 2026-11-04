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
  /** 徽标：待打卡的节数由页面自己写进 store，这里只标记位置；
   *  messages 表示家校沟通未读数（由 notices store 提供） */
  badge?: "checkin" | "messages";
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
 * - 五个端统一把「AI 顾问」放在最上面：对话是主入口，进来第一眼就该看见它，
 *   翻到侧栏最底部才找到反而像个附赠功能。
 * - 学生端其余分区：学习空间（每节课都在用）→ 我的成长（看得见）→ 学业档案（看结果）
 * - 其他端：各自的业务区域，锚点对应页面里的区块
 */
export const MODULES: Record<Role, NavGroup[]> = {
  student: [
    {
      key: "ai",
      label: "AI 顾问",
      caption: "随时问",
      items: [{ key: "chat", label: "学业对话", to: "/student", chat: true, hint: "基于你自己的数据回答，数字都由引擎算" }],
    },
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
        { key: "resources", label: "学习资源", to: "/student/resources", hint: "老师上传的历年真题与网课" },
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
  ],
  counselor: [
    {
      key: "ai",
      label: "AI 顾问",
      caption: "随时问",
      items: [{ key: "chat", label: "辅导员对话", to: "/counselor", chat: true, hint: "批量问、点名问都行" }],
    },
    {
      key: "contact",
      label: "家校沟通",
      caption: "联系家长",
      items: [
        { key: "messages", label: "家校沟通", to: "/messages", hint: "与各学生家长的直接对话，按学生分组，点谁和谁聊", badge: "messages" },
      ],
    },
    {
      key: "work",
      label: "班级工作台",
      caption: "本周先做",
      items: [
        { key: "roster", label: "风险名单", to: "/counselor#roster", hint: "按风险排序，一人一句先做哪件事" },
        { key: "forest", label: "智慧森林", to: "/counselor#forest", hint: "每个学生一棵树，每班一片森林：颜色一眼看出整体长势" },
      ],
    },
  ],
  admin: [
    {
      key: "ai",
      label: "AI 顾问",
      caption: "随时问",
      items: [{ key: "chat", label: "教务对话", to: "/admin", chat: true, hint: "全校统计、规则口径与校规条款，问我就行" }],
    },
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
      key: "ai",
      label: "AI 顾问",
      caption: "随时问",
      items: [{ key: "chat", label: "教学对话", to: "/teacher", chat: true, hint: "我课上学生的考勤、作业与风险，问我就行" }],
    },
    {
      key: "class",
      label: "课堂",
      caption: "任课视角",
      items: [
        { key: "view", label: "课堂学情", to: "/teacher#classroom", hint: "分数分布、出勤、作业、待办（按班级分组）" },
      ],
    },
    {
      key: "resources",
      label: "教学资源",
      caption: "给学生用",
      // 真题与网课在同一页的两个页签里，菜单只留一个入口，
      // 免得侧栏出现两条都跳同一个地址的项。
      items: [
        { key: "resources", label: "历年真题 · 网课", to: "/teacher/resources", hint: "上传历年期末试卷与网课视频/讲义，学生在「学习资源」里下载" },
      ],
    },
  ],
  parent: [
    {
      key: "ai",
      label: "AI 顾问",
      caption: "随时问",
      items: [{ key: "chat", label: "家校对话", to: "/parent", chat: true, hint: "孩子这学期怎么样，用通俗的话讲给你听" }],
    },
    {
      key: "contact",
      label: "家校沟通",
      caption: "直接联系",
      items: [
        { key: "messages", label: "家校沟通", to: "/messages", hint: "与孩子辅导员的直接对话，消息实时可见", badge: "messages" },
      ],
    },
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
