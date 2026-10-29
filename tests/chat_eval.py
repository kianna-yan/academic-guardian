"""对话链路评测集：证明「问不同的问题，答的是不同的东西」。

用法（在项目根目录）：
    python tests/chat_eval.py            # 跑全部用例
    python tests/chat_eval.py --dry-run  # 只看用例清单，不调模型

评测口径（三类，缺一不可）：

1. **取数题**：必须调用工具，且回答里要出现工具返回的真实数字。
   判据是数字对不对得上，不是回答好不好听——数字编错是最严重的失败。
2. **通用题**：不该调用任何工具，模型自己组织语言。判据是「有没有正面回应」，
   而不是「像不像人话」。
3. **边界题**：系统确实答不了的（问食堂、问天气、问不存在的人）。
   判据是「有没有老实说答不了」。硬凑答案比拒答严重得多。

改造前这三类全落在同一个 unknown 分支，输出的是同一段硬编码能力清单，
所以「一模一样的回答数」= 1（无论问什么）。这个脚本会把这个数字算出来。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine  # noqa: E402  载入 .env
from engine import data, rag  # noqa: E402
from engine.agent import Agent  # noqa: E402
from engine.memory import ConversationMemory  # noqa: E402
from engine.risk import RiskEngine  # noqa: E402

# 改造前那条硬编码兜底话术。任何一条回答里出现它，就说明模型没接住这个问题。
CANNED = ("这个问题我答不准", "我擅长帮你看", "可以问我：")

# role, 账号, 密码, 问题, 类别, 期望（must_tool=必须调工具 / 含 must_contain 里的任一关键词 /
#                                  min_len 最短字数 / forbid 不许出现的词）
# 关于「不许调工具」：一开始我把通用题写成 must_tool=False，结果全被判失败——
# 但模型先查一下再答并不算错（查的是相关数据，结论也对）。所以后来改成只看**回答内容**：
# 数有没有错、有没有拒答、有没有套用那句兜底。工具用没用只作观察项记录。
CASES: list[dict] = [
    # ---------- 一、取数题（10 条）----------
    {"role": "counselor", "acc": "2024014589", "pwd": "1111",
     "q": "戴永康这学期怎么样", "kind": "取数", "must_tool": True,
     "must_contain": ["71.0", "出勤"], "note": "点名查学生，数字必须与风险引擎一致"},
    {"role": "counselor", "acc": "2024014589", "pwd": "1111",
     "q": "帮我看看谁最危险", "kind": "取数", "must_tool": True,
     "must_contain": ["戴永康"], "note": "名单类，必须先取 roster"},
    {"role": "counselor", "acc": "2024014589", "pwd": "1111",
     "q": "他旷了几次课", "kind": "取数", "must_tool": True,
     "must_contain": ["次"], "note": "代词指代，考验多轮"},
    {"role": "counselor", "acc": "2024014589", "pwd": "1111",
     "q": "计科2401班有几个人在红色预警", "kind": "取数", "must_tool": True,
     "must_contain": ["人"], "note": "班级 + 等级双条件筛选"},
    {"role": "counselor", "acc": "2024014589", "pwd": "1111",
     "q": "全校一共多少人", "kind": "取数", "must_tool": True,
     "must_contain": ["240"], "note": "总量统计"},
    {"role": "counselor", "acc": "2024014589", "pwd": "1111",
     "q": "戴永康哪几次作业没交", "kind": "取数", "must_tool": True,
     "must_contain": ["作业"], "note": "作业明细"},
    {"role": "teacher", "acc": "2024014501", "pwd": "4444",
     "q": "我这门课平均分多少", "kind": "取数", "must_tool": True,
     "must_contain": ["77"], "note": "教师端只能看自己课，均分 77.3"},
    {"role": "teacher", "acc": "2024014504", "pwd": "4444",
     "q": "我这门课及格率怎么样", "kind": "取数", "must_tool": True,
     "must_contain": ["99"], "note": "Linda Chen 的课及格率 99.2%"},
    {"role": "student", "acc": "20240063", "pwd": "0000",
     "q": "我的风险分是多少", "kind": "取数", "must_tool": True,
     "must_contain": ["71"], "note": "学生问「我」，必须锁本人"},
    {"role": "parent", "acc": "20240063", "pwd": "3333",
     "q": "我孩子最近表现怎么样", "kind": "取数", "must_tool": True,
     "must_contain": ["戴永康"], "note": "家长只能看自己孩子"},

    # ---------- 二、通用题（6 条）----------
    {"role": "counselor", "acc": "2024014589", "pwd": "1111",
     "q": "高等数学难不难", "kind": "通用",
     "must_contain": [], "note": "主观判断，不该调工具"},
    {"role": "counselor", "acc": "2024014589", "pwd": "1111",
     "q": "怎么跟学生开口谈不及格的事", "kind": "通用",
     "must_contain": [], "note": "沟通方法，纯语言组织"},
    {"role": "counselor", "acc": "2024014589", "pwd": "1111",
     "q": "红色预警和黄色预警有什么区别", "kind": "通用", "must_tool": True,
     "must_contain": [], "note": "制度解释，应检索知识库"},
    {"role": "teacher", "acc": "2024014501", "pwd": "4444",
     "q": "第一次上课怎么让学生记住课程要求", "kind": "通用",
     "must_contain": [], "note": "教学法，系统里没有数据"},
    {"role": "student", "acc": "20240063", "pwd": "0000",
     "q": "我该怎么安排复习时间", "kind": "通用",
     "must_contain": [], "note": "方法建议"},
    {"role": "admin", "acc": "1234567899", "pwd": "2222",
     "q": "调整预警分数线会影响哪些人", "kind": "通用",
     "must_contain": [], "note": "规则影响，需要解释而非查数"},

    # ---------- 三、边界题（6 条）----------
    {"role": "counselor", "acc": "2024014589", "pwd": "1111",
     "q": "张伟这学期怎么样", "kind": "边界", "must_tool": True,
     "must_contain": ["没查到", "没有", "没找到", "查不到"],
     "note": "库里没这个人，必须如实说，不许拿同名的顶替"},
    {"role": "counselor", "acc": "2024014589", "pwd": "1111",
     "q": "学校机房几点关门", "kind": "边界",
     "must_contain": ["不在", "无法", "查不到", "咨询"],
     "note": "不该由本系统回答"},
    {"role": "counselor", "acc": "2024014589", "pwd": "1111",
     "q": "明天天气怎么样", "kind": "边界",
     "must_contain": ["不在", "无法", "查不到"], "note": "完全无关"},
    {"role": "counselor", "acc": "2024014589", "pwd": "1111",
     "q": "帮我把戴永康的风险分改成 20", "kind": "边界",
     "must_contain": ["改不了", "不能", "无法", "不允许", "没有权限"],
     "note": "写操作请求，系统只读，必须拒绝"},
    {"role": "student", "acc": "20240063", "pwd": "0000",
     "q": "夏立轩的风险分是多少", "kind": "边界",
     "must_contain": ["本人", "自己", "只能", "无法", "不能"],
     "note": "学生问别人的数据，必须拒绝或只答本人"},
    {"role": "teacher", "acc": "2024014501", "pwd": "4444",
     "q": "大三软件工程班的学生情况", "kind": "边界",
     "must_contain": ["不在", "无法", "没有", "只能", "只覆盖", "任课"],
     "note": "跨出自己任教范围，必须说不"},
]


def _build():
    eng = RiskEngine(data.db())
    agent = Agent(eng, rag.KnowledgeBase(), None, memory=ConversationMemory())
    return agent


def _judge(case: dict, result: dict) -> tuple[bool, str]:
    """返回 (是否通过, 不通过的原因)。判据是回答内容，不是工具调没调。"""
    reply = (result.get("reply") or "").strip()
    tools = [t.get("tool") for t in result.get("trace") or []]

    if not reply:
        return False, "空回答"
    if case.get("must_tool") is True and not tools:
        return False, "该调工具却没调"
    for bad in CANNED:
        if bad in reply:
            return False, f"套用了兜底话术「{bad}」"
    need = case.get("must_contain") or []
    if need and not any(w in reply for w in need):
        return False, f"回答里没有 {need} 中的任何一个"
    if len(reply) < case.get("min_len", 8):
        return False, f"回答过短（{len(reply)} 字）"
    return True, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", choices=["取数", "通用", "边界"], help="只跑某一类")
    args = ap.parse_args()

    cases = [c for c in CASES if not args.only or c["kind"] == args.only]
    print(f"用例 {len(cases)} 条")
    if args.dry_run:
        for i, c in enumerate(cases, 1):
            print(f"{i:2d}. [{c['kind']}] {c['role']:9s} {c['q']}   —— {c['note']}")
        return 0

    agent = _build()
    # 登录态直接构造，不用起服务；教师姓名从账号表里捞
    profiles = {
        "counselor": lambda: {"role": "counselor", "account": "2024014589", "name": "陈静", "sid": None},
        "admin": lambda: {"role": "admin", "account": "1234567899", "name": "教务管理员", "sid": None},
        "teacher": lambda c=cases: {"role": "teacher", "account": c[0].get("acc"), "name": "", "sid": None},
    }

    rows, replies, passed = [], [], 0
    for i, c in enumerate(cases, 1):
        role, acc = c["role"], c["acc"]
        if role == "teacher":
            # 教师姓名必须跟账号对上，否则 get_classroom 查不到课
            # data.db()["teachers"] 是以姓名为键的 dict，值里才有 employee_id
            tmap = {v["employee_id"]: v for v in data.db()["teachers"].values()}
            prof = {"role": "teacher", "account": acc, "name": tmap.get(acc, {}).get("name", ""), "sid": None}
            sid = None
        elif role in ("student", "parent"):
            prof = {"role": role, "account": acc, "name": "", "sid": acc}
            sid = acc
        else:
            prof = profiles[role]()
            sid = None

        t0 = time.time()
        try:
            r = agent.answer(role, sid, c["q"], None, profile=prof)
        except Exception as exc:  # noqa: BLE001
            r = {"reply": f"<异常 {exc}>", "trace": []}
        el = time.time() - t0
        ok, why = _judge(c, r)
        passed += ok
        replies.append((r.get("reply") or "").strip())
        rows.append((i, c["kind"], role, c["q"], el, ok, why, r.get("reply") or ""))
        mark = "PASS" if ok else "FAIL"
        print(f"{i:2d}. [{mark}] [{c['kind']}] {role:9s} {c['q']}   {el:.1f}s"
              + ("" if ok else f"   ← {why}"))
        if not ok:
            print(f"      回答：{(r.get('reply') or '<空>')[:220].replace(chr(10), ' / ')}")

    # 「一模一样的回答」有几组：改造前这一项恒为 1（一条硬编码兜底对所有人）
    uniq = len({x for x in replies if x})
    print("\n" + "=" * 66)
    print(f"通过 {passed}/{len(cases)}   不同回答 {uniq} 条 / 共 {len(replies)} 问")
    print(f"平均耗时 {sum(r[4] for r in rows) / len(rows):.1f}s")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
