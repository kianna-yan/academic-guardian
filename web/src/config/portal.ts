import type { Role } from "@/types";
import { MODULES, type NavItem } from "@/config/modules";

/**
 * 门户首屏的图形配置。
 *
 * 三条规则：
 * 1. **清单有几条，画布上就有几个节点**——节点由 `MODULES` 生成，不多不少。
 * 2. **形状统一**：所有端、所有节点都是同一枚尖顶六边形，层次靠大小、
 *    实心/描边和轻微旋转拉开，不靠换形状。
 * 3. **坐标是手写死的，不是算出来的**——网格算法一定会排出「齐整」的观感，
 *    所以每一端的节点位置都按构图单独摆：间距不等、上下不相齐、允许某一端
 *    整体偏左或偏右。换数量时只改这张表，排布逻辑不参与。
 */
export type NodeShape = "diamond" | "pent" | "hex" | "oct" | "dec";

export interface PortalNode {
  key: string;
  no: string;
  label: string;
  en: string;
  /** 画布坐标，百分比 */
  x: number;
  y: number;
  /** 只转形状层，文字层保持水平——像手贴便签的轻微歪斜 */
  rot?: number;
  /** 单个节点的缩放，0.94~1.05 之间来回，避免整齐划一 */
  scale?: number;
  /** 外形：正多边形的边数，0 表示正圆 */
  sides: number;
  /** 目标路由：点节点直接去这一页 */
  to?: string;
  /** 唤起 AI 对话抽屉 */
  act?: "ai";
  /** 需要显示未读数的节点 */
  badge?: "checkin" | "messages";
  tone?: "risk" | "learn" | "ai";
  note?: string;
}

export interface PortalMeta {
  kicker: string;
  /** 描边那一行 */
  outline: string;
  /** 实心那一行 */
  solid: string;
  /** 画布左上角的小字 */
  mark: string;
  /** 画布右下角的小字 */
  trace: string;
  /** 左侧大标题的第一行（整行独立） */
  lead: string;
  /** 第二行里数字前面的词，如「你还有」；不填就只有数字和 tail */
  mid?: string;
  /** 大标题的后半句 */
  tail: string;
  /** 标题下面那段说明 */
  sub: string;
  /** 焦点卡左上角的方括号标签，如「本院」「本校」 */
  focusTag: string;
}

/** 入口数量 → 形状 */
export function shapeOf(count: number): NodeShape {
  if (count <= 4) return "diamond";
  if (count === 5) return "pent";
  if (count === 6) return "hex";
  if (count <= 8) return "oct";
  return "dec";
}

/** 形状的边数 */
export function sidesOf(shape: NodeShape): number {
  if (shape === "diamond") return 4;
  if (shape === "pent") return 5;
  if (shape === "hex") return 6;
  if (shape === "oct") return 8;
  return 10;
}

/** 正多边形顶点，从正上方开始顺时针；圆心 50,50 */
export function polygonPoints(sides: number, r = 47): string {
  const out: string[] = [];
  for (let i = 0; i < sides; i++) {
    const a = ((-90 + (i * 360) / sides) * Math.PI) / 180;
    out.push(`${(50 + r * Math.cos(a)).toFixed(2)},${(50 + r * Math.sin(a)).toFixed(2)}`);
  }
  return out.join(" ");
}

/** 形状直径：入口越多缩得越小，保证 11 个节点也不打架 */
export function sizeOf(count: number): number {
  if (count <= 4) return 94;
  if (count <= 6) return 78;
  if (count <= 8) return 70;
  return 64;
}

/* ==========================================================================
   手写坐标表
   --------------------------------------------------------------------------
   画布是 100×100 的百分比坐标系。约定：
   · x 留 6~93，y 留 8~87（上面是 PORTAL 小字，下面是 AI 输入条）
   · 纵向要铺满：y 只用到 74 的话，画布底下会空出好大一截，整张图会显得头重
   · 相邻节点横向至少隔 16、纵向至少隔 20，重点节点按 1.28 倍再留一点余量
   · 编号顺序就是点的顺序，主链顺着编号连，所以表的顺序决定了线怎么走
   ========================================================================== */
const LAYOUT: Record<Role, [number, number][]> = {
  // 11 个：两道波。上波从左扬到右，右端下折成中波折回左，最后两道收在底部。
  // 重点是拉开：同排横向不挤、两波之间留出一整个节点的空档。
  student: [
    [13, 27], // 01 学业对话（实心）
    [30, 11],
    [49, 23],
    [68, 10],
    [85, 26],
    [87, 52],
    [66, 44],
    [43, 50], // 08 学情总览（实心，落在波谷，四周都是描边节点）
    [20, 68],
    [38, 85],
    [65, 77],
  ],
  // 4 个：一个 Z 字，靠疏密和转角撑住画面，不摆成四角方框。
  // 纵向两两至少错开 18 个单位（画布高约 590px，18 单位≈106px，正好一个节点的高度），
  // 否则 01 和 03 会在视觉上连成一条横线。
  counselor: [
    [14, 34],
    [36, 82],
    [57, 14],
    [86, 62],
  ],
  // 5 个：一条对角线 + 一道弧。两枚实心分别压在左下与右上，
  // 三个描边节点绕在外侧，不走「齐排一行」那种呆板的路子
  admin: [
    [15, 32], // 01 教务对话（实心）
    [84, 68], // 02 全校概览（实心）
    [80, 16],
    [55, 86],
    [22, 58],
  ],
  // 3 个：不等边三角形，实心一枚在上、一枚在右下，描边那枚补右上
  teacher: [
    [17, 32],
    [58, 78],
    [86, 14],
  ],
  // 3 个：一个三角，左上角起、右上角折回、底部收在中偏左
  parent: [
    [16, 26],
    [85, 44],
    [48, 84],
  ],
};

