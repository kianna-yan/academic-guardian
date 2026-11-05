"""工具中台：把取数能力注册成大模型可调用的函数。

设计原则（对应那份五端 Agent 架构文档 5.2 节）：
1. **数字只能从这里出**。模型不许自己算、自己编，只能调用工具拿结果。
2. **返回必须裁剪**。240 人名单全塞回去 token 会爆，一律限条数。
3. **权限在服务端二次过滤**。学生/家长只能查自己，教师只能查自己课上的人，
   这个判断不交给模型——模型传什么名字都不作数。
4. **查不到就说查不到**，顺带给最接近的候选，让模型能问"是不是这个人"。

每个工具返回 dict：{"ok": bool, "data": ..., "note": str}
"""
from __future__ import annotations

import difflib
import json

MAX_ROWS = 8
MAX_RECORDS = 6

# 角色分组
ALL_ROLES = ("student", "parent", "counselor", "admin", "teacher")
STAFF = ("counselor", "admin", "teacher")          # 能查别人的人
SELF_ONLY = ("student", "parent")                  # 只能查自己的人

# ---------------------------------------------------------------- 工具说明书
# params 为 JSON Schema 的 properties；required 为必填项。
# 「name」参数对 SELF_ONLY 角色自动隐藏——学生的工具天然作用于本人。
_SPEC: dict[str, dict] = {
    "get_student": {
        "desc": "查询一名学生的基本情况：学号、班级、专业、学业导师、GPA、挂科学分、风险分与等级。"
                "问「X 这学期怎么样」「X 是谁」「X 在哪个班」时用这个。",
        "params": {
            "name": {"type": "string", "description": "学生姓名，如「戴永康」；也可传 8 位学号"},
        },
        "required": ["name"],
        "roles": ALL_ROLES,
    },
    "get_risk": {
        "desc": "查询一名学生的风险评分构成：总分、等级、六项因子各占多少分、触发了哪些硬性规则、原始指标。"
                "问「为什么风险分高」「主因是什么」「风险等级怎么算的」时用这个。",
        "params": {
            "name": {"type": "string", "description": "学生姓名或学号"},
        },
        "required": ["name"],
        "roles": ALL_ROLES,
    },
    "get_attendance": {
        "desc": "查询一名学生的课堂出勤：总旷课次数、出勤率、最长连续旷课次数、各门课的缺勤分布、最近的异常记录。",
        "params": {
            "name": {"type": "string", "description": "学生姓名或学号"},
        },
        "required": ["name"],
        "roles": ALL_ROLES,
    },
    "get_homework": {
        "desc": "查询一名学生的作业提交情况：各门课应交/已交次数、未交作业清单（含科目、标题、截止日期）。",
        "params": {
            "name": {"type": "string", "description": "学生姓名或学号"},
        },
        "required": ["name"],
        "roles": ALL_ROLES,
    },
    "get_courses": {
        "desc": "查询一名学生的在修课程与任课教师：课名、学分、任课教师姓名、职称、办公室、邮箱、答疑时间。"
                "问「我的老师都有谁」「数据结构老师邮箱」时用这个。**这个工具不含分数**，"
                "问分数用 get_scores。",
        "params": {
            "name": {"type": "string", "description": "学生姓名或学号"},
        },
        "required": ["name"],
        "roles": ALL_ROLES,
    },
    "get_timetable": {
        "desc": "查询课表：某个时间点有哪些课——哪一天、第几节、什么课、在哪间教室、谁教、上过没有、"
                "记没记过课后自评，并给出「下一节课」。"
                "when 支持「今天 / 明天 / 后天 / 本周 / 下周 / 周三 / 第 8 周 / 下一节课」，不填按本周算。"
                "凡是问「明天有没有课」「我周三第几节在哪上课」「这周课表」「下节课是什么」都用这个。"
                "**不要用 get_courses 回答上课时间**——那个工具只有课程与教师档案，没有节次和教室。",
        "params": {
            "name": {"type": "string", "description": "学生姓名或学号"},
            "when": {"type": "string",
                     "description": "时间范围：今天 / 明天 / 后天 / 本周 / 下周 / 周三 / 第 8 周 / 下一节课"},
            "course": {"type": "string", "description": "只看某一门课，如「数据结构」；不填看全部"},
        },
        "required": ["name"],
        "roles": ALL_ROLES,
    },
    "get_final_forecast": {
        "desc": "成绩构成与期末试算：每门课的考核项权重、当前各项得分、当前总评，"
                "以及「期末卷面至少要考到多少才不挂科」（同时受总评 60 分、卷面 45 分两条线约束）。"
                "给了 target（目标总评，如 85）就改算「想拿 85 分期末要考多少」。"
                "问「我期末要考多少才不挂科」「这门课想拿 85 要考多少」用这个。"
                "与 get_scores 的分工：那个给已经考出来的分，这个给还没考的期末要考多少。",
        "params": {
            "name": {"type": "string", "description": "学生姓名或学号"},
            "course": {"type": "string", "description": "只算某一门课，如「数据结构」；不填算全部"},
            "target": {"type": "number", "description": "目标总评分，如 85；不填按及格线 60 算"},
        },
        "required": ["name"],
        "roles": ALL_ROLES,
    },
    "get_todos": {
        "desc": "查询本账号的未读通知与未完成待办：学生的补交作业 / 说明缺勤 / 查看预警，"
                "辅导员的约谈与异议处理，教师的作业缺交与考勤提醒。"
                "问「我有什么待办」「有没有新通知」「待办还剩几条」用这个。",
        "params": {},
        "required": [],
        "roles": ALL_ROLES,
    },
    "get_letter": {
        "desc": "查看学业预警文书的正文要点：风险等级与得分、触发依据（出勤/作业/成绩）、"
                "要求完成的整改事项、复查日期。kind 取 student（学生告知函）/ parent（家长信）/ "
                "counselor（辅导员简报）。问「告知函写了什么」「通知书要求我做什么」「家长信内容」用这个；"
                "要把文书导成 Word 文件才用导出。",
        "params": {
            "name": {"type": "string", "description": "学生姓名或学号"},
            "kind": {"type": "string", "enum": ["student", "parent", "counselor"],
                     "description": "文书类型，学生本人用 student，家长用 parent，辅导员用 counselor"},
        },
        "required": ["name"],
        "roles": ALL_ROLES,
    },
    "get_curriculum": {
        "desc": "查询培养方案与课程档案：本学期开设的每门课的学分、性质（必修/选修）、任课教师、"
                "上课周次与节次、教室，以及这名学生的学分要求与完成进度（已修/在修/计划）。"
                "问「毕业要修多少学分」「这学期一共多少学分」「有哪些选修课」「我还差多少学分」用这个。",
        "params": {
            "name": {"type": "string", "description": "学生姓名或学号，填了才给学分进度"},
        },
        "required": [],
        "roles": ALL_ROLES,
    },
    "get_interventions": {
        "desc": "查询干预台账：这名学生已经被记录过哪些谈话与帮扶动作（时间、标题、结论、状态），"
                "以及系统建议的下一步动作。问「之前谈过几次」「上次谈了什么」「台账里有什么」用这个。",
        "params": {
            "name": {"type": "string", "description": "学生姓名或学号"},
        },
        "required": ["name"],
        "roles": ALL_ROLES,
    },
    "get_class_report": {
        "desc": "生成某个班的学情简报：在册人数、红黄人数、平均风险分、成因构成（缺勤型/作业型等）、"
                "本周建议谈话的名单与理由、值得关注的变化。"
                "问「计科2402 这周情况怎么样」「给我一份 2401 的班情简报」时用这个。"
                "与 get_roster 的分工：那个只是按风险分排的名次表，这个带成因与处置建议。",
        "params": {
            "class_name": {"type": "string", "description": "班级名，如「计科2402」"},
        },
        "required": ["class_name"],
        "roles": STAFF,
    },
    "get_messages": {
        "desc": "查询家校消息：家长端看自己与辅导员的往来消息，辅导员端按学生看与家长的对话。"
                "问「老师给我发了什么」「辅导员有没有回复我」「最近的消息」用这个。",
        "params": {
            "name": {"type": "string", "description": "学生姓名或学号（仅辅导员端需要，看某位学生的家长会话）"},
        },
        "required": [],
        "roles": ("parent", "counselor", "admin"),
    },
    "get_appeals": {
        "desc": "查询异议处理进度：学生对某条考勤/作业记录提出的申诉，现在受理到哪一步、"
                "辅导员怎么答复的；辅导员端看全部待处理异议。"
                "问「我提的异议处理了吗」「谁还有异议没处理」用这个。",
        "params": {
            "name": {"type": "string", "description": "学生姓名或学号（辅导员端可选，用于只看某人）"},
        },
        "required": [],
        "roles": ALL_ROLES,
    },
    "get_scores": {
        "desc": "查询一名学生的成绩单：每门课的期中卷面分、随堂测均分、最近一次测评、本课班均、"
                "在本课的班内排名，以及学分加权期中均分、班级均分、班内总排名；"
                "还会直接给出「分数最高的课」「相对班均优势最大的课」「相对最弱的课」。"
                "凡是问「我最好的课是哪一门」「哪门课最差」「我考了多少分」「我排第几」都用这个。",
        "params": {
            "name": {"type": "string", "description": "学生姓名或学号"},
        },
        "required": ["name"],
        "roles": ALL_ROLES,
    },
    "get_class_scores": {
        "desc": "按人排名查班级成绩：按学分加权期中均分（或指定某门课的期中卷面）排出名次，"
                "返回总人数、班均、最高最低、前几名与末几名。"
                "问「我们班谁成绩最好」「班里谁考得最差」「2401 班平均分多少」时用这个。"
                "注意区别：这个工具是**按学生排名**；老师问「我这门课班均多少 / 及格率」要用 get_classroom。"
                "学生/家长调用时只会返回本人的名次与班均，不会给出其他同学的姓名，这是权限设计。",
        "params": {
            "class_name": {"type": "string", "description": "班级名，如「计科2401」「2401班」，不填表示全部班级"},
            "course": {"type": "string", "description": "只看某一门课，如「数据结构」；不填按学分加权期中均分"},
        },
        "required": [],
        "roles": ALL_ROLES,
    },
    "get_learning_track": {
        "desc": "查询一名学生在学生端做的课后自评与学习轨迹：哪门课从第几周开始连续没听懂（断点）、"
                "卡在哪个知识点、从第几分钟开始没跟上、后面有没有接上，以及这周记了几节、还差几节。"
                "问「我从哪节课开始没听懂」「我的学习轨迹怎么样」「哪门课最该补」时用这个。"
                "这些是学生自己的判断，不参与风险分，也不能当处分依据。",
        "params": {
            "name": {"type": "string", "description": "学生姓名或学号"},
        },
        "required": ["name"],
        "roles": ALL_ROLES,
    },
    "get_roster": {
        "desc": "查询风险名单：可按班级或预警等级筛选，返回风险分最高的若干人及总人数。"
                "问「谁最危险」「红色预警有几个人」「计科2402 班情况」时用这个。",
        "params": {
            "class_name": {"type": "string", "description": "班级名，如「计科2402」，不填表示全部班级"},
            "level": {"type": "string", "enum": ["red", "yellow", "green"], "description": "预警等级"},
        },
        "required": [],
        "roles": ("counselor", "admin"),
    },
    "get_overview": {
        "desc": "查询全校整体情况：总人数、红/黄/绿人数与占比、各班的预警分布与均分。"
                "问「全校有多少人预警」「整体情况怎么样」时用这个。",
        "params": {},
        "required": [],
        "roles": STAFF,
    },
    "search_policy": {
        "desc": "检索学校规章制度原文：降级试读、退学、预警等级划分、通知家长的触发条件、申诉流程、缓考重修等。"
                "凡是问「学校规定」「会不会被退学」「什么情况通知家长」这类制度问题，必须用这个查，不许凭印象回答。",
        "params": {
            "query": {"type": "string", "description": "检索关键词，用制度术语，如「降级试读 学分」「通知家长 条件」"},
        },
        "required": ["query"],
        "roles": ALL_ROLES,
    },
    "get_classroom": {
        "desc": "查询某位任课教师所教课程的课堂情况：课程、学生人数、期中均分、及格率、出勤率、作业提交率、待办事项。"
                "教师问「我这门课怎么样」「我课上谁需要关注」时用这个。",
        "params": {
            "course": {"type": "string", "description": "课程名或课程代码，不填表示该教师全部课程"},
        },
        "required": [],
        "roles": ("teacher",),
    },
}


