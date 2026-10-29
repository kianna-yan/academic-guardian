# -*- coding: utf-8 -*-
"""意图识别与多轮指代的系统性测试：直接调 Agent，不起服务。

覆盖：用户指名的三个 bug（通知家长误判 / 第N个指代 / 老师电话落空）
+ 四端评委可能问的常规题 + 原有能力回归。
"""
import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

sys.path.insert(0, ".")
from app import _make_agent, MEMORY  # noqa: E402

agent = _make_agent()
PASS, FAIL = [], []


def ask(role, sid, msg, profile, check, label):
    d = agent.answer(role, sid, msg, "测试大学", profile=profile)
    reply = d["reply"]
    intent = d["intent"]
    ok, why = check(reply, intent)
    tag = "PASS" if ok else "FAIL"
    (PASS if ok else FAIL).append(label)
    print(f"[{tag}] {label}")
    print(f"      intent={intent}  {reply[:110].replace(chr(10), ' ⏎ ')}")
    if not ok:
        print(f"      期望: {why}")
    print()


stu = {"role": "student", "account": "20240001"}
cou = {"role": "counselor", "account": "2024014589"}
par = {"role": "parent", "account": "20240001"}
adm = {"role": "admin", "account": "1234567899"}

# ---------- 1. 用户指名的三个 bug ----------
ask("student", "20240001", "学校什么情况下会通知家长？", stu,
    lambda r, i: ((i == "policy" and "家长" in r and "预警" not in r[:15]) or (i == "policy" and "查到" in r), "policy 意图 + 条款内容，不能答成自己的风险分"),
    "学生：学校什么情况下会通知家长？（原误判为 letter→风险分）")

ask("student", "20240001", "数据结构老师的电话是多少？", stu,
    lambda r, i: (i == "contact" and "138-0013-8001" in r, "contact 意图 + 周立群电话 138-0013-8001"),
    "学生：数据结构老师的电话？（原文不对题答风险分）")

# 先给名单（写记忆），再问第2个
agent.answer("counselor", None, "本班红色预警名单", "测试大学", profile=cou)
ask("counselor", None, "第2个学生的情况展开说说", cou,
    lambda r, i: ("夏立轩" in r and "风险最高的 6 位" not in r, "展开名单第2位（夏立轩），不能再返回完整名单"),
    "导员：名单→第2个学生的情况展开说说（原返回完整名单）")

# ---------- 2. 新增能力 ----------
ask("student", "20240001", "我缺了几次课？", stu,
    lambda r, i: (i == "attendance" and ("旷课" in r or "迟到" in r) and "周" in r, "attendance 意图 + 具体周次明细"),
    "学生：我缺了几次课？")

ask("student", "20240001", "我哪次作业没交？", stu,
    lambda r, i: (i == "homework" and ("未交" in r or "迟交" in r or "全部按时" in r), "homework 意图 + 未交/迟交明细"),
    "学生：我哪次作业没交？")

ask("student", "20240001", "这学期修了多少学分？", stu,
    lambda r, i: (i == "course" and "学分" in r, "course 意图 + 学分统计"),
    "学生：这学期修了多少学分？")

ask("student", "20240001", "数据结构老师的邮箱和答疑时间", stu,
    lambda r, i: (i == "contact" and "zhoulq@cs.univ.edu.cn" in r and "周二" in r, "邮箱 zhoulq@cs.univ.edu.cn + 答疑周二"),
    "学生：数据结构老师的邮箱和答疑时间")

ask("student", "20240001", "今天天气怎么样？", stu,
    lambda r, i: ("答不准" in r or "查到" in r, "兜底：诚实说不知道或给条款，绝不答风险分"),
    "学生：今天天气怎么样？（兜底不得文不对题）")

ask("parent", "20240001", "孩子的作业哪次没交？", par,
    lambda r, i: (i == "homework" and ("未交" in r or "迟交" in r or "全部按时" in r), "家长端作业明细"),
    "家长：孩子的作业哪次没交？")

ask("parent", "20240001", "数据结构老师怎么联系？", par,
    lambda r, i: (i == "contact" and "138-0013-8001" in r, "家长端查老师电话"),
    "家长：数据结构老师怎么联系？")

