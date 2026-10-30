"""课表、课后自评与学习轨迹。

三件事放在一个模块里，因为它们共用同一份"这节课"：

1. **课表**：由 engine/data.py 的 COURSES[].slots 现算，不另存一份。
   考勤明细（学生端「课堂考勤」）也是按 slots 生成的，所以课表上的每一节
   和考勤记录里的每一条永远对得上，不会出现"课表说周三有课、考勤里没有"。

2. **课后记录**：学生自己写的一句话状态（听懂 / 模糊 / 没听懂 + 从第几分钟
   开始没听懂 + 卡在哪个知识点 + 之后打算怎么办），落 data/checkins.json。

3. **学习轨迹**：把每门课已上过的课按时间连成一条线，标出断点从哪一节开始、
   哪一节又接上了（修复）。断点判定用的是"连续几节没听懂"，而不是单节—— 
   一节课没跟上很正常，连着三节没跟上才是真掉队。

**设计红线：打卡内容不进风险分公式。** 学生诚实地说"没听懂"，系统只会给他
更清楚的轨迹和更具体的求助路径，绝不会因为自评差而扣分。所以这里算出来的
任何数字都只用于展示与建议，不参与 risk.py 的加权。
"""
from __future__ import annotations

import json
import threading
from datetime import date, timedelta
from pathlib import Path
from random import Random

from .data import COURSES, SESSIONS_TOTAL, SLOT_LABEL, TEACHERS, TODAY, WEEK1_MONDAY, db

# 一节课按 2 小节 × 45 分钟算，学生说的"第几分钟"落在这个区间里
LESSON_MINUTES = 90

UNDERSTAND = {
    "full": {"label": "听懂了", "short": "听懂", "level": 0},
    "fuzzy": {"label": "有点模糊", "short": "模糊", "level": 1},
    "lost": {"label": "没听懂", "short": "没懂", "level": 2},
}

# 「从什么时候开始没听懂」：给学生几个符合直觉的锚点，也允许自己填分钟数
BREAK_AT = {
    "none": ("这节课都跟上了", 0),
    "start": ("从上课一开始就没跟上", 0),
    "first15": ("前 15 分钟还行，之后就懵了", 15),
    "middle": ("讲到中间（约第 45 分钟）开始", 45),
    "secondhalf": ("后半节课（约第 60 分钟）开始", 60),
    "minute": ("我记得具体是第几分钟", -1),
}

PLANS = {
    "none": "先放着，等讲完这章再说",
    "replay": "看回放 / 微课补一遍",
    "peer": "问同学要笔记",
    "teacher": "下次答疑去问老师",
    "self": "自己重看书和例题",
}

# 课表里的教室：演示数据，不参与任何计算，只为让课表看起来像课表
ROOMS = {
    "CS201": "信息楼 A305",
    "CS203": "信息楼 A402",
    "MA204": "理科楼 B210",
    "EN203": "文科楼 C301",
    "PE201": "文科楼 C108",
    "CS215": "信息楼 A518（机房）",
}

# 打卡时"卡在哪个知识点"的快选标签（也可以自己写）
POINTS = {
    "CS201": ["递归与栈", "二叉树遍历", "图的最短路", "哈希冲突", "复杂度分析"],
    "CS203": ["浮点数表示", "Cache 命中率", "指令流水", "ALU 设计", "总线时序"],
    "MA204": ["全概率公式", "贝叶斯公式", "二维随机变量", "期望与方差", "参数估计"],
    "EN203": ["长难句拆解", "听力速记", "议论文结构", "学术词汇", "口语表达"],
    "PE201": ["唯物辩证法", "实践与认识", "社会基本矛盾", "剩余价值", "科学社会主义"],
    "CS215": ["ORM 建模", "路由与蓝图", "表单校验", "RESTful 设计", "鉴权与权限"],
}

MAX_NOTE = 160
MAX_POINT = 40


def period_order(period: str) -> int:
    """「3-4 节」→ 3，用来给课表行排序。"""
    head = period.split("-")[0].strip()
    return int(head) if head.isdigit() else 99


def break_label(break_at: str, minute: int | None) -> str:
    if break_at == "minute":
        return f"第 {int(minute or 0)} 分钟起没跟上"
    label = BREAK_AT.get(break_at, BREAK_AT["none"])[0]
    return "" if break_at in ("none", "") else label


def _break_minute(break_at: str, minute: int | None) -> int:
    if break_at == "minute":
        return max(0, min(LESSON_MINUTES, int(minute or 0)))
    return max(0, BREAK_AT.get(break_at, ("", 0))[1])