def specs_for(role: str) -> list[dict]:
    """按角色裁剪出可用的工具清单（OpenAI tools 格式）。"""
    out: list[dict] = []
    self_only = role in SELF_ONLY
    for name, spec in _SPEC.items():
        if role not in spec["roles"]:
            continue
        props = dict(spec["params"])
        required = list(spec["required"])
        if self_only and "name" in props:
            # 学生/家长没有「查别人」这个动作，参数直接不给模型看
            props.pop("name")
            required = [r for r in required if r != "name"]
        out.append({
            "type": "function",
            "function": {
                "name": name,
                "description": spec["desc"],
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            },
        })
    return out


# ---------------------------------------------------------------- 内部工具函数
def _resolve(agent, text: str) -> tuple[dict | None, list[str]]:
    """姓名 → 学生。返回 (命中的学生, 候选名单)。查不到时候选名单给模型兜底。"""
    text = (text or "").strip().strip("「」\"' ")
    if not text:
        return None, []
    if text.isdigit() and len(text) >= 6:
        try:
            return agent.engine.get(text), []
        except KeyError:
            pass
    if text in agent._names:
        return agent._names[text], []
    # 包含匹配：把「戴永康的成绩」也认成「戴永康」
    hits = [s for n, s in agent._names.items() if n in text]
    if len(hits) == 1:
        return hits[0], []
    if len(hits) > 1:
        return None, [s["name"] for s in hits[:5]]
    close = difflib.get_close_matches(text, list(agent._names), n=3, cutoff=0.4)
    return None, close