ask("parent", "20240001", "我们家长能做什么？", par,
    lambda r, i: ("在家能帮上忙" in r or "三件事" in r, "家长配合建议"),
    "家长：我们家长能做什么？")

ask("counselor", None, "数据结构老师是谁？", cou,
    lambda r, i: (i == "contact" and "周立群" in r, "导员端查老师"),
    "导员：数据结构老师是谁？")

# ---------- 3. 原有能力回归 ----------
ask("student", "20240001", "我的风险分为什么这么高？", stu,
    lambda r, i: (i == "why" and "62.7" in r, "why 回归"),
    "回归：学生问风险分原因")

ask("student", "20240001", "挂多少学分会被降级？", stu,
    lambda r, i: (i == "policy" and "25 学分" in r, "policy 回归"),
    "回归：挂多少学分会被降级")

ask("student", "20240001", "我的成绩是在涨还是在掉？", stu,
    lambda r, i: (i == "trend" and "走势" in r, "trend 回归"),
    "回归：成绩涨还是掉")

ask("student", "20240001", "这学期还来得及补回来吗？", stu,
    lambda r, i: (i == "advice" and "做" in r, "advice 回归"),
    "回归：还来得及吗")

ask("student", "20240001", "导出我的告知函", stu,
    lambda r, i: (i == "export" and "下载" in r, "export 回归"),
    "回归：导出告知函")

agent.answer("counselor", None, "许雨桐", "测试大学", profile=cou)
ask("counselor", None, "给他生成谈话要点", cou,
    lambda r, i: (i == "brief" and "许雨桐" in r, "指代「他」→许雨桐 + brief 回归"),
    "回归：导员指名→「他」的谈话要点")

ask("counselor", None, "记录：已完成谈话", cou,
    lambda r, i: (i == "record" and "已记录" in r, "record 回归"),
    "回归：记录已完成谈话")

ask("counselor", None, "本班谁的风险上升最快？", cou,
    lambda r, i: ("上升最快" in r or "没有" in r, "rising 名单回归"),
    "回归：谁的风险上升最快")

ask("admin", None, "全校风险分布如何？", adm,
    lambda r, i: (i == "overview" and "红色" in r, "overview 回归"),
    "回归：教务端全校分布")

# ---------- 4. 教师端（第五端口，AI 独立互不相通）----------
tea = {"role": "teacher", "account": "2024014501", "name": "周立群", "advisor": "周立群"}
ask("teacher", None, "我教的课", tea,
    lambda r, i: ("数据结构" in r and "学分" in r, "course：我教的课清单"),
    "教师：我教的课")

ask("teacher", None, "我课上的学生", tea,
    lambda r, i: ("风险分" in r and "周立群" not in r[:5], "roster：我课上的学生名单"),
    "教师：我课上的学生")

ask("teacher", None, "班均多少", tea,
    lambda r, i: ("班均" in r and "77" in r, "班均：各课期中班均"),
    "教师：班均多少")

# 多轮指代：先给名单，再问第2个
agent.answer("teacher", None, "我课上的学生", "测试大学", profile=tea)
ask("teacher", None, "第2个学生缺了几次课", tea,
    lambda r, i: ("旷课" in r and "风险最高的" not in r[:20], "展开名单第2位考勤"),
    "教师：名单→第2个学生缺了几次课")

ask("teacher", None, "我该重点关注谁", tea,
    lambda r, i: ("红色" in r or "重点" in r, "advice：教学重点关注名单"),
    "教师：我该重点关注谁")

# AI 隔离：教师问「你是谁为谁服务」，应是任课老师视角（提自己教的课），不是学生口吻
ask("teacher", None, "用一句话说：你是谁，专门为谁服务的？", tea,
    lambda r, i: ("课" in r or "教" in r or "学生" in r, "teacher 人设：任课老师视角"),
    "教师：你是谁为谁服务（人设独立）")

print("=" * 50)
print(f"通过 {len(PASS)} / 总 {len(PASS) + len(FAIL)}")
if FAIL:
    print("失败项：")
    for f in FAIL:
        print("  -", f)
    sys.exit(1)
print("ALL PASSED")
