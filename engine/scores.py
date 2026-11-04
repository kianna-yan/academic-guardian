"""成绩查询：把「哪门课最好」「班里谁成绩最好」变成可计算的数。

为什么单开一个模块：
课程数据里本来就有 `midterm`（期中卷面）和 `quizzes` / `assessments`（随堂测），
但原来的工具只暴露了课名、学分、任课教师——模型被问「我最好的课是哪一门」时，
翻遍所有工具都拿不到分数，只能诚实地说「系统里没有显示具体的课程成绩信息」。
这不是模型的问题，是取数能力缺了一块。

本模块按两个口径把成绩算清楚：
1. **课程内**：这门课我考了多少、班上均分多少、我在班里第几；
2. **班级内**：按学分加权期中均分排，谁在前谁在后。

口径和风险引擎 `raw.mid_avg`、教师端 `classroom._weighted_mid` 完全一致，
三处不会互相打脸。
"""
from __future__ import annotations

from statistics import mean

# 「与班均相比」必须由工具把方向说死。
# 之前只给裸数字 +4.2，模型有一次读成了「低于班均 4.2 分」。
def _vs(score: float, base: float) -> str:
    gap = round(score - base, 1)
    if gap > 0:
        return f"高 {gap} 分"
    if gap < 0:
        return f"低 {abs(gap)} 分"
    return "与班均持平"


def _mid(course: dict) -> float:
    try:
        return float(course.get("midterm") or 0)
    except (TypeError, ValueError):
        return 0.0


def weighted_mid(stu: dict) -> float:
    """学分加权期中均分。与 risk.py / classroom.py 同口径。"""
    courses = stu.get("courses") or []
    credits = sum(float(c.get("credit") or 0) for c in courses)
    if not credits:
        return 0.0
    return round(sum(_mid(c) * float(c.get("credit") or 0) for c in courses) / credits, 1)


def _course_of(stu: dict, code: str) -> dict | None:
    for c in stu.get("courses") or []:
        if c.get("code") == code:
            return c
    return None


def class_name_of(engine, text: str) -> tuple[str | None, list[str]]:
    """把用户口中的班级名对到库里的真实班级。

    返回 (命中班级, 候选)。库里的班级只有「计科2401…2406」，
    用户说「软件2401」「2401班」「计科一班」都要能落到同一个班；
    实在对不上就把候选还给调用方，让模型去问，而不是返回「0 人」。
    """
    text = (text or "").strip()
    classes = sorted({s["class_name"] for s in engine.students})
    if not text:
        return None, []
    if text in classes:
        return text, []
    # 包含匹配："计科2401班" / "2401那个班"
    hits = [c for c in classes if c in text or c.replace("计科", "") in text]
    if len(hits) == 1:
        return hits[0], []
    # 只给了班号："2401"、"2401班"、"01班"
    import re
    m = re.search(r"(\d{2,4})\s*班?", text)
    if m:
        tail = m.group(1)
        cand = [c for c in classes if c.endswith(tail[-2:])]
        if len(cand) == 1:
            return cand[0], []
        if len(cand) > 1:
            return None, cand
    # 字形相近（软件2401 → 计科2401）
    import difflib
    close = difflib.get_close_matches(text, classes, n=3, cutoff=0.5)
    if close:
        return None, close
    return None, classes[:6]


def class_rank(engine, stu: dict, code: str | None = None) -> tuple[int, int, float]:
    """在班内按某门课（或学分加权）排第几。返回 (名次, 总人数, 班均)。"""
    peers = [s for s in engine.students if s.get("class_name") == stu.get("class_name")]
    if code:
        vals = [(s["id"], _mid(_course_of(s, code) or {})) for s in peers]
    else:
        vals = [(s["id"], weighted_mid(s)) for s in peers]
    vals.sort(key=lambda x: -x[1])
    total = len(vals)
    base = round(mean(v for _, v in vals), 1) if vals else 0.0
    for i, (sid, _) in enumerate(vals, 1):
        if sid == stu.get("id"):
            return i, total, base
    return 0, total, base