def _target(agent, role: str, sid: str | None, args: dict) -> tuple[dict | None, dict | None]:
    """确定这次要查谁。返回 (学生, 错误结果)。学生/家长强制锁死为本人。"""
    if role in SELF_ONLY:
        if not sid:
            return None, {"ok": False, "note": "当前会话没有绑定学生身份，无法查询。"}
        try:
            return agent.engine.get(sid), None
        except KeyError:
            return None, {"ok": False, "note": "当前账号没有关联学生档案。"}

    if not (args.get("name") or "").strip():
        return None, {"ok": False, "note": "这次没指定要查哪个学生。先问用户是哪一位（说姓名或学号），再查。"}
    stu, cands = _resolve(agent, args.get("name", ""))
    if not stu:
        if cands:
            return None, {
                "ok": False,
                "note": f"没有找到叫「{args.get('name','')}」的学生。库里最接近的是：{'、'.join(cands)}。"
                        f"请确认是哪一位，或直接问用户全名。不要把别人的数据当成他的。",
            }
        return None, {"ok": False, "note": f"学生库（{len(agent._names)} 人）里没有「{args.get('name','')}」这个姓名，"
                                            f"也没有相近的名字。请直接告诉用户查不到，不要编造。"}
    # 教师只能碰自己课上的人
    if role == "teacher":
        tname = (args.get("__teacher__") or "").strip()
        if tname:
            view = agent.engine.teacher_view(tname)
            allowed = {r["id"] for r in view["students"]}
            if stu["id"] not in allowed:
                return None, {"ok": False, "note": f"{stu['name']} 不在你任教的课程名单里，按权限不能查。"}
    return stu, None


def _mid(c: dict) -> float:
    return float(c.get("midterm") or 0)


def _longest_streak(records: list[dict]) -> int:
    best = cur = 0
    for r in sorted(records, key=lambda x: x.get("date", "")):
        if r.get("status") == "absent":
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


# ---------------------------------------------------------------- 各工具实现
def _t_get_student(agent, role, sid, args):
    stu, err = _target(agent, role, sid, args)
    if err:
        return err
    r = agent.engine.score(stu["id"])
    h = stu["history"]
    cr = stu.get("credits")
    if isinstance(cr, dict):
        credit_txt = (f"已修 {cr.get('earned')} / 在修 {cr.get('in_progress')} / "
                      f"计划 {cr.get('plan')}")
    else:
        credit_txt = str(cr)
    return {"ok": True, "data": {
        "姓名": stu["name"], "学号": stu["id"], "班级": stu["class_name"],
        "专业": stu["major"], "学业导师": stu.get("advisor"),
        "风险分": r["score"], "预警等级": r["level_label"],
        "上学期GPA": h.get("gpa"), "累计挂科学分": h.get("failed_credits"),
        "学分进度": credit_txt,
        "主要失分项": r["factors"][0]["label"] if r["factors"] else "",
    }}


def _t_get_risk(agent, role, sid, args):
    stu, err = _target(agent, role, sid, args)
    if err:
        return err
    r = agent.engine.score(stu["id"])
    raw = r.get("raw") or {}
    return {"ok": True, "data": {
        "姓名": stu["name"], "风险分": r["score"], "等级": r["level_label"],
        "六项因子": [
            {"项": f["label"], "权重": f["weight"], "得分": f["points"],
             "实际值": round(float(f["value"]), 3)}
            for f in r["factors"]
        ],
        "触发硬规则": r.get("overrides") or [],
        "原始指标": {
            "旷课次数": raw.get("absent"), "总课时": raw.get("sessions"),
            "缺勤率": raw.get("absence_ratio"),
            "缺交作业率": raw.get("miss_ratio"),
            "学分加权期中均分": raw.get("mid_avg"),
        },
    }}


def _t_get_attendance(agent, role, sid, args):
    stu, err = _target(agent, role, sid, args)
    if err:
        return err
    courses, total_absent, total_sessions = [], 0, 0
    recent: list[dict] = []
    for c in stu["courses"]:
        recs = c.get("attendance") or []
        absent = sum(1 for r in recs if r.get("status") == "absent")
        late = sum(1 for r in recs if r.get("status") == "late")
        total_absent += absent
        total_sessions += len(recs)
        if absent or late:
            courses.append({
                "课": c["name"], "旷课": absent, "迟到": late,
                "课时": len(recs), "最长连续旷课": _longest_streak(recs),
            })
        for r in recs:
            if r.get("status") == "absent":
                recent.append({"日期": r.get("date"), "课": c["name"],
                               "节次": r.get("period"), "备注": r.get("note", "")})
    recent.sort(key=lambda x: x.get("日期") or "", reverse=True)
    return {"ok": True, "data": {
        "姓名": stu["name"],
        "总旷课次数": total_absent,
        "总课时": total_sessions,
        "出勤率": round(1 - total_absent / total_sessions, 3) if total_sessions else None,
        "各课分布": courses,
        "最近旷课记录": recent[:MAX_RECORDS],
        "还有更多记录": max(0, len(recent) - MAX_RECORDS),
    }}


def _t_get_homework(agent, role, sid, args):
    stu, err = _target(agent, role, sid, args)
    if err:
        return err
    rows, missed = [], []
    for c in stu["courses"]:
        hw = c.get("homework") or []
        if not hw:
            continue
        done = sum(1 for h in hw if h.get("status") == "submitted")
        rows.append({"课": c["name"], "应交": len(hw), "已交": done,
                     "提交率": round(done / len(hw), 3)})
        for h in hw:
            if h.get("status") != "submitted":
                missed.append({"课": c["name"], "作业": h.get("title"),
                               "截止": h.get("due"), "状态": h.get("status")})
    return {"ok": True, "data": {
        "姓名": stu["name"],
        "各课提交情况": rows,
        "未交清单": missed[:MAX_ROWS],
        "未交总数": len(missed),
    }}


def _t_get_courses(agent, role, sid, args):
    stu, err = _target(agent, role, sid, args)
    if err:
        return err
    from . import checkin as checkin_mod

    out = []
    for c in stu["courses"]:
        tp = c.get("teacher_profile") or {}
        # 上课时间与教室一起给：以前这里只有课名和老师，学生问「明天有没有课」
        # 模型拿到的是"没有上课时间"，只能答查不到。数据本来就在课表里。
        slots = c.get("slots") or []
        when = "、".join(f"{_WEEKDAY_LABEL[w]} {p}" for w, p in slots) or c.get("period")
        out.append({
            "课程": c["name"], "代码": c.get("code"), "学分": c.get("credit"),
            "教师": c.get("teacher"), "职称": tp.get("title"),
            "上课时间": when,
            "教室": checkin_mod.ROOMS.get(c.get("code"), ""),
            "办公室": tp.get("office"), "邮箱": tp.get("email"),
            "答疑": tp.get("office_hour"),
        })
    return {"ok": True, "data": {
        "姓名": stu["name"], "在修课程": out,
        "说明": "要查具体某天有没有课、第几节上哪门，用 get_timetable 更准（含日期与节次）。",
    }}