# ---------------------------------------------------------------------------
# 课表：由 COURSES 的 slots 现算，缓存一份，教务改课程名后 rebuild 时会重建
# ---------------------------------------------------------------------------
_CAL: dict[str, list[dict]] = {}


def calendar() -> dict[str, list[dict]]:
    """每门课本学期每一节课的具体日期（含未上的），按日期排好序。"""
    if _CAL:
        return _CAL
    for course in COURSES:
        slots = course.get("slots") or [(0, "1-2 节")]
        weeks = int(course.get("weeks", SESSIONS_TOTAL))
        rows: list[dict] = []
        for week in range(1, weeks + 1):
            monday = WEEK1_MONDAY + timedelta(weeks=week - 1)
            for weekday, period in slots:
                day = monday + timedelta(days=weekday)
                rows.append({
                    "course": course["code"],
                    "name": course["name"],
                    "teacher": course["teacher"],
                    "kind": course.get("kind", "必修"),
                    "credit": course.get("credit", 0),
                    "room": ROOMS.get(course["code"], ""),
                    "date": day.isoformat(),
                    "week": week,
                    "weekday": weekday,
                    "weekday_label": SLOT_LABEL[weekday],
                    "period": period,
                    # held：这节课是否已经上过（含今天正在上的）
                    "held": day <= TODAY,
                    "today": day == TODAY,
                })
        rows.sort(key=lambda r: (r["date"], period_order(r["period"])))
        for i, row in enumerate(rows):
            row["index"] = i
        _CAL[course["code"]] = rows
    return _CAL


def rebuild() -> None:
    """教务改了课程档案后重建日历（课程代码集合变了也不需要重启）。"""
    _CAL.clear()
    calendar()


def course_meta(code: str) -> dict:
    for c in COURSES:
        if c["code"] == code:
            return c
    return {}


def held_sessions(code: str) -> list[dict]:
    return [s for s in calendar().get(code, []) if s["held"]]


def record_id(code: str, day: str, period: str) -> str:
    return f"{code}|{day}|{period}"


def _decorate(session: dict, rec: dict | None) -> dict:
    """一节课 + 学生自己的记录 = 课表上的一格。"""
    out = dict(session)
    out["recorded"] = bool(rec)
    out["state"] = (rec or {}).get("understand") or ""
    out["state_label"] = UNDERSTAND.get(out["state"], {}).get("label", "")
    out["break_label"] = (rec or {}).get("break_label", "")
    out["point"] = (rec or {}).get("point", "")
    out["plan_label"] = PLANS.get((rec or {}).get("plan", ""), "")
    out["note"] = (rec or {}).get("note", "")
    out["checkin_id"] = (rec or {}).get("id", "")
    return out


def timetable(week: int, index: dict[str, dict], meta: dict) -> dict:
    """某一教学周的课表格子。index 是 {(课程, 日期, 节次): 记录}。"""
    week = max(1, min(SESSIONS_TOTAL, int(week)))
    monday = WEEK1_MONDAY + timedelta(weeks=week - 1)
    slots: list[dict] = []
    for code, rows in calendar().items():
        for s in rows:
            if s["week"] != week or s["weekday"] > 4:
                continue
            rec = index.get(record_id(code, s["date"], s["period"]))
            slots.append(_decorate(s, rec))

    slots.sort(key=lambda r: (r["weekday"], period_order(r["period"])))
    days = [
        {
            "key": d,
            "label": SLOT_LABEL[d],
            "date": (monday + timedelta(days=d)).isoformat(),
            "today": (monday + timedelta(days=d)) == TODAY,
        }
        for d in sorted({s["weekday"] for s in slots}) or [0, 1, 2, 3, 4]
    ]
    periods = sorted({s["period"] for s in slots}, key=period_order)
    cells: dict[str, list[dict]] = {}
    for s in slots:
        cells.setdefault(f"{s['weekday']}@{s['period']}", []).append(s)

    held = [s for s in slots if s["held"]]
    checked = [s for s in held if s["recorded"]]
    this_week_due = [s for s in held if not s["recorded"]]
    return {
        "week": week,
        "weeks": {"min": 1, "max": SESSIONS_TOTAL, "current": int(meta.get("week") or week)},
        "today": TODAY.isoformat(),
        "days": days,
        "periods": periods,
        "cells": cells,
        "slots": slots,
        "stats": {
            "total": len(slots),
            "held": len(held),
            "checked": len(checked),
            "pending": len(this_week_due),
        },
    }


