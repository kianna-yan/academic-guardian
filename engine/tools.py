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
                "问「我的老师都有谁」「数据结构老师邮箱」时用这个。",
        "params": {
            "name": {"type": "string", "description": "学生姓名或学号"},
        },
        "required": ["name"],
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
    out = []
    for c in stu["courses"]:
        tp = c.get("teacher_profile") or {}
        out.append({
            "课程": c["name"], "代码": c.get("code"), "学分": c.get("credit"),
            "教师": c.get("teacher"), "职称": tp.get("title"),
            "办公室": tp.get("office"), "邮箱": tp.get("email"),
            "答疑": tp.get("office_hour"),
        })
    return {"ok": True, "data": {"姓名": stu["name"], "在修课程": out}}


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
    rows = agent.engine.roster(cls, level)
    brief = [{
        "姓名": r["name"], "班级": r["class_name"], "风险分": r["score"],
        "等级": r["level_label"], "主因": r.get("top_factor"),
        "旷课": r.get("absent"), "缺交作业": r.get("missed_hw"),
    } for r in rows[:MAX_ROWS]]
    return {"ok": True, "data": {
        "筛选": {"班级": cls or "全部", "等级": level or "全部"},
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
    return {"ok": True, "data": {
        "检索词": q,
        "条款": [{
            "出处": h.get("citation"),
            "学校": h.get("school"),
            "原文": (h.get("text") or "")[:400],
        } for h in hits[:3]],
        "说明": "回答时必须注明出自哪一条，不要改写条款里的数字。",
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
    "get_roster": _t_get_roster,
    "get_overview": _t_get_overview,
    "search_policy": _t_search_policy,
    "get_classroom": _t_get_classroom,
}


def run(agent, role: str, sid: str | None, name: str, args: dict,
        teacher_name: str = "") -> dict:
    """执行一个工具。任何异常都收敛成 ok=False，绝不把堆栈抛给模型。"""
    fn = _HANDLERS.get(name)
    if not fn:
        return {"ok": False, "note": f"没有名为 {name} 的工具，可用的是：{'、'.join(_HANDLERS)}"}
    safe = dict(args or {})
    safe["__teacher__"] = teacher_name
    try:
        return fn(agent, role, sid, safe)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "note": f"工具 {name} 执行出错：{type(e).__name__}: {e}"}


def render(result: dict) -> str:
    """把工具结果压成给模型看的紧凑文本。"""
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