# ---------------------------------------------------------------- 课表
# 「明天有没有课」这类问题以前答不出来，是因为所有工具里都没有节次和教室：
# 课表页的数据在 engine/checkin.py（由 COURSES[].slots 现算），一直没接进来。
_CN_WEEKDAY = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
_WEEKDAY_LABEL = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _window(when: str, today, week: int) -> tuple[str, str, str, str]:
    """把「明天 / 本周 / 周三 / 第 8 周」解析成日期区间。

    返回 (标签, 起始日, 结束日, 口径说明)；标签为 next 表示问的是「下一节课」。
    """
    import re
    from datetime import timedelta

    from .data import WEEK1_MONDAY

    when = (when or "").strip()

    def monday_of(w: int):
        return WEEK1_MONDAY + timedelta(weeks=max(1, w) - 1)

    def rng(label: str, d0, d1, note: str = ""):
        return label, d0.isoformat(), d1.isoformat(), note

    def week_rng(label: str, w: int):
        m = monday_of(w)
        return rng(label, m, m + timedelta(days=6), f"第 {w} 教学周")

    if any(k in when for k in ("下一节", "下节课", "最近一节课", "接下来的课")):
        return "next", today.isoformat(), today.isoformat(), "从今天起最近的一节课"
    m = re.search(r"第\s*(\d{1,2})\s*周", when)
    if m:
        return week_rng(f"第{m.group(1)}周", int(m.group(1)))
    if "下周" in when:
        return week_rng("下周", week + 1)
    if "上周" in when:
        return week_rng("上周", week - 1)
    if "今天" in when or "今日" in when:
        return rng("今天", today, today)
    if "明天" in when:
        d = today + timedelta(days=1)
        return rng("明天", d, d)
    if "后天" in when:
        d = today + timedelta(days=2)
        return rng("后天", d, d)
    if "昨天" in when:
        d = today - timedelta(days=1)
        return rng("昨天", d, d)
    if any(k in when for k in ("本周", "这周", "这星期", "这个星期", "全周", "课表", "一周")):
        return week_rng("本周", week)
    # 「周三 / 星期三 / 礼拜三」：定位到本周那一天
    m = re.search(r"(?:周|星期|礼拜)([一二三四五六日天])", when)
    if m:
        idx = _CN_WEEKDAY[m.group(1)]
        monday = monday_of(week)
        d = monday + timedelta(days=idx)
        return rng(_WEEKDAY_LABEL[idx], d, d, f"本周第 {week} 周")
    return week_rng("本周", week)


def _day_label(iso: str) -> str:
    from datetime import date
    d = date.fromisoformat(iso)
    return f"{iso[5:]} {_WEEKDAY_LABEL[d.weekday()]}" if d.weekday() < 7 else iso[5:]


def _session_rows(stu: dict, want_course: str) -> list[dict]:
    """这名学生自己的全部课表条目（按时间排）。课表页用的是同一份 calendar()。"""
    from . import checkin as checkin_mod
    mine = {c["code"] for c in stu.get("courses") or []}
    mine |= {c["code"] for c in stu.get("extra_courses") or []}
    rows: list[dict] = []
    for code, sessions in checkin_mod.calendar().items():
        if mine and code not in mine:
            continue
        rows.extend(sessions)
    if want_course:
        rows = [r for r in rows
                if want_course in (r.get("name") or "")
                or want_course.upper() == (r.get("course") or "").upper()]
    rows.sort(key=lambda r: (r["date"], checkin_mod.period_order(r["period"])))
    return rows


def _t_get_timetable(agent, role, sid, args):
    """课表查询：日期 + 节次 + 教室 + 教师，和「我的课表」页面同源。"""
    from .data import TODAY, db as _db

    meta = _db()
    week = int(meta.get("week") or 1)
    when = (args.get("when") or "").strip()
    want = (args.get("course") or "").strip()

    tname = (args.get("__teacher__") or "").strip()
    if role == "teacher" and not (args.get("name") or "").strip() and tname:
        # 教师问「我明天有课吗」：指的是自己教的那几门课
        codes = {c["code"] for c in agent.engine.teacher_view(tname)["courses"]}
        rows = [r for r in _session_rows({"courses": [], "extra_courses": []}, "")
                if r["course"] in codes]
        who = f"{tname}老师"
        if want:
            rows = [r for r in rows
                    if want in (r.get("name") or "") or want.upper() == (r.get("course") or "").upper()]
            if not rows:
                return {"ok": False, "note": f"你名下没有「{want}」这门课。"}
    else:
        stu, err = _target(agent, role, sid, args)
        if err:
            return err
        rows = _session_rows(stu, want)
        who = stu["name"]
        if want and not rows:
            names = "、".join(sorted({c["name"] for c in stu.get("courses") or []}))
            return {"ok": False, "note": f"{stu['name']} 这学期没有「{want}」这门课。在修的是：{names}。"}

    label, start, end, note = _window(when, TODAY, week)
    if label == "next":
        future = [r for r in rows if r["date"] > TODAY.isoformat()]
        picked = future[:1]
    else:
        picked = [r for r in rows if start <= r["date"] <= end]

    total = len(rows)
    held = sum(1 for r in picked if r["held"])
    items = [{
        "日期": _day_label(r["date"]),
        "节次": r["period"],
        "课程": r["name"],
        "教师": r["teacher"],
        "教室": r.get("room") or "未排教室",
        "状态": "已上过" if r["held"] else "还没上",
    } for r in picked[:12]]

    # 空档期必须说清「这几天没课」，并给出下一次有课的时间，别只回一个空列表
    upcoming = [r for r in rows if r["date"] > TODAY.isoformat()]
    data = {
        "姓名": who,
        "查询范围": ("下一节课" if label == "next" else label) + (f"（{note}）" if note else ""),
        "范围起止": f"{start} ~ {end}",
        "今天": f"{_day_label(TODAY.isoformat())}（第 {week} 教学周）",
        "本学期总课次": total,
        "范围内的课": items,
        "范围内课次": len(picked),
        "其中已上过": held,
    }
    if not items:
        if upcoming:
            nxt = upcoming[0]
            data["说明"] = (f"{label}没有排课。下一次有课是 {_day_label(nxt['date'])} "
                            f"{nxt['period']}《{nxt['name']}》，教室 {nxt.get('room') or '未排'}，"
                            f"{nxt['teacher']}老师。")
        else:
            data["说明"] = f"{label}没有排课，本学期课表也全部上完了。"
    else:
        data["说明"] = "同一天多节课按节次排序；教室与教师来自教务排课，和「我的课表」页面一致。"
    return {"ok": True, "data": data}


# ---------------------------------------------------------------- 期末试算
def _need_final(course: dict, target: float) -> float | None:
    """想拿到 target 总评，期末卷面要考多少。考满 100 也拿不到时返回 None。"""
    w = {x["key"]: float(x["weight"]) for x in course["components"]}
    s = {x["key"]: float(x["base"]) for x in course["components"]}
    wf = w.get("final", 0.0)
    if wf <= 0:
        return None
    tw = sum(w.values()) or 100.0
    rest = sum(s.get(k, 0.0) * v for k, v in w.items() if k != "final")
    need = (target * tw - rest) / wf
    return round(max(0.0, min(100.0, need)), 1) if need <= 100 else None