# ---------------------------------------------------------------------------
# 记录存储：data/checkins.json，跨重启保留
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STORE = DATA_DIR / "checkins.json"


class CheckinError(Exception):
    pass


class Checkins:
    def __init__(self, path: Path = STORE) -> None:
        self.path = path
        self._lock = threading.RLock()
        self.data: dict[str, list[dict]] = {}
        self.persistent = True
        self._load()

    # ---------------- 持久化 ----------------
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        rows = raw.get("records") if isinstance(raw, dict) else None
        if isinstance(rows, dict):
            self.data = {k: [r for r in v if isinstance(r, dict)] for k, v in rows.items()}

    def _save(self) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps({"records": self.data}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self.path)
            self.persistent = True
        except Exception:
            # 落盘失败不影响本次演示，但要把状态标出来，别让用户以为存住了
            self.persistent = False

    # ---------------- 读写 ----------------
    def rows(self, sid: str, course: str | None = None) -> list[dict]:
        with self._lock:
            items = list(self.data.get(sid, []))
        if course:
            items = [r for r in items if r.get("course") == course]
        items.sort(key=lambda r: (r.get("date", ""), -period_order(r.get("period", ""))))
        return [dict(r) for r in items]

    def index(self, sid: str) -> dict[str, dict]:
        return {r["id"]: r for r in self.rows(sid)}

    def _validate(self, code: str, day: str, period: str, body: dict) -> dict:
        cal = calendar().get(code)
        if not cal:
            raise CheckinError("没有这门课")
        session = next((s for s in cal if s["date"] == day and s["period"] == period), None)
        if not session:
            raise CheckinError("这节课不在课表里，请从课表进入记录")
        if not session["held"]:
            raise CheckinError("这节课还没上，等上完再记")
        understand = str(body.get("understand") or "full")
        if understand not in UNDERSTAND:
            raise CheckinError("请选择这节课的状态（听懂 / 模糊 / 没听懂）")
        break_at = str(body.get("break_at") or "none")
        if break_at not in BREAK_AT:
            break_at = "none"
        if understand == "full":
            break_at = "none"
        minute = body.get("break_minute")
        try:
            minute = int(minute) if minute not in (None, "") else None
        except (TypeError, ValueError):
            minute = None
        plan = str(body.get("plan") or "none")
        if plan not in PLANS:
            plan = "none"
        point = str(body.get("point") or "").strip()[:MAX_POINT]
        note = str(body.get("note") or "").strip()[:MAX_NOTE]
        return {
            "understand": understand,
            "break_at": break_at,
            "break_minute": minute,
            "break_label": break_label(break_at, minute) if understand != "full" else "",
            "minute_from": _break_minute(break_at, minute) if understand != "full" else 0,
            "point": point,
            "plan": plan,
            "note": note,
        }

    def upsert(self, sid: str, body: dict) -> dict:
        code = str(body.get("course") or "")
        day = str(body.get("date") or "")
        period = str(body.get("period") or "")
        payload = self._validate(code, day, period, body)
        rid = record_id(code, day, period)
        meta = course_meta(code)
        with self._lock:
            items = self.data.setdefault(sid, [])
            old = next((r for r in items if r.get("id") == rid), None)
            row = {
                "id": rid,
                "course": code,
                "course_name": meta.get("name", code),
                "date": day,
                "week": next(
                    (s["week"] for s in calendar()[code] if s["date"] == day and s["period"] == period), 0
                ),
                "period": period,
                "created_at": (old or {}).get("created_at") or "",
                "updated_at": "",
                **payload,
            }
            from datetime import datetime

            now = datetime.now().strftime("%m-%d %H:%M")
            row["updated_at"] = now
            if not row["created_at"]:
                row["created_at"] = now
            if old:
                items[items.index(old)] = row
            else:
                items.append(row)
            self._save()
            return dict(row)

    def remove(self, sid: str, rid: str) -> bool:
        with self._lock:
            items = self.data.get(sid) or []
            keep = [r for r in items if r.get("id") != rid]
            if len(keep) == len(items):
                return False
            self.data[sid] = keep
            self._save()
            return True

    # ---------------- 演示数据 ----------------
    def demo(self, sid: str) -> int:
        """给演示用：按这位学生的期中成绩生成近几周的自评记录。

        低分课程留一段"到现在还没接上"的断点，中段课程留一段后来接上的断点，
        这样学习轨迹里的红带、修复环、建议卡都能看见。学生随时可以改或删。
        已有记录不覆盖——学生自己写的永远优先。
        """
        student = next((s for s in db()["students"] if s["id"] == sid), None)
        if not student:
            return 0
        rng = Random(hash(sid) & 0xFFFF)
        existing = {r["id"] for r in self.rows(sid)}
        added = 0
        for course in student["courses"]:
            code = course["code"]
            mid = course["midterm"]
            p_lost = 0.40 if mid < 50 else 0.20 if mid < 65 else 0.05
            p_fuzzy = 0.30 if mid < 65 else 0.16
            # 只留最后一节不写：正好给「课后打卡」留一条待办，其余整学期都有记录
            held = held_sessions(code)[:-1]
            points = POINTS.get(code, [])
            for i, s in enumerate(held):
                # 低分课：最近两节还没跟上（未接上的断点）
                if mid < 62 and i >= len(held) - 2:
                    state = "lost"
                # 中段课：第 3、4 节掉队，后面又接回来（已修复的断点）
                elif 62 <= mid < 74 and i in (2, 3):
                    state = "lost"
                else:
                    roll = rng.random()
                    if roll < p_lost:
                        state = "lost"
                    elif roll < p_lost + p_fuzzy:
                        state = "fuzzy"
                    else:
                        state = "full"
                if record_id(code, s["date"], s["period"]) in existing:
                    continue
                payload = {
                    "course": code,
                    "date": s["date"],
                    "period": s["period"],
                    "understand": state,
                    "break_at": rng.choice(["start", "first15", "middle", "secondhalf"]) if state != "full" else "none",
                    "point": rng.choice(points) if state != "full" and points else "",
                    "plan": rng.choice(list(PLANS.keys())) if state != "full" else "none",
                    "note": "",
                }
                self.upsert(sid, payload)
                added += 1
        return added


