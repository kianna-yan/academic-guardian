"""教师端课堂学情聚合（第五端 · 任课老师视角）。

和其他四端最本质的区别：这里的统计单位是「一门课的课堂」，不是「一个学生」。
同一个学生在数据结构老师眼里是「作业 6 次交 3 次」，在概率论老师眼里可能是
「出勤全勤、期中考了 88」——所以本模块所有指标都在本课程范围内重算，
不搬用学生的跨课汇总，避免老师看到不属于自己课堂的事实。

输出三块：
1. courses：每门课的课堂画像（均分、及格率、分布、逐周出勤、逐次作业、分班对比）
2. students：修课学生在本课堂的明细（含课堂内排名、与同伴均分的差距）
3. todos：只有任课老师才会做的四件事（催作业、盯连续缺勤、课后答疑、反馈辅导员）
"""
from __future__ import annotations

from statistics import mean, median, pstdev

BUCKETS = [(90, 101, "90 分以上"), (80, 90, "80-89"), (70, 80, "70-79"),
           (60, 70, "60-69"), (0, 60, "60 分以下")]


def _weighted_mid(student: dict) -> float:
    """学分加权期中均分：和风险引擎 raw.mid_avg 完全同口径，口径不一致会被老师质疑。"""
    courses = student.get("courses") or []
    credits = sum(float(c.get("credit") or 0) for c in courses)
    if not credits:
        return 0.0
    return sum(_midterm_of(c) * float(c.get("credit") or 0) for c in courses) / credits


def _midterm_of(course: dict) -> float:
    try:
        return float(course.get("midterm") or 0)
    except (TypeError, ValueError):
        return 0.0


def _longest_absent_streak(records: list[dict]) -> int:
    """最长连续旷课次数：老师关心的是「连着不来」，不是「总共缺几次」。"""
    best = cur = 0
    for r in records:
        if r.get("status") == "absent":
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _weekly(records: list[dict]) -> list[dict]:
    """按教学周聚合出勤：第 1-7 周，每周两次课。"""
    buckets: dict[int, dict] = {}
    for r in records:
        w = int(r.get("week") or 0)
        if not w:
            continue
        slot = buckets.setdefault(w, {"week": w, "absent": 0, "late": 0, "present": 0, "total": 0})
        slot["total"] += 1
        st = r.get("status")
        if st == "absent":
            slot["absent"] += 1
        elif st == "late":
            slot["late"] += 1
        else:
            slot["present"] += 1
    return [buckets[k] for k in sorted(buckets)]


def _homework_items(rows: list[list[dict]]) -> list[dict]:
    """逐次作业的提交情况：rows 是每个学生的作业列表。"""
    order: list[str] = []
    stat: dict[str, dict] = {}
    for hw_list in rows:
        for h in hw_list:
            key = h.get("id") or h.get("title") or ""
            if key not in stat:
                order.append(key)
                stat[key] = {"id": key, "title": h.get("title", ""), "due": h.get("due", ""),
                             "assigned": h.get("assigned", ""),
                             "submitted": 0, "late": 0, "missing": 0}
            st = h.get("status")
            slot = stat[key]
            if st == "submitted":
                slot["submitted"] += 1
            elif st == "late":
                slot["late"] += 1
                slot["submitted"] += 1     # 迟交也算交了，算提交率时合并
            else:
                slot["missing"] += 1
    out = []
    for key in order:
        slot = stat[key]
        total = slot["submitted"] + slot["missing"]
        slot["total"] = total
        slot["rate"] = round(slot["submitted"] / total * 100, 1) if total else 0.0
        slot["ontime_rate"] = round((slot["submitted"] - slot["late"]) / total * 100, 1) if total else 0.0
        out.append(slot)
    return out


def _dist(scores: list[float]) -> list[dict]:
    rows = []
    for lo, hi, label in BUCKETS:
        n = sum(1 for s in scores if lo <= s < hi)
        rows.append({"label": label, "count": n,
                     "pct": round(n / len(scores) * 100, 1) if scores else 0.0})
    return rows