def _t_get_final_forecast(agent, role, sid, args):
    """成绩构成 + 期末要考多少。页面「成绩分配试算」用的是同一套 simulator。"""
    stu, err = _target(agent, role, sid, args)
    if err:
        return err
    from . import simulator as sim

    risk = agent.engine.score(stu["id"])
    pay = sim.payload(stu, risk, stu.get("term"))
    want = (args.get("course") or "").strip()
    try:
        target = float(args["target"]) if args.get("target") not in (None, "") else None
    except (TypeError, ValueError):
        target = None
    target = max(0.0, min(100.0, target)) if target is not None else None

    courses = pay["courses"]
    if want:
        courses = [c for c in courses
                   if want in c["name"] or want.upper() in (c["code"] or "").upper()]
        if not courses:
            return {"ok": False,
                    "note": f"没有「{want}」这门课。在修的是："
                            f"{'、'.join(c['name'] for c in pay['courses'])}。"}

    out = []
    for c in courses:
        need = c["needed_final"] if target is None else _need_final(c, target)
        item = {
            "课程": c["name"], "学分": c["credit"],
            "考核方案": c.get("scheme_label"),
            "当前总评": c["base_total"],
            "期末占比": f"{next((x['weight'] for x in c['components'] if x['key'] == 'final'), 0)}%",
            "各项": [{"项": x["short"], "权重": f"{x['weight']:g}%", "当前": x["base"]}
                     for x in c["components"]],
        }
        if target is None:
            if c["needed_final"] <= 45:
                item["及格所需期末"] = ("期末卷面考到 45 分就稳过（校规要求卷面至少 45 分，"
                                        "按这个下限算）")
            else:
                item["及格所需期末"] = f"期末卷面至少要考 {c['needed_final']} 分才不挂科"
        else:
            if need is None:
                item["目标所需期末"] = f"想拿 {target:g} 分，期末考满 100 分也不够"
            else:
                item["目标所需期末"] = f"想拿 {target:g} 分，期末要考 {need} 分"
        fp = c.get("fail_probability")
        if isinstance(fp, (int, float)):
            item["挂科风险"] = f"{round(fp * 100)}%"   # 来自 risk.py 的 fail_probability
        out.append(item)

    # 危险度排序：及格所需期末分越高越危险
    risky = sorted([c for c in courses], key=lambda x: -x["needed_final"])
    head = f"{stu['name']}的本学期成绩构成（及格线 {pay['pass_line']:g} 分，期末卷面另需过 45 分）："
    data = {
        "姓名": stu["name"],
        "口径": "各项起点分来自真实数据：随堂测=四次均值，期中=期中卷面，平时=出勤折算，作业=提交率折算；"
                "期末还没考，按期中与测评趋势估一个参考值，仅作试算，以任课教师最终方案为准。",
        "结论": head,
        "课程": out,
        "总评": pay.get("base"),
    }
    if risky and len(risky) > 1:
        worst = risky[0]
        data["最需要补的一门"] = (f"{worst['name']}：期末至少要考 {worst['needed_final']} 分才不挂科，"
                                  f"当前总评 {worst['base_total']} 分")
    if target is not None:
        data["目标总评"] = target
    return {"ok": True, "data": data}


# ---------------------------------------------------------------- 通知 / 待办
def _t_get_todos(agent, role, sid, args):
    """本账号的未读通知与未完成待办。页面的铃铛和待办列表就是这份数据。"""
    from .notifications import NOTIFS, TODOS

    p = args.get("__profile__") or {}
    account = (p.get("account") or "").strip() or (sid or "")
    if not account:
        return {"ok": False, "note": "当前会话没有账号信息，查不到待办。"}
    unread = NOTIFS.unread(role, account)
    todos = [t for t in TODOS.items(role, account) if not t.get("done")]
    if not unread and not todos:
        return {"ok": True, "data": {"账号": account, "未读通知": 0, "未完成待办": 0,
                                     "说明": "当前没有未读通知，也没有未完成待办。"}}
    return {"ok": True, "data": {
        "账号": account,
        "未读通知": len(unread),
        "未完成待办": len(todos),
        "通知": [{"标题": n.get("title"), "内容": n.get("text"), "时间": n.get("ts")}
                 for n in unread[:6]],
        "待办": [{"事项": t.get("title"), "说明": t.get("detail")} for t in todos[:6]],
        "说明": "这是当前账号自己名下的通知与待办，其他账号看不到。",
    }}


# ---------------------------------------------------------------- 文书正文
def _t_get_letter(agent, role, sid, args):
    """告知函 / 家长信 / 辅导员简报的正文要点。原来只能在页面上下载，问内容就答不上。"""
    stu, err = _target(agent, role, sid, args)
    if err:
        return err
    kind = (args.get("kind") or "").strip()
    if role in SELF_ONLY:
        kind = "parent" if role == "parent" else "student"
    if kind not in ("student", "parent", "counselor"):
        kind = "student"
    from . import letters as letters_mod

    school = None
    try:
        doc = (letters_mod.parent_letter(agent.engine, agent.kb, stu["id"], school)
               if kind == "parent" else
               letters_mod.counselor_brief(agent.engine, agent.kb, stu["id"], school)
               if kind == "counselor" else
               letters_mod.student_letter(agent.engine, agent.kb, stu["id"], school))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "note": f"生成{kind}文书失败：{type(e).__name__}: {e}"}
    body = (doc.get("body") or "").strip()
    if len(body) > 1500:
        body = body[:1500] + "\n…（正文较长，已截断，完整版可在页面导出 Word）"
    return {"ok": True, "data": {
        "姓名": stu["name"],
        "文书": doc.get("title"),
        "标题": doc.get("subject"),
        "正文": body,
        "要点": doc.get("meta") or {},
        "说明": "这是系统按当前真实数据生成的文书正文，可逐条念给用户；要文件用导出。",
    }}


# ---------------------------------------------------------------- 培养方案
def _t_get_curriculum(agent, role, sid, args):
    """培养方案与课程档案：学分、性质、周次节次、教室，加学生自己的学分进度。"""
    from .curriculum import CURRICULUM
    from .data import db as _db

    payload = CURRICULUM.payload(_db())
    rows = [{
        "课程": c["name"], "代码": c.get("code"), "学分": c.get("credit"),
        "性质": c.get("kind"), "教师": c.get("teacher"),
        "周次": f"第 1-{c.get('weeks', 16)} 周" if c.get("weeks") else "全学期",
        "上课节次": c.get("period"),
    } for c in payload["courses"]]
    data = {
        "本学期开设课程": rows,
        "课程总学分": sum(c.get("credit") or 0 for c in payload["courses"]),
        "说明": "培养方案的学分要求、课程性质以教务系统为准，本页与「培养方案」页同源。",
    }
    # 学生自己的进度：不传姓名（教师/教务泛问）时就不给，避免张冠李戴
    name = (args.get("name") or "").strip()
    if name or role in SELF_ONLY:
        stu, err = _target(agent, role, sid, args)
        if not err:
            cr = stu.get("credits")
            if isinstance(cr, dict):
                data["学分进度"] = (f"培养方案要求 {cr.get('plan_total')} 学分，"
                                    f"已修 {cr.get('earned')}，本学期在读 {cr.get('in_progress')}，"
                                    f"还差 {round(float(cr.get('plan_total') or 0) - float(cr.get('earned') or 0), 1)} 学分")
                data["姓名"] = stu["name"]
    return {"ok": True, "data": data}