# ---------------------------------------------------------------------------
# 学习轨迹：把记录连成线，标出断点与修复
# ---------------------------------------------------------------------------
def _segments(points: list[dict]) -> list[dict]:
    """把逐节状态压成连续的段，前端画轨道时一段一个色块。"""
    out: list[dict] = []
    for p in points:
        state = p["state"] or "none"
        if out and out[-1]["state"] == state:
            out[-1]["to"] = p["index"]
            out[-1]["count"] += 1
            out[-1]["dates"].append(p["date"])
        else:
            out.append({
                "state": state,
                "from": p["index"],
                "to": p["index"],
                "count": 1,
                "dates": [p["date"]],
            })
    return out


def _breaks(points: list[dict]) -> list[dict]:
    """断点 = 连续没听懂；后面第一次出现听懂/模糊就算接上了（修复）。

    只在"有记录"的课之间判断连续性：某节课没记，是学生没写，不是没听懂，
    不能拿它当证据，也不能让它在中间把一段断点切断。所以先筛出有状态的课，
    再在筛完的序列上找连续段，最后把位置映射回完整列表（给前端的修复环用）。
    """
    seq = [(i, p) for i, p in enumerate(points) if p["state"]]
    out: list[dict] = []
    k = 0
    while k < len(seq):
        if seq[k][1]["state"] != "lost":
            k += 1
            continue
        m = k
        while m + 1 < len(seq) and seq[m + 1][1]["state"] == "lost":
            m += 1
        run = [p for _, p in seq[k : m + 1]]
        after = seq[m + 1] if m + 1 < len(seq) else None
        # 单节没听懂不算断点：一节课跟不上很正常，连着两节以上才是真掉队
        if len(run) < 2:
            k = m + 1
            continue
        out.append({
            "start_index": seq[k][0],
            "end_index": seq[m][0],
            "count": len(run),
            "start_week": run[0]["week"],
            "start_date": run[0]["date"],
            "end_date": run[-1]["date"],
            "point": run[-1]["point"] or run[0]["point"],
            "minute_from": run[0]["minute_from"],
            "open": after is None,
            "recovered_index": after[0] if after else None,
            "recovered_week": after[1]["week"] if after else None,
            "recovered_date": after[1]["date"] if after else None,
            "state_after": after[1]["state"] if after else "",
        })
        k = m + 1
    return out