def report(engine, teacher_name: str, teacher_profile: dict | None = None,
           term: str = "", week: int = 0) -> dict:
    """把某位任课教师的课堂学情整理成前端直接可画的结构。"""
    profile = dict(teacher_profile or {})
    profile.setdefault("name", teacher_name)

    my_courses: list[dict] = []
    seen: set[str] = set()
    by_course: dict[str, list[dict]] = {}

    for s in engine.students:
        mine = [c for c in s["courses"] if c.get("teacher") == teacher_name]
        if not mine:
            continue
        for c in mine:
            if c["code"] not in seen:
                seen.add(c["code"])
                my_courses.append({"code": c["code"], "name": c["name"],
                                   "credit": c.get("credit"), "kind": c.get("kind"),
                                   "period": c.get("period"), "teacher": c.get("teacher")})
            by_course.setdefault(c["code"], []).append({"student": s, "course": c})

    courses_out: list[dict] = []
    student_rows: list[dict] = []

    # 年级总均分：全体学生六门课的学分加权均分（与风险分里的 mid_avg 同口径）。
    # 用全校同一门课的均分做参照没有意义——这门课 240 人就是全校 240 人，
    # 差值恒为 0；能说明问题的参照是「这门课在年级六门课里偏难还是偏易」。
    grade_mids = [_weighted_mid(s) for s in engine.students]
    grade_avg_all = round(mean(grade_mids), 1) if grade_mids else 0.0

    for brief in my_courses:
        code = brief["code"]
        rows = by_course.get(code, [])
        scores = [_midterm_of(r["course"]) for r in rows]
        # 教学班（行政班在本课堂里的分布）：老师最想知道「哪个班我讲得最吃力」
        class_bucket: dict[str, dict] = {}
        for r in rows:
            cls = r["student"]["class_name"]
            slot = class_bucket.setdefault(cls, {"class_name": cls, "students": 0, "scores": [],
                                                 "absent": 0, "late": 0, "sessions": 0,
                                                 "hw_sub": 0, "hw_asg": 0, "red": 0, "yellow": 0})
            c = r["course"]
            slot["students"] += 1
            slot["scores"].append(_midterm_of(c))
            slot["absent"] += int(c.get("absent") or 0)
            slot["late"] += int(c.get("late") or 0)
            slot["sessions"] += int(c.get("sessions_held") or 0)
            slot["hw_sub"] += int(c.get("hw_submitted") or 0)
            slot["hw_asg"] += int(c.get("hw_assigned") or 0)

        attend_all = [a for r in rows for a in (r["course"].get("attendance") or [])]
        hw_all = [r["course"].get("homework") or [] for r in rows]
        weekly = _weekly(attend_all)
        hw_items = _homework_items(hw_all)

        absent_total = sum(int(r["course"].get("absent") or 0) for r in rows)
        late_total = sum(int(r["course"].get("late") or 0) for r in rows)
        sessions_total = sum(int(r["course"].get("sessions_held") or 0) for r in rows)
        hw_sub = sum(int(r["course"].get("hw_submitted") or 0) for r in rows)
        hw_asg = sum(int(r["course"].get("hw_assigned") or 0) for r in rows)
        cohort_avg = engine.course_stats.get(code, {}).get("mean")
        mid_avg = round(mean(scores), 1) if scores else 0.0
        grade_avg = grade_avg_all

        for cls, slot in class_bucket.items():
            slot["mid_avg"] = round(mean(slot["scores"]), 1) if slot["scores"] else 0.0
            # 班级差距对齐「本课均分」：老师关心的是班与班之间，不是班与全校
            slot["gap"] = round(slot["mid_avg"] - mid_avg, 1)
            slot["hw_rate"] = round(slot["hw_sub"] / slot["hw_asg"] * 100, 1) if slot["hw_asg"] else 0.0
            slot["absent_rate"] = round(slot["absent"] / slot["sessions"] * 100, 1) if slot["sessions"] else 0.0
            slot["low"] = sum(1 for s in slot["scores"] if s < 60)
            slot.pop("scores", None)
            for key in ("hw_sub", "hw_asg", "sessions"):
                slot.pop(key, None)

        # 课堂内排名：老师排座位、叫名字都用得上
        ranked = sorted(rows, key=lambda r: -_midterm_of(r["course"]))
        rank_of = {r["student"]["id"]: i + 1 for i, r in enumerate(ranked)}

        for r in rows:
            s, c = r["student"], r["course"]
            try:
                risk = engine.score(s["id"])
                score, level, label = risk["score"], risk["level"], risk["level_label"]
                top_factor = risk["factors"][0]["label"] if risk["factors"] else ""
            except Exception:
                score, level, label, top_factor = 0, "green", "正常", ""
            mid = _midterm_of(c)
            class_mean = engine.course_stats.get(code, {}).get("mean") or 0
            student_rows.append({
                "id": s["id"], "name": s["name"], "class_name": s["class_name"],
                "score": score, "level": level, "level_label": label, "top_factor": top_factor,
                "code": code, "course": c["name"],
                "midterm": c.get("midterm"),
                "cohort_avg": class_mean,
                "gap": round(mid - class_mean, 1),
                "absent": int(c.get("absent") or 0),
                "late": int(c.get("late") or 0),
                "sessions_held": int(c.get("sessions_held") or 0),
                "hw_submitted": int(c.get("hw_submitted") or 0),
                "hw_assigned": int(c.get("hw_assigned") or 0),
                "hw_missing": int(c.get("hw_assigned") or 0) - int(c.get("hw_submitted") or 0),
                "rank": rank_of.get(s["id"]),
                "rank_total": len(rows),
                "absent_streak": _longest_absent_streak(c.get("attendance") or []),
                "attendance": c.get("attendance") or [],
                "homework": c.get("homework") or [],
            })

        # 分班行的红黄人数：学生的风险等级是在上面逐人算完的，这里回填到班
        for slot in class_bucket.values():
            mine = [x for x in student_rows
                    if x["code"] == code and x["class_name"] == slot["class_name"]]
            slot["red"] = sum(1 for x in mine if x["level"] == "red")
            slot["yellow"] = sum(1 for x in mine if x["level"] == "yellow")

        risk_dist = {"red": sum(1 for x in student_rows if x["code"] == code and x["level"] == "red"),
                     "yellow": sum(1 for x in student_rows if x["code"] == code and x["level"] == "yellow"),
                     "green": sum(1 for x in student_rows if x["code"] == code and x["level"] == "green")}

        courses_out.append({
            "code": code, "name": brief["name"], "credit": brief.get("credit"),
            "kind": brief.get("kind"), "period": brief.get("period"),
            "students": len(rows),
            "mid_avg": mid_avg,
            "cohort_avg": cohort_avg,
            "grade_avg": grade_avg,
            "gap_grade": round(mid_avg - grade_avg, 1) if grade_avg else 0.0,
            "median": round(median(scores), 1) if scores else 0.0,
            "highest": round(max(scores), 1) if scores else 0.0,
            "lowest": round(min(scores), 1) if scores else 0.0,
            "std": round(pstdev(scores), 1) if len(scores) > 1 else 0.0,
            "pass_rate": round(sum(1 for x in scores if x >= 60) / len(scores) * 100, 1) if scores else 0.0,
            "dist": _dist(scores),
            "risk": risk_dist,
            "attend": {
                "sessions": max((int(r["course"].get("sessions_held") or 0) for r in rows), default=0),
                "absent": absent_total,
                "late": late_total,
                "rate": round((sessions_total - absent_total) / sessions_total * 100, 1) if sessions_total else 0.0,
                "weekly": weekly,
            },
            "hw": {
                "assigned": max((int(r["course"].get("hw_assigned") or 0) for r in rows), default=0),
                "submitted": hw_sub,
                "rate": round(hw_sub / hw_asg * 100, 1) if hw_asg else 0.0,
                "items": hw_items,
            },
            "classes": sorted(class_bucket.values(), key=lambda x: -x["mid_avg"]),
        })

    student_rows.sort(key=lambda r: -(r["midterm"] or 0))
    todos = _todos(student_rows, courses_out, week=week)

    return {
        "teacher": profile,
        "term": term,
        "week": week,
        "courses": courses_out,
        "students": student_rows,
        "todos": todos,
        "summary": _summary(profile.get("name", teacher_name), courses_out, student_rows),
    }


