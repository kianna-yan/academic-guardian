"""学业风险评分引擎。

设计原则：
1. 分数必须能拆开——每个风险因素单独贡献多少分，学生和家长要看得懂；
2. 阈值可配置——不同学校的预警线不一样，教务端能改；
3. 硬规则优先——期中挂科两门以上这类红线，不允许被加权平均稀释掉。
"""
from __future__ import annotations

import math
from statistics import mean, pstdev

from engine import advice, trend as trend_mod

DEFAULT_CONFIG = {
    "red_line": 55,
    "yellow_line": 35,
    "weights": {
        "attendance": 0.26,
        "homework": 0.20,
        "exam": 0.20,
        "engagement": 0.12,
        "history": 0.12,
        "credit": 0.10,
    },
    "policy": {
        "warn_failed_credits": 15,
        "downgrade_failed_credits": 25,
        "absence_warn_ratio": 0.25,
        "midterm_fail_trigger": 2,
    },
}

FACTOR_LABELS = {
    "attendance": "课堂出勤",
    "homework": "作业提交",
    "exam": "期中成绩",
    "engagement": "学习投入",
    "history": "历史欠账",
    "credit": "学分进度",
}

LEVELS = {
    "red": {"label": "红色预警", "tone": "danger"},
    "yellow": {"label": "黄色关注", "tone": "warning"},
    "green": {"label": "状态正常", "tone": "success"},
}


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _logistic(x: float) -> float:
    return 1 / (1 + math.exp(-x))