def _course_track(course: dict, rows: list[dict]) -> dict:
    code = course["code"]
    idx = {r["id"]: r for r in rows}
    held = held_sessions(code)
    points: list[dict] = []
    for s in held:
        rec = idx.get(record_id(code, s["date"], s["period"]))
        points.append({
            "index": s["index"],
            "date": s["date"],
            "week": s["week"],
            "weekday": s["weekday_label"],
            "period": s["period"],
            "state": (rec or {}).get("understand", ""),
            "recorded": bool(rec),
            "minute_from": (rec or {}).get("minute_from", 0),
            "break_label": (rec or {}).get("break_label", ""),
            "point": (rec or {}).get("point", ""),
            "plan": (rec or {}).get("plan", ""),
            "plan_label": PLANS.get((rec or {}).get("plan", ""), ""),
            "note": (rec or {}).get("note", ""),
            "id": (rec or {}).get("id", ""),
            "updated_at": (rec or {}).get("updated_at", ""),
        })

    recorded = [p for p in points if p["recorded"]]
    breaks = _breaks(points)
    open_breaks = [b for b in breaks if b["open"]]
    fixed = [b for b in breaks if not b["open"]]
    lost = sum(1 for p in points if p["state"] == "lost")
    fuzzy = sum(1 for p in points if p["state"] == "fuzzy")
    full = sum(1 for p in points if p["state"] == "full")

    if open_breaks:
        status = "break"
    elif lost or fuzzy:
        status = "watch"
    elif recorded:
        status = "ok"
    else:
        status = "empty"

    latest = recorded[-1] if recorded else None
    teacher = dict(TEACHERS.get(course.get("teacher", ""), {}))
    line = ""
    if open_breaks:
        b = open_breaks[-1]
        line = f"第 {b['start_week']} 周（{_md(b['start_date'])}）起，连续 {b['count']} 节没听懂，还没接上"
    elif fixed:
        b = fixed[-1]
        line = f"第 {b['start_week']} 周断过一次，第 {b['recovered_week']} 周已经接上了"
    elif status == "ok":
        line = f"已记录的 {len(recorded)} 节都跟上了"
    elif status == "watch":
        line = "有零星几节没跟上，暂时没形成连续断点"
    else:
        line = "这门课还没有课后记录"

    return {
        "code": code,
        "name": course["name"],
        "teacher": course["teacher"],
        "teacher_profile": teacher,
        "period": course.get("period", ""),
        "room": ROOMS.get(code, ""),
        "kind": course.get("kind", ""),
        "credit": course.get("credit", 0),
        "points": points,
        "segments": _segments(points),
        "breaks": breaks,
        "open_breaks": len(open_breaks),
        "fixed_breaks": len(fixed),
        "held": len(points),
        "recorded": len(recorded),
        "full": full,
        "fuzzy": fuzzy,
        "lost": lost,
        "status": status,
        "line": line,
        "latest": latest,
    }


def _md(iso: str) -> str:
    try:
        _, m, d = iso.split("-")
        return f"{int(m)} 月 {int(d)} 日"
    except Exception:
        return iso


def timeline(rows: list[dict]) -> list[dict]:
    names = {c["code"]: c["name"] for c in COURSES}
    rooms = ROOMS
    cal = calendar()
    out = []
    for r in rows:
        state = r.get("understand", "")
        session = next(
            (s for s in cal.get(r.get("course", ""), [])
             if s["date"] == r.get("date") and s["period"] == r.get("period")),
            None,
        )
        out.append({
            "id": r.get("id", ""),
            "course": r.get("course", ""),
            "course_name": r.get("course_name") or names.get(r.get("course", ""), ""),
            "teacher": (session or {}).get("teacher", ""),
            "room": rooms.get(r.get("course", ""), ""),
            "date": r.get("date", ""),
            "week": r.get("week", 0),
            "weekday": (session or {}).get("weekday_label", ""),
            "period": r.get("period", ""),
            "state": state,
            "state_label": UNDERSTAND.get(state, {}).get("label", ""),
            "break_label": r.get("break_label", ""),
            "minute_from": r.get("minute_from", 0),
            "point": r.get("point", ""),
            "plan": r.get("plan", ""),
            "plan_label": PLANS.get(r.get("plan", ""), ""),
            "note": r.get("note", ""),
            "updated_at": r.get("updated_at", ""),
        })
    out.sort(key=lambda x: (x["date"], period_order(x["period"])), reverse=True)
    return out