/**
 * 所有节点统一用的外形：尖顶正六边形（顶点在上，左右两侧竖边）。
 * 原来是六/八/五/圆混排，现在按需求收成同一种形状——靠大小、旋转和
 * 实心/描边的差别拉开层次，不再靠换形状。
 */
const SIDES = 6;

/** 实心重点节点：AI 对话 + 各端那块最该看的板 */
const MAIN_KEYS = ["chat", "overview", "roster", "board", "classroom", "status"];
export function isMainKey(key: string, i = -1): boolean {
  return i === 0 || MAIN_KEYS.includes(key);
}

/** 每端节点的短名（只影响画布，菜单仍是全名） */
const SHORT_LABEL: Record<string, string> = {
  "历年真题 · 网课": "真题与网课",
};

/** 每端节点的歪斜角度，手挑的不规则序列，不用取模循环 */
const ROT: Record<Role, number[]> = {
  student: [4, -3, 5, -4, 3, -5, 4, -2, 5, -3, 4],
  counselor: [-4, 5, -5, 3],
  admin: [5, -4, 3, -5, 4],
  teacher: [-4, 5, -3],
  parent: [4, -5, 3],
};

/** 单个节点的缩放微差，让形状不完全一样大 */
const SCL: number[] = [1, 0.95, 1.03, 0.97, 1.02, 0.94, 1.04, 0.98, 1.01, 0.96, 1.03];

/** 少数节点换一种笔触：AI 用陶土赭虚线，风险/成长类压深一档 */
const TONE: Record<string, PortalNode["tone"]> = {
  chat: "ai",
  roster: "risk",
  forest: "learn",
  tree: "learn",
};

/** 表里没有这一端（或数量对不上）时的兜底：沿一道浅弧均匀铺开 */
function spread(n: number): [number, number][] {
  const out: [number, number][] = [];
  for (let i = 0; i < n; i++) {
    const t = n === 1 ? 0.5 : i / (n - 1);
    out.push([10 + t * 80, 46 - Math.sin(t * Math.PI) * 20 + (i % 2 ? 6 : -6)]);
  }
  return out;
}

/** 把一端的所有条目摊平成画布节点：编号、坐标、动作都在这里定下来 */
export function buildNodes(role: Role): PortalNode[] {
  const items: NavItem[] = (MODULES[role] ?? MODULES.student).flatMap((g) => g.items);
  const base = LAYOUT[role];
  const pos = base && base.length === items.length ? base : spread(items.length);

  return items.map((it, i) => ({
    key: it.key,
    no: String(i + 1).padStart(2, "0"),
    // 菜单里那几个长名字在图上塞不进形状，这里换短的；菜单本身不动
    label: SHORT_LABEL[it.label] ?? it.label,
    en: it.en,
    x: pos[i][0],
    y: pos[i][1],
    rot: ROT[role]?.[i] ?? 0,
    scale: SCL[i % SCL.length],
    // 全端统一种形状：尖顶六边形。重点节点只是更大、更实，形状不再区分
    sides: SIDES,
    to: it.to,
    act: it.chat ? "ai" : undefined,
    badge: it.badge,
    tone: TONE[it.key],
    note: it.hint,
  }));
}

export const PORTAL: Record<Role, PortalMeta> = {
  student: {
    kicker: "STUDENT PORTAL / 我的学习空间",
    outline: "学业",
    solid: "画像",
    mark: "PIPELINE / LEARN",
    trace: "COURSE → CHECKIN → TRACK → TREE",
    lead: "从今天这节课，",
    mid: "到期末还有 ",
    tail: "件事",
    sub: "左边是这两天该交的，右边是期末前要补的。打卡 10 秒、试算随手调，改完的数立刻反映到风险分上。",
    focusTag: "本周",
  },
  counselor: {
    kicker: "COUNSELOR PORTAL / 班级研判台",
    outline: "一个班",
    solid: "四件事",
    mark: "PIPELINE / RISK",
    trace: "SIS → EXAM → CLEAN → SCORE → NOTIFY",
    lead: "名单会自己说话，",
    tail: "件事等你拍板",
    sub: "先分诊、再谈话、后记台账，家长那边随时能接上。点哪个节点，数据就跟到哪一步。",
    focusTag: "本班",
  },
  admin: {
    kicker: "ACADEMIC OFFICE / 全校总控台",
    outline: "全校",
    solid: "总控台",
    mark: "PIPELINE / GOVERN",
    trace: "RULE → RECALC → RANK → EXPORT",
    lead: "红线一改，全校重算——",
    tail: "件事你得盯",
    sub: "分布、对比、排行都在同一屏，改完阈值立刻落到各端。账号和课程也在这张图上维护，不用逐级通知。",
    focusTag: "本校",
  },
  teacher: {
    kicker: "FACULTY PORTAL / 课堂观察窗",
    outline: "课堂",
    solid: "观察窗",
    mark: "PIPELINE / CLASS",
    trace: "ATTEND → HOMEWORK → SCORE → ADVISE",
    lead: "上课铃响之前，",
    tail: "件事值得先看",
    sub: "考勤、作业、分数按课堂顺序排开；错在哪、该补什么、给谁发消息，点进去就是那节课的数据。",
    focusTag: "我的课",
  },
  parent: {
    kicker: "FAMILY PORTAL / 孩子这一学期",
    outline: "孩子",
    solid: "这学期",
    mark: "PIPELINE / FAMILY",
    trace: "SCORE → RISK → CARE → LETTER",
    lead: "不用看懂分数，",
    tail: "件事和你有关",
    sub: "孩子在学校怎么样、学校做了什么、家里能配合什么——都用人话写，点开就能回一句。",
    focusTag: "我家",
  },
};