class RiskEngine:
    def __init__(self, dataset: dict, config: dict | None = None):
        self.students = dataset["students"]
        self.config = config or DEFAULT_CONFIG
        self.course_stats = self._course_stats()
        self._by_id = {s["id"]: s for s in self.students}

    # ---------- 基础统计 ----------
    def _course_stats(self) -> dict:
        stats = {}
        for c in self.students[0]["courses"]:
            scores = [next(x for x in s["courses"] if x["code"] == c["code"])["midterm"] for s in self.students]
            stats[c["code"]] = {
                "mean": round(mean(scores), 1),
                "std": round(pstdev(scores), 1) or 1.0,
                "name": c["name"],
                "credit": c["credit"],
            }
        return stats

    def get(self, sid: str) -> dict:
        return self._by_id[sid]

    def teacher_view(self, teacher_name: str) -> dict:
        """任课教师视角的数据：他教的课 + 上这些课的学生（每生只带该老师课的明细 + 风险分）。"""
        my_courses: list[dict] = []
        seen = set()
        student_rows: list[dict] = []
        for s in self.students:
            my_cs = [c for c in s["courses"] if c.get("teacher") == teacher_name]
            if not my_cs:
                continue
            for c in my_cs:
                if c["code"] not in seen:
                    seen.add(c["code"])
                    my_courses.append({k: c.get(k) for k in
                                       ("code", "name", "credit", "kind", "period", "teacher")})
            try:
                r = self.score(s["id"])
                score, level, level_label = r["score"], r["level"], r["level_label"]
                factors = r["factors"][:3]
            except Exception:
                score, level, level_label, factors = 0, "green", "正常", []
            # 每门课只保留该老师课的考勤/作业/期中明细
            courses_brief = [{
                "code": c["code"], "name": c["name"], "midterm": c.get("midterm"),
                "absent": c.get("absent", 0), "late": c.get("late", 0),
                "sessions_held": c.get("sessions_held", 0),
                "hw_submitted": c.get("hw_submitted", 0), "hw_assigned": c.get("hw_assigned", 0),
                "cohort_avg": self.course_stats.get(c["code"], {}).get("mean"),
                "attendance": c.get("attendance", []),
                "homework": c.get("homework", []),
            } for c in my_cs]
            student_rows.append({
                "id": s["id"], "name": s["name"], "class_name": s["class_name"],
                "score": score, "level": level, "level_label": level_label,
                "top_factor": factors[0]["label"] if factors else "",
                "courses": courses_brief,
            })
        # 按风险分降序，红色优先
        student_rows.sort(key=lambda r: -r["score"])
        return {"teacher": teacher_name, "courses": my_courses, "students": student_rows}

    # ---------- 单因素计算 ----------
    def _factors(self, s: dict) -> dict:
        courses = s["courses"]
        total_sessions = sum(c["sessions_held"] for c in courses)
        total_absent = sum(c["absent"] for c in courses)
        absence_ratio = total_absent / total_sessions if total_sessions else 0
        f_attendance = _clamp(absence_ratio / 0.26)

        assigned = sum(c["hw_assigned"] for c in courses)
        submitted = sum(c["hw_submitted"] for c in courses)
        miss_ratio = 1 - submitted / assigned if assigned else 0
        f_homework = _clamp(miss_ratio / 0.38)

        credits = sum(c["credit"] for c in courses)
        my_avg = sum(c["midterm"] * c["credit"] for c in courses) / credits
        expected = sum(self.course_stats[c["code"]]["mean"] * c["credit"] for c in courses) / credits
        z = sum(
            (c["midterm"] - self.course_stats[c["code"]]["mean"]) / self.course_stats[c["code"]]["std"] * c["credit"]
            for c in courses
        ) / credits
        f_exam = _clamp(0.5 * (82 - my_avg) / 36 + 0.5 * (-z) / 1.6)

        e = s["engagement"]
        login_part = 1 - min(1.0, e["weekly_logins"] / 12)
        video_part = 1 - e["video_rate"]
        idle_part = min(1.0, e["days_since_active"] / 14)
        f_engagement = _clamp(0.35 * login_part + 0.35 * video_part + 0.30 * idle_part)

        h = s["history"]
        f_history = _clamp(0.6 * min(1.0, h["failed_credits"] / 12) + 0.4 * _clamp((3.2 - h["gpa"]) / 1.6))

        expected_earned = 105
        deficit = max(0, expected_earned - s["credits"]["earned"])
        f_credit = _clamp(deficit / 12)

        return {
            "attendance": f_attendance,
            "homework": f_homework,
            "exam": f_exam,
            "engagement": f_engagement,
            "history": f_history,
            "credit": f_credit,
            "_raw": {
                "absence_ratio": round(absence_ratio, 3),
                "absent": total_absent,
                "sessions": total_sessions,
                "miss_ratio": round(miss_ratio, 3),
                "hw_submitted": submitted,
                "hw_assigned": assigned,
                "mid_avg": round(my_avg, 1),
                "cohort_avg": round(expected, 1),
                "z": round(z, 2),
                "credits_deficit": deficit,
            },
        }

    # ---------- 风险评分 ----------
    def score(self, sid: str) -> dict:
        s = self.get(sid)
        f = self._factors(s)
        w = self.config["weights"]
        parts = []
        total = 0.0
        for key, weight in w.items():
            contribution = 100 * weight * f[key]
            total += contribution
            parts.append({
                "key": key,
                "label": FACTOR_LABELS[key],
                "value": round(f[key], 3),
                "weight": weight,
                "points": round(contribution, 1),
            })
        parts.sort(key=lambda p: -p["points"])

        midterm_fails = [c for c in s["courses"] if c["midterm"] < 60]
        raw_score = total
        overrides = []
        pol = self.config["policy"]
        if len(midterm_fails) >= pol["midterm_fail_trigger"]:
            floor = self.config["red_line"] + 1
            if total < floor:
                overrides.append(f"期中已有 {len(midterm_fails)} 门不及格，触发硬性红线")
                total = floor
        if f["_raw"]["absence_ratio"] >= pol["absence_warn_ratio"]:
            floor = self.config["yellow_line"] + 15
            if total < floor:
                overrides.append(f"缺勤率 {f['_raw']['absence_ratio']:.0%} 超过 {pol['absence_warn_ratio']:.0%} 警戒线")
                total = floor
        if s["history"]["failed_credits"] >= pol["downgrade_failed_credits"]:
            if total < 80:
                overrides.append(f"累计不及格学分 {s['history']['failed_credits']} 已接近降级试读线")
                total = 80

        total = round(min(100, total), 1)
        if total >= self.config["red_line"]:
            level = "red"
        elif total >= self.config["yellow_line"]:
            level = "yellow"
        else:
            level = "green"

        return {
            "student_id": s["id"],
            "score": total,
            "raw_score": round(raw_score, 1),
            "level": level,
            "level_label": LEVELS[level]["label"],
            "factors": parts,
            "raw": f["_raw"],
            "overrides": overrides,
            "trend": self._trend(s, total),
            "pass_probability": self._pass_probability(s),
        }

    def _trend(self, s: dict, current: float) -> dict:
        h = s["history"]
        # 上学期没有过程性数据，用 GPA 与不及格学分折算一个可比的风险分
        last = 100 * (0.55 * _clamp((3.6 - h["gpa"]) / 2.2) + 0.45 * _clamp(h["failed_credits"] / 15))
        last = round(last, 1)
        delta = round(current - last, 1)
        if delta > 8:
            label, direction = "快速上升", "up"
        elif delta > 2:
            label, direction = "略有上升", "up"
        elif delta < -8:
            label, direction = "明显下降", "down"
        elif delta < -2:
            label, direction = "略有下降", "down"
        else:
            label, direction = "基本持平", "flat"
        return {"last_score": last, "delta": delta, "label": label, "direction": direction}

    def _pass_probability(self, s: dict) -> list[dict]:
        out = []
        for c in s["courses"]:
            stat = self.course_stats[c["code"]]
            z = (c["midterm"] - stat["mean"]) / stat["std"]
            miss = 1 - c["hw_submitted"] / c["hw_assigned"] if c["hw_assigned"] else 0
            absence = c["absent"] / c["sessions_held"]
            x = 1.35 * z - 2.2 * miss - 3.0 * absence - 0.6
            fail_prob = _logistic(-x)
            out.append({
                "code": c["code"],
                "name": c["name"],
                "midterm": c["midterm"],
                "cohort_avg": stat["mean"],
                "fail_probability": round(fail_prob, 3),
            })
        out.sort(key=lambda x: -x["fail_probability"])
        return out

    # ---------- 干预建议 ----------
    def interventions(self, sid: str) -> list[dict]:
        """个性化干预动作。具体生成逻辑在 engine/advice.py（按成因分型 + 引用证据）。

        这里保留旧签名，是因为信件生成、学生端清单、接口都在用它；
        返回值仍是 [{factor,title,detail,owner,deadline,priority}]，
        另外附带 tag/steps/points，新前端可以直接用，旧调用方忽略即可。
        """
        return advice.plan(self, sid)["actions"]

    def advice(self, sid: str, score: dict | None = None) -> dict:
        """完整方案：判断、证据、动作、可调用资源、复查点。"""
        return advice.plan(self, sid, score)

    # ---------- 班级 / 全校聚合 ----------
    def roster(self, class_name: str | None = None, level: str | None = None) -> list[dict]:
        rows = []
        for s in self.students:
            if class_name and s["class_name"] != class_name:
                continue
            r = self.score(s["id"])
            if level and r["level"] != level:
                continue
            tip = advice.brief(self, s["id"], r)
            rows.append({
                "id": s["id"],
                "name": s["name"],
                "class_name": s["class_name"],
                "gender": s["gender"],
                "score": r["score"],
                "level": r["level"],
                "level_label": r["level_label"],
                "delta": r["trend"]["delta"],
                "direction": r["trend"]["direction"],
                "top_factor": r["factors"][0]["label"],
                "absent": r["raw"]["absent"],
                "missed_hw": r["raw"]["hw_assigned"] - r["raw"]["hw_submitted"],
                "mid_avg": r["raw"]["mid_avg"],
                "advisor": s["advisor"],
                "pattern": tip["pattern"],
                "pattern_label": tip["pattern_label"],
                "advice": tip["line"],
                "advice_tag": tip["tag"],
                # 名单上每行一条迷你走势线：五学期的均分 + 名次变化
                **trend_mod.roster_extra(s),
            })
        rows.sort(key=lambda x: -x["score"])
        return rows

    def overview(self) -> dict:
        rows = self.roster()
        n = len(rows)
        dist = {"red": 0, "yellow": 0, "green": 0}
        for r in rows:
            dist[r["level"]] += 1
        by_class = {}
        for c in sorted({r["class_name"] for r in rows}):
            sub = [r for r in rows if r["class_name"] == c]
            by_class[c] = {
                "total": len(sub),
                "red": sum(1 for r in sub if r["level"] == "red"),
                "yellow": sum(1 for r in sub if r["level"] == "yellow"),
                "avg_score": round(sum(r["score"] for r in sub) / len(sub), 1),
            }
        factor_pressure = {}
        for s in self.students:
            for p in self.score(s["id"])["factors"]:
                factor_pressure[p["label"]] = factor_pressure.get(p["label"], 0) + p["points"]
        top_factors = sorted(
            [{"label": k, "points": round(v / n, 1)} for k, v in factor_pressure.items()],
            key=lambda x: -x["points"],
        )
        rising = [r for r in rows if r["direction"] == "up" and r["level"] != "green"]
        return {
            "total": n,
            "dist": dist,
            "dist_pct": {k: round(v / n * 100, 1) for k, v in dist.items()},
            "by_class": by_class,
            "top_factors": top_factors,
            "rising_count": len(rising),
            "avg_score": round(sum(r["score"] for r in rows) / n, 1),
            "updated_at": "2026-10-21",
        }