def student_scores(engine, stu: dict) -> dict:
    """一名学生的成绩全景：每门课的分数与班内位置 + 最强/最该补的两门。"""
    rows = []
    for c in stu.get("courses") or []:
        code = c.get("code") or ""
        score = _mid(c)
        rank, total, base = class_rank(engine, stu, code)
        quizzes = [q for q in (c.get("quizzes") or [])]
        last_assess = ""
        for a in reversed(c.get("assessments") or []):
            if a.get("score") is not None:
                last_assess = f"{a.get('label')} {a.get('score')} 分（{a.get('date')}）"
                break
        rows.append({
            "课程": c.get("name"),
            "学分": c.get("credit"),
            "期中卷面": score,
            "班内排名": f"{rank}/{total}",
            "班级均分": base,
            "与班均相比": _vs(score, base),
            "随堂测均分": round(mean(quizzes), 1) if quizzes else None,
            "最近一次测评": last_assess or "无",
            "任课教师": c.get("teacher"),
        })

    # 「最好的课」按期中卷面分排；「相对优势」按超出班均多少排——
    # 两者常常不是同一门（英语 81 分但全班都 85，数据结构 52 分却是班里第一）
    if rows:
        best = max(rows, key=lambda x: x["期中卷面"])
        weakest = min(rows, key=lambda x: x["期中卷面"])
        advantage = max(rows, key=lambda x: x["期中卷面"] - x["班级均分"])
        lagging = min(rows, key=lambda x: x["期中卷面"] - x["班级均分"])
    else:
        best = weakest = advantage = lagging = None

    my_rank, my_total, class_avg = class_rank(engine, stu)
    hist = stu.get("history") or {}
    gh = (stu.get("grade_history") or [])
    last_term = gh[-1] if gh else {}

    out = {
        "姓名": stu["name"],
        "学号": stu["id"],
        "班级": stu.get("class_name"),
        "学分加权期中均分": weighted_mid(stu),
        "班级均分": class_avg,
        "班内排名": f"{my_rank}/{my_total}",
        "各课成绩": rows,
        "上学期GPA": hist.get("gpa"),
        "上学期均分": hist.get("avg"),
        "上学期班级名次": (f"{last_term.get('rank')}/{last_term.get('rank_total')}"
                          if last_term.get("rank") else None),
    }
    if best:
        out["分数最高的课"] = {
            "课程": best["课程"], "期中卷面": best["期中卷面"],
            "班内排名": best["班内排名"], "与班均相比": best["与班均相比"],
        }
        out["相对班均优势最大的课"] = {
            "课程": advantage["课程"], "期中卷面": advantage["期中卷面"],
            "与班均相比": advantage["与班均相比"],
        }
        out["相对最弱的课"] = {
            "课程": lagging["课程"], "期中卷面": lagging["期中卷面"],
            "与班均相比": lagging["与班均相比"],
        }
        out["分数最低的课"] = {
            "课程": weakest["课程"], "期中卷面": weakest["期中卷面"],
            "班内排名": weakest["班内排名"], "与班均相比": weakest["与班均相比"],
        }
        out["口径"] = ("「分数最高」看的是期中卷面绝对分；「优势最大」看的是比本课班均高多少。"
                       "两者常常不是同一门，按用户问法选用，不要说成同一件事。")
    return out


def class_scores(engine, cls: str | None = None, course: str | None = None,
                 top_n: int = 8) -> dict:
    """班级成绩排序。course 给了就按那门课排，否则按学分加权期中均分。"""
    students = list(engine.students)
    if cls:
        students = [s for s in students if s.get("class_name") == cls]

    code, course_name = None, None
    pool = students if students else list(engine.students)
    if course and pool:
        want = course.strip()
        for c in pool[0].get("courses") or []:
            if want in (c.get("name") or "") or want.upper() == (c.get("code") or "").upper():
                code, course_name = c.get("code"), c.get("name")
                break

    def val(s: dict) -> float:
        if code:
            return _mid(_course_of(s, code) or {})
        return weighted_mid(s)

    ranked = sorted(students, key=lambda s: -val(s))
    total = len(ranked)
    scores = [val(s) for s in ranked]
    out = {
        "筛选": {"班级": cls or "全部班级", "口径": f"{course_name}期中卷面" if code else "学分加权期中均分"},
        "总人数": total,
        "班均": round(mean(scores), 1) if scores else None,
        "最高": round(max(scores), 1) if scores else None,
        "最低": round(min(scores), 1) if scores else None,
        "前几名": [{"名次": i, "姓名": s["name"], "班级": s.get("class_name"), "分数": val(s)}
                    for i, s in enumerate(ranked[:top_n], 1)],
    }
    if total > top_n:
        out["末几名"] = [{"名次": i, "姓名": s["name"], "分数": val(s)}
                        for i, s in enumerate(ranked[-3:], total - 2)]
        out["说明"] = f"共 {total} 人，这里只列前 {top_n} 名和末 3 名，不是全部"
    else:
        out["说明"] = f"共 {total} 人，已全部列出"
    return out


def my_rank_only(engine, stu: dict, course: str | None = None) -> dict:
    """学生 / 家长端：只给自己的名次与班均，不给其他同学的姓名。"""
    code, course_name = None, None
    if course:
        want = course.strip()
        for c in stu.get("courses") or []:
            if want in (c.get("name") or "") or want.upper() == (c.get("code") or "").upper():
                code, course_name = c.get("code"), c.get("name")
                break
    rank, total, base = class_rank(engine, stu, code)
    mine = _mid(_course_of(stu, code) or {}) if code else weighted_mid(stu)
    return {
        "班级": stu.get("class_name"),
        "口径": f"{course_name}期中卷面" if code else "学分加权期中均分",
        "我的分数": mine,
        "我的名次": f"{rank}/{total}",
        "班级均分": base,
        "与班均相比": _vs(mine, base),
        "超过": f"班里 {max(0, total - rank)} 人",
        "说明": "只给本人的名次与均分，不提供其他同学的姓名与分数。",
    }