# ---------------------------------------------------------------- 干预台账
def _t_get_interventions(agent, role, sid, args):
    """已经记过哪些谈话与帮扶动作。学生/家长只看本人的部分结论。"""
    stu, err = _target(agent, role, sid, args)
    if err:
        return err
    store = getattr(agent, "store", None) or {}
    rows = store.get(stu["id"]) or []          # app.py 里的 INTERVENTIONS 就是一个 dict
    plan = agent.engine.interventions(stu["id"])[:3]
    if role in SELF_ONLY:
        # 台账里的 internal 备注是辅导员内部记录，不外发
        out = [{"时间": r.get("ts") or r.get("time"), "事项": r.get("title"),
                "状态": r.get("status")} for r in rows[:5]]
        return {"ok": True, "data": {
            "姓名": stu["name"], "已记录": len(rows), "记录": out,
            "下一步建议": [a["title"] for a in plan],
            "说明": "只能看到本人被记录过的事项标题，内部备注不对外提供。",
        }}
    return {"ok": True, "data": {
        "姓名": stu["name"],
        "已记录": len(rows),
        "记录": [{"时间": r.get("ts") or r.get("time"), "事项": r.get("title"),
                  "结论": r.get("note"), "状态": r.get("status")} for r in rows[:6]],
        "下一步建议": [{"事项": a["title"], "内容": a["detail"], "时限": a.get("deadline")} for a in plan],
        "说明": "台账只记录已经发生的动作；建议项来自规则库，尚未执行。",
    }}


# ---------------------------------------------------------------- 班级简报
def _t_get_class_report(agent, role, sid, args):
    """班级学情简报：辅导员页面上「班级报告」那一份，正文按班级现场聚合。"""
    from . import letters as letters_mod
    from . import scores as scores_mod

    cls = (args.get("class_name") or "").strip()
    if not cls:
        return {"ok": False, "note": "没说哪个班。现有班级是："
                                     f"{'、'.join(sorted({s['class_name'] for s in agent.engine.students}))}。"}
    hit, cands = scores_mod.class_name_of(agent.engine, cls)
    if not hit:
        return {"ok": False, "note": f"没有叫「{cls}」的班级。现有班级是：{'、'.join(cands)}。"}
    if role == "teacher":
        tname = (args.get("__teacher__") or "").strip()
        mine = {s["class_name"] for s in agent.engine.students
                if any(c.get("teacher") == tname for c in s.get("courses") or [])}
        if hit not in mine:
            return {"ok": False, "note": f"{hit} 不在你任教的班里（你带的是 "
                                         f"{'、'.join(sorted(mine))}），按权限看不到。可以问你自己班上的情况。"}
    rep = letters_mod.class_report(agent.engine, hit)
    body = (rep.get("body") or "").strip()
    return {"ok": True, "data": {
        "班级": hit,
        "简报": body[:1500],
        "要点": rep.get("meta") or {},
        "说明": "这份简报和「班级报告」页面同一份数据，数字可直接转述。",
    }}


# ---------------------------------------------------------------- 异议
_APPEAL_STATUS = {"pending": "待处理", "accepted": "已受理", "rejected": "未支持"}


def _t_get_appeals(agent, role, sid, args):
    """异议处理进度。学生只看自己的，辅导员看全部待处理。"""
    from .notifications import APPEALS

    if role in SELF_ONLY:
        if not sid:
            return {"ok": False, "note": "当前会话没有绑定学生身份，查不到异议。"}
        rows = APPEALS.by_student(sid)
        if not rows:
            return {"ok": True, "data": {"异议": 0,
                                         "说明": "这位学生还没有提过异议。遇到考勤或作业记录有误，"
                                                 "可以在学业明细里点「有异议」提交说明。"}}
        return {"ok": True, "data": {
            "异议": len(rows),
            "明细": [{"课程": r.get("course"), "类型": "考勤" if r.get("kind") == "attendance" else "作业",
                      "理由": r.get("reason"), "状态": _APPEAL_STATUS.get(r.get("status"), r.get("status")),
                      "答复": r.get("reply") or "还没答复", "提交时间": r.get("ts")}
                     for r in rows[:5]],
            "说明": "状态为「待处理」的，辅导员那边还没裁定。",
        }}

    rows = APPEALS.all()
    want = (args.get("name") or "").strip()
    if want:
        stu = _resolve(agent, want)[0]
        if not stu:
            return {"ok": False, "note": f"没有找到叫「{want}」的学生。"}
        rows = [r for r in rows if str(r.get("sid")) == str(stu["id"])]
    pending = [r for r in rows if r.get("status") == "pending"]
    if not rows:
        return {"ok": True, "data": {
            "异议总数": 0, "待处理": 0,
            "说明": f"{want or '全校'}目前没有异议记录——既没有待处理的，也没有处理过的。",
        }}
    return {"ok": True, "data": {
        "异议总数": len(rows), "待处理": len(pending),
        "明细": [{"学生": r.get("name"), "班级": r.get("class_name"), "课程": r.get("course"),
                  "类型": "考勤" if r.get("kind") == "attendance" else "作业",
                  "理由": r.get("reason"),
                  "状态": _APPEAL_STATUS.get(r.get("status"), r.get("status"))}
                 for r in rows[:8]],
        "说明": "只列最近 8 条；裁定后会自动回执给学生并关闭对应待办。",
    }}


# ---------------------------------------------------------------- 家校消息
def _t_get_messages(agent, role, sid, args):
    """家校消息往来。家长看自己那条线，辅导员按学生看。"""
    from .notifications import MESSAGES

    p = args.get("__profile__") or {}
    account = (p.get("account") or "").strip() or (sid or "")
    if not MESSAGES or not account:
        return {"ok": False, "note": "当前账号没有家校消息通道（只有家长端与辅导员端有）。"}
    if role == "parent":
        threads = MESSAGES.threads_for("parent", account)
        thread = threads[0] if threads else {}
        msgs = thread.get("messages") or []
        if not msgs:
            return {"ok": True, "data": {"消息数": 0,
                                         "说明": f"还没有和辅导员的往来消息。辅导员电话 {thread.get('peer_phone', '')}，"
                                                 "需要沟通可以直接在家长端发。",
                                         "对方": thread.get("peer_name") or "辅导员"}}
        return {"ok": True, "data": {
            "对方": thread.get("peer_name") or "辅导员",
            "消息数": len(msgs),
            "未读": thread.get("unread"),
            "最近消息": [{"方向": "我发出" if m.get("from_role") == "parent" else "辅导员发来",
                          "内容": m.get("text"), "时间": m.get("ts")} for m in msgs[-6:]],
        }}

    students = [{"id": s["id"], "name": s["name"], "class_name": s.get("class_name", ""),
                 "advisor": s.get("advisor", ""), "level": agent.engine.score(s["id"])["level"],
                 "score": agent.engine.score(s["id"])["score"]}
                for s in agent.engine.students]
    want = (args.get("name") or "").strip()
    if want:
        stu, cands = _resolve(agent, want)
        if not stu:
            return {"ok": False, "note": f"没有找到叫「{want}」的学生。库里最接近的是：{'、'.join(cands) or '无'}。"}
        threads = MESSAGES.threads_for("counselor", account, students=students)
        thread = next((t for t in threads if str(t.get("sid")) == str(stu["id"])), None)
        msgs = (thread or {}).get("messages") or []
        if not msgs:
            return {"ok": True, "data": {"学生": stu["name"], "消息数": 0,
                                         "说明": f"和 {stu['name']} 的家长还没有往来消息，"
                                                 f"家长电话 {thread.get('peer_phone', '') if thread else ''}。"}}
        return {"ok": True, "data": {
            "学生": stu["name"], "对方": thread.get("peer_name"),
            "消息数": len(msgs), "未读": thread.get("unread"),
            "最近消息": [{"方向": "辅导员发出" if m.get("from_role") == "counselor" else "家长发来",
                          "内容": m.get("text"), "时间": m.get("ts")} for m in msgs[-6:]],
        }}

    threads = MESSAGES.threads_for("counselor", account, students=students)
    active = [t for t in threads if t.get("messages")]
    return {"ok": True, "data": {
        "会话数": len(active),
        "未读": MESSAGES.unread_count("counselor", account),
        "最近会话": [{"学生": t.get("peer_name"), "最后一条": t.get("last_text"),
                      "时间": t.get("last_ts"), "未读": t.get("unread")} for t in active[:6]],
        "说明": "家长会话按风险优先排列；没发过消息的家长不在这个列表里。",
    }}