def track(sid: str, rows: list[dict], meta: dict) -> dict:
    """整页学习轨迹：每门课一条线 + 待补记录 + 记录流 + 汇总数字。"""
    tracks = [_course_track(c, rows) for c in COURSES]
    # 断点中的课排前面，其次是模糊，最后是没记录的 —— 学生一进来先看到该管的
    order = {"break": 0, "watch": 1, "ok": 2, "empty": 3}
    tracks.sort(key=lambda t: (order.get(t["status"], 9), -t["open_breaks"], t["code"]))

    timeline_rows = timeline(rows)
    week = int(meta.get("week") or 0)
    due: list[dict] = []
    for code, sessions in calendar().items():
        idx = {record_id(code, r["date"], r["period"]): r for r in rows}
        for s in sessions:
            if not s["held"] or record_id(code, s["date"], s["period"]) in idx:
                continue
            due.append({
                "course": code,
                "course_name": s["name"],
                "teacher": s["teacher"],
                "room": s["room"],
                "date": s["date"],
                "week": s["week"],
                "weekday": s["weekday_label"],
                "period": s["period"],
                "today": s["today"],
            })
    due.sort(key=lambda d: (d["date"], period_order(d["period"])), reverse=True)

    held_all = sum(t["held"] for t in tracks)
    recorded_all = sum(t["recorded"] for t in tracks)
    open_breaks = sum(t["open_breaks"] for t in tracks)
    fixed_breaks = sum(t["fixed_breaks"] for t in tracks)
    this_week = [d for d in due if d["week"] == week]
    week_held = [s for rows_ in calendar().values() for s in rows_ if s["held"] and s["week"] == week]
    week_done = sum(
        1 for s in week_held if record_id(s["course"], s["date"], s["period"]) in {r["id"] for r in rows}
    )

    # 连续记录：从最近一节已经上过的课往前数，有多少节是记了的
    streak = 0
    latest_held = sorted(
        [s for rows_ in calendar().values() for s in rows_ if s["held"]],
        key=lambda s: (s["date"], period_order(s["period"])),
        reverse=True,
    )
    recorded_ids = {r["id"] for r in rows}
    # 从最近一条记录往前数：今天还没记的课先跳过，不然刚下课就显示"连续 0 节"
    for s in latest_held:
        if record_id(s["course"], s["date"], s["period"]) in recorded_ids:
            streak += 1
        elif streak:
            break

    advice: list[dict] = []
    for t in tracks:
        if t["open_breaks"]:
            b = next(b for b in t["breaks"] if b["open"])
            teacher = t.get("teacher_profile") or {}
            advice.append({
                "kind": "break",
                "course": t["code"],
                "course_name": t["name"],
                "title": f"{t['name']}：第 {b['start_week']} 周起的断点还没补",
                "text": (
                    f"断点从 {_md(b['start_date'])} 那节课的第 {b['minute_from']} 分钟开始"
                    + (f"，卡在「{b['point']}」" if b["point"] else "")
                    + f"。已经连着 {b['count']} 节了，下一节上课前先把这一小段补掉，"
                    "比等到期中之后再补省力得多。"
                ),
                "who": teacher.get("name", t["teacher"]),
                "office_hour": teacher.get("office_hour", ""),
                "email": teacher.get("email", ""),
            })
        elif (t["fuzzy"] or t["lost"]) and t["recorded"]:
            last = t["latest"] or {}
            loose = t["fuzzy"] + t["lost"]
            advice.append({
                "kind": "fuzzy",
                "course": t["code"],
                "course_name": t["name"],
                "title": f"{t['name']}：{loose} 节没跟上，还没连成断点",
                "text": (
                    f"最近一次是在「{last['point']}」这一节：{last.get('break_label') or '没跟上'}。"
                    "还没连成断点，现在补成本最低。"
                    if last.get("point")
                    else f"有 {loose} 节没跟上，但还没连成断点，现在补成本最低。"
                ),
                    "who": t["teacher"],
                    "office_hour": (t.get("teacher_profile") or {}).get("office_hour", ""),
                    "email": (t.get("teacher_profile") or {}).get("email", ""),
                })

    return {
        "courses": tracks,
        "timeline": timeline_rows,
        "due": due,
        "advice": advice[:4],
        "stats": {
            "held": held_all,
            "recorded": recorded_all,
            "coverage": round(recorded_all / held_all, 3) if held_all else 0,
            "open_breaks": open_breaks,
            "fixed_breaks": fixed_breaks,
            "due": len(due),
            "week": week,
            "week_due": len(week_held),
            "week_done": week_done,
            "streak": streak,
            "courses": len([t for t in tracks if t["recorded"]]),
            "today": TODAY.isoformat(),
        },
        "meta": {"week": week, "term": meta.get("term", ""), "persistent": True},
    }
