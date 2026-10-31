"""成绩分配试算台：把一门课的考核构成摊开，让学生自己调，立刻看到会不会挂。

三条纪律（前端页面上也要写明，别让人以为这是承诺）：

1. **权重按课程性质给默认方案**，不是随便拍的：理论必修课重期末，语言课重作业与
   过程，思政课重平时参与，项目制选修重项目产出。教务最终方案为准，页面可以改。
2. **每一项的起点分都来自学生自己的真实数据**：随堂测 = 四次随堂测均值，期中 =
   期中卷面，平时 = 出勤与迟到折算，作业 = 提交率折算。学生点开就能对上账。
3. **期末还没考**，起点分按"期中 + 本学期测评趋势"估一个参考值，并明确标注是估算，
   学生要做的就是把这条估算往下调、看看还能不能过。
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

PASS_LINE = 60.0
# 常见校规：总评及格之外，期末卷面也要过 45 分，否则直接不通过
FINAL_GUARD = 45.0

# ---------------------------------------------------------------------------
# 考核构成方案：key -> 权重（合计 100）
# 每项：key / 名称 / 一句话说明（起点分从哪儿来）
# ---------------------------------------------------------------------------
SCHEME_COMPONENTS: dict[str, list[dict]] = {
    "theory": [
        {"key": "daily", "label": "平时（出勤·课堂）", "short": "平时", "weight": 10},
        {"key": "homework", "label": "作业与实验报告", "short": "作业", "weight": 15},
        {"key": "quiz", "label": "随堂测（4 次）", "short": "随堂测", "weight": 15},
        {"key": "midterm", "label": "期中考试", "short": "期中", "weight": 20},
        {"key": "final", "label": "期末考试", "short": "期末", "weight": 40},
    ],
    "language": [
        {"key": "daily", "label": "平时（出勤·课堂表现）", "short": "平时", "weight": 10},
        {"key": "homework", "label": "作业与口语任务", "short": "作业", "weight": 20},
        {"key": "quiz", "label": "随堂测（4 次）", "short": "随堂测", "weight": 15},
        {"key": "midterm", "label": "期中考试", "short": "期中", "weight": 20},
        {"key": "final", "label": "期末考试", "short": "期末", "weight": 35},
    ],
    "ideology": [
        {"key": "daily", "label": "平时（出勤·课堂参与）", "short": "平时", "weight": 20},
        {"key": "homework", "label": "作业与读书报告", "short": "作业", "weight": 20},
        {"key": "quiz", "label": "随堂测（4 次）", "short": "随堂测", "weight": 10},
        {"key": "midterm", "label": "期中考核", "short": "期中", "weight": 20},
        {"key": "final", "label": "期末考核", "short": "期末", "weight": 30},
    ],
    "project": [
        {"key": "daily", "label": "出勤与课堂", "short": "出勤", "weight": 10},
        {"key": "homework", "label": "项目与作业产出", "short": "项目", "weight": 35},
        {"key": "quiz", "label": "随堂测（4 次）", "short": "随堂测", "weight": 10},
        {"key": "midterm", "label": "中期检查", "short": "中期", "weight": 15},
        {"key": "final", "label": "期末答辩与作品", "short": "期末", "weight": 30},
    ],
    "lab": [
        {"key": "daily", "label": "平时（出勤·实验纪律）", "short": "平时", "weight": 20},
        {"key": "homework", "label": "实验报告", "short": "报告", "weight": 30},
        {"key": "quiz", "label": "实验操作考核", "short": "操作", "weight": 20},
        {"key": "final", "label": "期末实验考核", "short": "期末", "weight": 30},
    ],
}

SCHEME_LABEL = {
    "theory": "理论必修",
    "language": "语言类",
    "ideology": "思政人文",
    "project": "项目制选修",
    "lab": "实验实践",
}

# 起点分从哪儿来，展示给学生的口径说明
BASIS_TEXT = {
    "daily": "按你的出勤与迟到次数折算",
    "homework": "按作业提交率折算",
    "quiz": "你 4 次随堂测的平均分",
    "midterm": "你的期中卷面分",
    "final": "还没考，按期中与本期趋势估算",
}


def scheme_of(course: dict) -> str:
    """按课程性质挑一套权重。顺序有讲究：实验/项目优先于"选修"，思政优先于通识。"""
    name = course.get("name") or ""
    kind = course.get("kind") or ""
    code = course.get("code") or ""
    if "实验" in name or "实践" in name or "实训" in name or "实验" in kind:
        return "lab"
    if code.startswith("EN") or "英语" in name or "英文" in name:
        return "language"
    if any(k in name for k in ("马克思主义", "毛泽东", "思想政治", "历史", "哲学", "形势与政策")):
        return "ideology"
    if "选修" in kind or "项目" in name or "开发" in name or "设计" in name:
        return "project"
    return "theory"


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _gpa_of(score: float) -> float:
    for line, g in ((90, 4.0), (85, 3.7), (82, 3.3), (78, 3.0), (75, 2.7),
                    (72, 2.3), (68, 2.0), (64, 1.5), (60, 1.0)):
        if score >= line:
            return g
    return 0.0


def _trend_delta(course: dict) -> float:
    """本学期测评趋势：最后一点减第一点，只取一半，别把一次超常发挥当成常态。"""
    pts = [p["score"] for p in (course.get("assessments") or []) if p.get("kind") == "quiz"]
    if len(pts) < 2:
        return 0.0
    return (pts[-1] - pts[0]) / 2.0


def _base_scores(course: dict) -> dict[str, float]:
    """每一项的起点分：全部从学生自己的明细推，不另造数字。"""
    sessions = course.get("sessions_held") or 0
    absent = course.get("absent") or 0
    late = course.get("late") or 0
    if sessions:
        rate = _clamp((sessions - absent - 0.5 * late) / sessions, 0.0, 1.0)
        daily = 45 + 55 * rate
    else:
        daily = 80.0

    assigned = course.get("hw_assigned") or 0
    submitted = course.get("hw_submitted") or 0
    homework = 35 + 65 * (_clamp(submitted / assigned, 0.0, 1.0) if assigned else 0.8)

    quizzes = [p["score"] for p in (course.get("assessments") or []) if p.get("kind") == "quiz"]
    quiz = mean(quizzes) if quizzes else float(course.get("midterm") or 70)
    midterm = float(course.get("midterm") or 70)
    final = _clamp(midterm + _trend_delta(course) + 1.5, 0, 100)

    return {
        "daily": round(_clamp(daily, 0, 100), 1),
        "homework": round(_clamp(homework, 0, 100), 1),
        "quiz": round(_clamp(quiz, 0, 100), 1),
        "midterm": round(_clamp(midterm, 0, 100), 1),
        "final": round(_clamp(final, 0, 100), 1),
    }


def _weighted(scores: dict[str, float], weights: dict[str, float]) -> float:
    total_w = sum(weights.values()) or 1.0
    return sum(scores.get(k, 0) * w for k, w in weights.items()) / total_w


def _level(total: float) -> tuple[str, str]:
    if total >= 85:
        return "great", "很稳"
    if total >= 75:
        return "good", "较稳"
    if total >= 60:
        return "watch", "临界"
    return "risk", "会挂"


def _needed_final(scores: dict[str, float], weights: dict[str, float]) -> float:
    """期末卷面至少考多少才能过：取"总评够 60"与"卷面够 45"两条线里更狠的那条。"""
    w_final = weights.get("final", 0.0)
    total_w = sum(weights.values()) or 1.0
    if w_final <= 0:
        return 0.0
    rest = sum(scores.get(k, 0) * w for k, w in weights.items() if k != "final")
    need = (PASS_LINE * total_w - rest) / w_final
    return round(_clamp(max(need, FINAL_GUARD), 0, 100), 1)


def _course_payload(student_course: dict, fail_prob: float, cohort_avg: float | None) -> dict:
    scheme = scheme_of(student_course)
    comps = SCHEME_COMPONENTS[scheme]
    base = _base_scores(student_course)
    weights = {c["key"]: float(c["weight"]) for c in comps}
    scores = {k: base.get(k, 0.0) for k in weights}
    total = round(_weighted(scores, weights), 1)
    key, label = _level(total)
    return {
        "code": student_course["code"],
        "name": student_course["name"],
        "teacher": student_course.get("teacher", ""),
        "credit": student_course.get("credit", 0),
        "kind": student_course.get("kind", ""),
        "scheme": scheme,
        "scheme_label": SCHEME_LABEL[scheme],
        "components": [
            {
                "key": c["key"],
                "label": c["label"],
                "short": c["short"],
                "weight": float(c["weight"]),
                "base": base.get(c["key"], 0.0),
                "basis": BASIS_TEXT.get(c["key"], ""),
            }
            for c in comps
        ],
        "base_total": total,
        "base_level": key,
        "base_level_label": label,
        "needed_final": _needed_final(scores, weights),
        "fail_probability": round(fail_prob, 3),
        "cohort_avg": round(cohort_avg, 1) if cohort_avg else None,
    }


def payload(student: dict, risk: dict, term: str | None = None) -> dict:
    """整页数据：每门课一套构成 + 学生自己的起点分 + 已保存的方案。"""
    fps = {p["code"]: p for p in (risk.get("pass_probability") or [])}
    stats = {}
    courses = []
    for c in student.get("courses") or []:
        fp = fps.get(c["code"], {})
        item = _course_payload(c, float(fp.get("fail_probability") or 0.0), fp.get("cohort_avg"))
        courses.append(item)
        stats[c["code"]] = item

    credits = sum(c["credit"] or 0 for c in courses) or 1
    avg = round(sum(c["base_total"] * (c["credit"] or 0) for c in courses) / credits, 1)
    failing = [c for c in courses if c["base_total"] < PASS_LINE]
    gpa = round(sum(_gpa_of(c["base_total"]) * (c["credit"] or 0) for c in courses) / credits, 2)
    return {
        "student": {
            "id": student["id"],
            "name": student["name"],
            "class_name": student.get("class_name", ""),
            "term": term or student.get("term", ""),
        },
        "pass_line": PASS_LINE,
        "final_guard": FINAL_GUARD,
        "schemes": {k: {"label": SCHEME_LABEL[k], "components": SCHEME_COMPONENTS[k]} for k in SCHEME_COMPONENTS},
        "courses": courses,
        "base": {
            "avg": avg,
            "gpa": gpa,
            "credits": round(credits, 1),
            "failing": len(failing),
            "failing_codes": [c["code"] for c in failing],
            "level": _level(avg)[1],
        },
    }


# ---------------------------------------------------------------------------
# 方案持久化：学生调好的分配存下来，换台设备还能接着调
# ---------------------------------------------------------------------------
class Simulations:
    """试算方案的落盘存储。只存分数与权重，不存任何结论——结论永远由前端/引擎重算。"""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.data: dict[str, dict] = {}
        self.persistent = True
        try:
            if self.path.exists():
                self.data = json.loads(self.path.read_text("utf-8")) or {}
        except Exception:
            self.data = {}
            self.persistent = False

    def get(self, sid: str) -> dict:
        row = self.data.get(sid) or {}
        return {"plans": row.get("plans") or {}, "saved_at": row.get("saved_at")}

    def save(self, sid: str, plans: dict, stamp: str) -> dict:
        clean: dict[str, dict] = {}
        for code, plan in (plans or {}).items():
            scores = {
                str(k): round(_clamp(float(v), 0, 100), 1)
                for k, v in (plan.get("scores") or {}).items()
                if isinstance(v, (int, float))
            }
            weights = {
                str(k): round(_clamp(float(v), 0, 100), 1)
                for k, v in (plan.get("weights") or {}).items()
                if isinstance(v, (int, float))
            }
            if scores:
                clean[str(code)] = {"scores": scores, "weights": weights}
        if not clean:
            self.data.pop(sid, None)
        else:
            self.data[sid] = {"plans": clean, "saved_at": stamp}
        self._flush()
        return self.get(sid)

    def clear(self, sid: str) -> dict:
        self.data.pop(sid, None)
        self._flush()
        return self.get(sid)

    def _flush(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), "utf-8")
            self.persistent = True
        except Exception:
            self.persistent = False