def _t_get_scores(agent, role, sid, args):
    """一名学生的成绩全景。原来没有任何工具能拿到分数，模型只能答「系统没显示」。"""
    stu, err = _target(agent, role, sid, args)
    if err:
        return err
    from . import scores as scores_mod
    return {"ok": True, "data": scores_mod.student_scores(agent.engine, stu)}


def _t_get_class_scores(agent, role, sid, args):
    """班级成绩排名。学生/家长降级为「只看自己名次」，这是权限设计不是缺陷。"""
    from . import scores as scores_mod
    course = (args.get("course") or "").strip() or None

    if role in SELF_ONLY:
        if not sid:
            return {"ok": False, "note": "当前会话没有绑定学生身份，无法查询。"}
        try:
            stu = agent.engine.get(sid)
        except KeyError:
            return {"ok": False, "note": "当前账号没有关联学生档案。"}
        return {"ok": True, "data": scores_mod.my_rank_only(agent.engine, stu, course)}

    engine = agent.engine
    cls = (args.get("class_name") or "").strip() or None
    if cls:
        hit, cands = scores_mod.class_name_of(engine, cls)
        if not hit:
            return {"ok": False, "note": f"没有叫「{cls}」的班级。现有班级是：{'、'.join(cands)}。"
                                         f"请确认是哪一个（或直接问用户是哪个班），不要默认成别的班。"}
        cls = hit
    elif role == "teacher":
        tname = (args.get("__teacher__") or "").strip()
        mine = {s["class_name"] for s in engine.students
                if any(c.get("teacher") == tname for c in s.get("courses") or [])}
        if len(mine) == 1:
            cls = next(iter(mine))

    if role == "teacher":
        tname = (args.get("__teacher__") or "").strip()
        mine = {s["class_name"] for s in engine.students
                if any(c.get("teacher") == tname for c in s.get("courses") or [])}
        if cls and cls not in mine:
            return {"ok": False, "note": f"{cls} 不在你任教的班里（你带的是 {'、'.join(sorted(mine))}），"
                                         f"按权限看不到。可以问你自己班上的成绩。"}

    if cls:
        return {"ok": True, "data": scores_mod.class_scores(engine, cls, course)}

    # 没指定班级：给「每班一条」的横向对比，比拉 240 人长名单有用
    classes = sorted({s["class_name"] for s in engine.students})
    if role == "teacher":
        tname = (args.get("__teacher__") or "").strip()
        classes = [c for c in classes
                   if any(s.get("class_name") == c and any(x.get("teacher") == tname for x in s.get("courses") or [])
                          for s in engine.students)]
    rows = []
    for c in classes:
        one = scores_mod.class_scores(engine, c, course, top_n=1)
        top = (one.get("前几名") or [{}])[0]
        rows.append({"班级": c, "班均": one.get("班均"), "人数": one.get("总人数"),
                     "第一": top.get("姓名"), "最高分": top.get("分数")})
    rows.sort(key=lambda x: -(x.get("班均") or 0))
    return {"ok": True, "data": {
        "口径": f"{course}期中卷面" if course else "学分加权期中均分",
        "各班对比": rows,
        "说明": "按班均从高到低排。要某个班的完整名单，请带上班级名再问一次。",
    }}


def _t_get_learning_track(agent, role, sid, args):
    """课后自评 → 学习轨迹。数据来自学生自己每节课后的记录，不进风险分。"""
    stu, err = _target(agent, role, sid, args)
    if err:
        return err
    store = getattr(agent, "checkins", None)
    if store is None:
        return {"ok": False, "note": "课后自评记录还没接入，查不到学习轨迹。"}

    from . import checkin as checkin_mod
    from .data import db as _db

    meta = _db()
    rows = store.rows(stu["id"])
    t = checkin_mod.track(stu["id"], rows, {"week": meta.get("week", 8), "term": meta.get("term", "")})
    if not t["stats"]["recorded"]:
        return {"ok": True, "data": {
            "姓名": stu["name"], "记录条数": 0,
            "说明": "这位学生还没做过课后自评，学习轨迹是空的。让他下课后在「我的课表」里点一节已经上过的课记一句就行。",
        }}

    label = {"break": "有断点还没接上", "watch": "零星几节没跟上", "ok": "跟得上", "empty": "没记录"}
    courses = []
    for c in t["courses"]:
        if not c["recorded"]:
            continue
        courses.append({
            "课": c["name"],
            "记录": f"{c['recorded']}/{c['held']} 节",
            "状态": label.get(c["status"], c["status"]),
            "判断": c["line"],
            "断点": [
                {
                    "起始周": b["start_week"], "起始日期": b["start_date"],
                    "连续节数": b["count"],
                    "从什么时候开始": "上课一开始" if b["minute_from"] <= 0 else f"第 {b['minute_from']} 分钟",
                    "卡在": b["point"] or "未填",
                    "是否接上": "还没接上" if b["open"] else f"第 {b['recovered_week']} 周接上了",
                }
                for b in c["breaks"][:2]
            ],
        })
    return {"ok": True, "data": {
        "姓名": stu["name"],
        "记录条数": t["stats"]["recorded"],
        "覆盖率": f"{round(t['stats']['coverage'] * 100)}%",
        "未接上的断点": t["stats"]["open_breaks"],
        "已接上的断点": t["stats"]["fixed_breaks"],
        "本周记录": f"{t['stats']['week_done']}/{t['stats']['week_due']} 节",
        "各课轨迹": courses[:MAX_ROWS],
        "可以做的事": [a["title"] for a in t["advice"]][:4],
        "口径": "以上都是学生课后的自评，只用于看趋势，不参与风险分，也不作为处分依据。",
    }}