def _summary(name: str, courses: list[dict], students: list[dict]) -> str:
    if not courses:
        return f"{name} 老师本学期暂无任课记录。"
    c = courses[0]
    return (f"{name}老师：{c['name']}共 {c['students']} 人，期中均分 {c['mid_avg']}"
            f"（年级总均分 {c['grade_avg']}，{c['gap_grade']:+}），及格率 {c['pass_rate']}%，"
            f"作业提交率 {c['hw']['rate']}%，需重点关注 {len([s for s in students if s['level'] != 'green'])} 人。")


def _todos(students: list[dict], courses: list[dict], week: int = 0) -> list[dict]:
    """任课老师这一周真正要做的四件事，按紧急程度排。"""
    out: list[dict] = []

    # 1) 最近一次作业的未交名单：老师布置完作业最先看的就是这个
    if courses:
        items = courses[0]["hw"]["items"]
        if items:
            latest = items[-1]
            miss = [s for s in students
                    if any((h.get("title") == latest["title"] and h.get("status") == "missing")
                           for h in s["homework"])]
            miss.sort(key=lambda s: -s["score"])
            if miss:
                out.append({
                    "id": "hw-latest", "kind": "homework", "tone": "amber",
                    "title": f"催交《{latest['title']}》：还差 {len(miss)} 人",
                    "detail": f"截止 {latest['due']}，已交 {latest['submitted'] - latest['late']} 人、"
                              f"迟交 {latest['late']} 人、未交 {latest['missing']} 人。",
                    "names": [s["name"] for s in miss[:6]],
                    "sids": [s["id"] for s in miss[:6]],
                    "action": "课上点名提醒，或让学习委员单独通知",
                })

    # 2) 连续缺勤：连着两次不来，通常不是临时有事
    streak = [s for s in students if s["absent_streak"] >= 2]
    streak.sort(key=lambda s: (-s["absent_streak"], s["score"]))
    if streak:
        out.append({
            "id": "absent-streak", "kind": "attendance", "tone": "red",
            "title": f"连续缺勤 ≥2 次：{len(streak)} 人",
            "detail": "连续两次没到的学生，多半是遇到了具体困难，建议课前单独问一句。",
            "names": [f"{s['name']}（{s['absent_streak']} 次）" for s in streak[:6]],
            "sids": [s["id"] for s in streak[:6]],
            "action": "课前询问原因；确属无故旷课再反馈辅导员",
        })

    # 3) 明显掉队：低于课堂均分 10 分以上，属于讲一遍听不懂的群体
    if students:
        avg = mean([s["midterm"] or 0 for s in students]) if students else 0
        behind = [s for s in students if (s["midterm"] or 0) <= avg - 10]
        behind.sort(key=lambda s: (s["midterm"] or 0))
        if behind:
            out.append({
                "id": "behind", "kind": "grade", "tone": "amber",
                "title": f"低于课堂均分 10 分以上：{len(behind)} 人",
                "detail": f"课堂均分 {round(avg, 1)}，这批学生在听同一个进度时最吃力。",
                "names": [f"{s['name']}（{s['midterm']}）" for s in behind[:6]],
                "sids": [s["id"] for s in behind[:6]],
                "action": "安排一次课后答疑，或把这批人的共性错题集中讲一遍",
            })

    # 4) 红色预警：课堂管不了的部分交回辅导员，老师只负责反馈
    red = [s for s in students if s["level"] == "red"]
    if red:
        out.append({
            "id": "feedback", "kind": "risk", "tone": "red",
            "title": f"红色预警 {len(red)} 人：建议反馈辅导员",
            "detail": "风险分已过预警线的学生，任课教师能做的到此为止，剩下交给辅导员面谈。",
            "names": [f"{s['name']}（{s['score']} 分）" for s in red[:6]],
            "sids": [s["id"] for s in red[:6]],
            "action": "点「反馈辅导员」生成一段可转发的说明",
        })
    return out