def _t_get_roster(agent, role, sid, args):
    level = (args.get("level") or "").strip() or None
    cls = (args.get("class_name") or "").strip() or None
    if level and level not in ("red", "yellow", "green"):
        level = None
    if role == "teacher":
        return {"ok": False, "note": "教师端不提供跨班名单，请用 get_classroom 查你自己课上的学生。"}
    # 班级名对不上时给候选，别返回一个「0 人」让模型去猜
    mapped = ""
    if cls:
        from . import scores as scores_mod
        hit, cands = scores_mod.class_name_of(agent.engine, cls)
        if not hit:
            return {"ok": False, "note": f"没有叫「{cls}」的班级，风险名单查不到这个班。"
                                         f"现有班级是：{'、'.join(cands)}。请确认是哪一个，"
                                         f"不要用「0 人」来回答——是班级名对不上，不是班里没人。"}
        if hit != cls:
            mapped = f"（「{cls}」按 {hit} 处理）"
        cls = hit
    rows = agent.engine.roster(cls, level)
    brief = [{
        "姓名": r["name"], "班级": r["class_name"], "风险分": r["score"],
        "等级": r["level_label"], "主因": r.get("top_factor"),
        "旷课": r.get("absent"), "缺交作业": r.get("missed_hw"),
    } for r in rows[:MAX_ROWS]]
    return {"ok": True, "data": {
        "筛选": {"班级": (cls or "全部") + mapped, "等级": level or "全部"},
        "总人数": len(rows),
        "前几名": brief,
        "说明": f"按风险分从高到低排，只列前 {len(brief)} 人" if len(rows) > MAX_ROWS else "已全部列出",
    }}


def _t_get_overview(agent, role, sid, args):
    ov = agent.engine.overview()
    data = {
        "总人数": ov.get("total"),
        "红色预警": ov["dist"].get("red"), "黄色预警": ov["dist"].get("yellow"),
        "正常": ov["dist"].get("green"),
        "各等级占比": ov.get("dist_pct"),
    }
    # 教师只给全校总量，不给逐班分布——那是辅导员和教务的视野
    if role != "teacher":
        data["各班分布"] = {k: {"人数": v["total"], "红": v["red"], "黄": v["yellow"]}
                            for k, v in list((ov.get("by_class") or {}).items())[:12]}
    return {"ok": True, "data": data}


def _t_search_policy(agent, role, sid, args):
    q = (args.get("query") or "").strip()
    if not q:
        return {"ok": False, "note": "检索词为空，请给出制度关键词，例如「降级试读 学分」。"}
    hits = agent.kb.search(q, top_k=4, school=None, min_score=0.25)
    if not hits:
        return {"ok": False, "note": f"知识库里没有检索到「{q}」相关条款。请如实告诉用户没有对应规定，"
                                     f"建议咨询教务，不要凭印象编条款。"}
    meta = agent.kb.meta()
    return {"ok": True, "data": {
        "检索词": q,
        "改写后检索词": meta.get("rewritten") or "",
        "检索通道": meta.get("channel") or "",
        "条款": [{
            "出处": h.get("citation"),
            "学校": h.get("school"),
            "相关度": h.get("score_pct"),
            "命中原因": h.get("why"),
            "原文": (h.get("text") or "")[:400],
        } for h in hits[:3]],
        "说明": "回答时必须注明出自哪一条（用 [1][2] 序号对应上表顺序），不要改写条款里的数字。",
    }}


def _t_get_classroom(agent, role, sid, args):
    from . import classroom
    tname = (args.get("__teacher__") or "").strip()
    if not tname:
        return {"ok": False, "note": "当前会话没有识别到教师身份。"}
    want = (args.get("course") or "").strip()
    rep = classroom.report(agent.engine, tname)
    courses = rep.get("courses") or []
    if want:
        courses = [c for c in courses
                   if want in (c.get("name") or "") or want.upper() in (c.get("code") or "").upper()]
        if not courses:
            return {"ok": False, "note": f"你名下没有「{want}」这门课。你教的是："
                                         f"{'、'.join(c['name'] for c in rep.get('courses') or [])}"}
    out = []
    for c in courses:
        gap = c.get("gap_grade") or 0
        # 只给 "+4.2" 这种裸数字，模型有一次把「高于年级 4.2」读成了「低于年级 4.2」。
        # 方向性的话必须由工具说死，模型只负责转述。
        if gap > 0:
            vs = f"高于年级平均 {gap} 分"
        elif gap < 0:
            vs = f"低于年级平均 {abs(gap)} 分"
        else:
            vs = "与年级平均持平"
        item = {
            "课程": c["name"], "代码": c.get("code"), "人数": c.get("students"),
            "期中均分": c.get("mid_avg"), "与年级平均相比": vs,
            "及格率": c.get("pass_rate"),
            "出勤率": (c.get("attend") or {}).get("rate"),
            "作业提交率": (c.get("hw") or {}).get("rate"),
        }
        # 分班对比：老师最常问「哪个班最弱」，这里直接把最弱/最强两个班点出来
        classes = c.get("classes") or []
        if classes:
            ranked = sorted(classes, key=lambda x: x.get("mid_avg") or 0)
            item["分班均分"] = {x.get("class_name"): x.get("mid_avg") for x in classes}
            item["最弱班"] = f"{ranked[0].get('class_name')}（{ranked[0].get('mid_avg')} 分，" \
                             f"红色预警 {ranked[0].get('red', 0)} 人）"
            item["最强班"] = f"{ranked[-1].get('class_name')}（{ranked[-1].get('mid_avg')} 分）"
            item["红色预警人数"] = sum(x.get("red") or 0 for x in classes)
        out.append(item)
    return {"ok": True, "data": {
        "教师": tname,
        "课程": out,
        "本周待办": [{"类型": t.get("kind"), "说明": t.get("text")}
                     for t in (rep.get("todos") or [])[:6]],
        "最需关注的学生": [{"姓名": s["name"], "班级": s.get("class_name"),
                            "风险分": s.get("score"), "等级": s.get("level_label")}
                           for s in (rep.get("students") or [])[:5]],
    }}


_HANDLERS = {
    "get_student": _t_get_student,
    "get_risk": _t_get_risk,
    "get_attendance": _t_get_attendance,
    "get_homework": _t_get_homework,
    "get_learning_track": _t_get_learning_track,
    "get_courses": _t_get_courses,
    "get_timetable": _t_get_timetable,
    "get_final_forecast": _t_get_final_forecast,
    "get_todos": _t_get_todos,
    "get_letter": _t_get_letter,
    "get_curriculum": _t_get_curriculum,
    "get_interventions": _t_get_interventions,
    "get_class_report": _t_get_class_report,
    "get_messages": _t_get_messages,
    "get_appeals": _t_get_appeals,
    "get_scores": _t_get_scores,
    "get_class_scores": _t_get_class_scores,
    "get_roster": _t_get_roster,
    "get_overview": _t_get_overview,
    "search_policy": _t_search_policy,
    "get_classroom": _t_get_classroom,
}


def run(agent, role: str, sid: str | None, name: str, args: dict,
        teacher_name: str = "", profile: dict | None = None) -> dict:
    """执行一个工具。任何异常都收敛成 ok=False，绝不把堆栈抛给模型。"""
    fn = _HANDLERS.get(name)
    if not fn:
        return {"ok": False, "note": f"没有名为 {name} 的工具，可用的是：{'、'.join(_HANDLERS)}"}
    safe = dict(args or {})
    safe["__teacher__"] = teacher_name
    # 通知与待办按账号取数，身份由服务端注入，不让模型传
    safe["__profile__"] = profile or {}
    try:
        return fn(agent, role, sid, safe)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "note": f"工具 {name} 执行出错：{type(e).__name__}: {e}"}


def render(result: dict) -> str:
    """把工具结果压成给模型看的紧凑文本。"""
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
