"""模拟学情数据源。

真实项目里这一层对接教务系统 / 学习平台 / 一卡通，这里用确定性随机生成，
保证每次启动看到的是同一批学生，方便演示和答辩复现。
"""
from __future__ import annotations

import random
from datetime import date, timedelta

SEED = 20261018
TODAY = date(2026, 10, 21)

CLASSES = ["计科2401", "计科2402", "计科2403", "计科2404", "计科2405", "计科2406"]

SURNAMES = list("王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦方白邹孟熊秦邱江尹薛段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤")
GIVEN_M = ["浩然", "子轩", "宇航", "俊杰", "明轩", "志强", "文博", "嘉豪", "天宇", "泽宇",
           "一鸣", "梓豪", "瑞霖", "思远", "皓宇", "昊天", "博文", "晨阳", "子墨", "家豪",
           "永康", "伟诚", "锦程", "立轩", "承泽", "书豪", "若飞", "亦辰", "沐阳", "少卿"]
GIVEN_F = ["雨欣", "梦琪", "佳怡", "思彤", "欣怡", "语嫣", "子涵", "梓萱", "嘉琪", "若曦",
           "雨桐", "晓彤", "诗涵", "一诺", "婉清", "静怡", "佳宁", "可欣", "雅涵", "沐瑶",
           "思远", "明月", "静姝", "佩瑶", "婉如", "语晨", "亦菲", "舒雅", "书瑶", "清越"]

# 2026 秋季学期（第 8 教学周）
COURSES = [
    {"code": "CS201", "name": "数据结构", "credit": 4, "kind": "必修", "teacher": "周立群", "period": "周一 1-2 节", "weeks": 16},
    {"code": "CS203", "name": "计算机组成原理", "credit": 4, "kind": "必修", "teacher": "何建平", "period": "周二 3-4 节", "weeks": 16},
    {"code": "MA204", "name": "概率论与数理统计", "credit": 3, "kind": "必修", "teacher": "宋雅琴", "period": "周三 1-2 节", "weeks": 16},
    {"code": "EN203", "name": "大学英语 III", "credit": 2, "kind": "必修", "teacher": "Linda Chen", "period": "周四 5-6 节", "weeks": 16},
    {"code": "PE201", "name": "马克思主义基本原理", "credit": 3, "kind": "必修", "teacher": "吴国强", "period": "周五 3-4 节", "weeks": 16},
    {"code": "CS215", "name": "Python Web 开发", "credit": 2, "kind": "选修", "teacher": "林澈", "period": "周三 7-8 节", "weeks": 12},
]

SESSIONS_HELD = 14          # 已上课次数
SESSIONS_TOTAL = 16
HOMEWORK_ASSIGNED = 6       # 已布置作业数
HOMEWORK_TOTAL = 8


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _gauss(rng: random.Random, mu: float, sigma: float) -> float:
    return rng.gauss(mu, sigma)


def _build_students() -> list[dict]:
    rng = random.Random(SEED)
    students: list[dict] = []
    used_names: set[str] = set()
    sid = 0
    for cls in CLASSES:
        for _ in range(40):
            sid += 1
            gender = "男" if rng.random() < 0.68 else "女"
            pool = GIVEN_M if gender == "男" else GIVEN_F
            while True:
                name = rng.choice(SURNAMES) + rng.choice(pool)
                if name not in used_names:
                    used_names.add(name)
                    break
            ability = _clamp(_gauss(rng, 74, 11), 38, 97)
            diligence = _clamp(_gauss(rng, 0.70, 0.17), 0.18, 1.0)
            # 少数学生会出现"能力不错但完全不投入"的组合，这是预警真正要抓的
            if rng.random() < 0.05:
                ability = _clamp(ability + 10, 38, 97)
                diligence = _clamp(diligence - 0.35, 0.08, 0.6)

            students.append({
                "id": f"2024{sid:04d}",
                "name": name,
                "gender": gender,
                "class_name": cls,
                "major": "计算机科学与技术",
                "grade": "2024级",
                "enroll_year": 2024,
                "advisor": "陈静" if cls.endswith(("01", "02", "03")) else "刘畅",
                "ability": round(ability, 2),
                "diligence": round(diligence, 2),
                "_rng": rng,
            })
    return students


def _semester_history(rng: random.Random, ability: float, diligence: float) -> dict:
    """上学期（2025-2026 春）成绩，用于趋势对比。"""
    base = 0.45 * (ability / 100) + 0.55 * diligence
    gpa = _clamp(_gauss(rng, 0.6 + base * 3.3, 0.32), 0.6, 4.0)
    failed = 0
    if gpa < 1.6:
        failed = rng.choice([9, 12, 15, 18])
    elif gpa < 2.2:
        failed = rng.choice([3, 4, 6])
    elif gpa < 2.8 and rng.random() < 0.25:
        failed = rng.choice([2, 3])
    return {
        "term": "2025-2026 春",
        "gpa": round(gpa, 2),
        "failed_credits": failed,
        "credits_earned": 24 + rng.choice([0, 0, 0, 2, 4]),
        "credits_plan": 26,
    }


def _course_state(rng: random.Random, ability: float, diligence: float, course: dict) -> dict:
    quality = 0.55 * (ability / 100) + 0.45 * diligence
    hard = 0.06 if course["code"] in {"CS201", "CS203", "MA204"} else 0.0
    midterm = _clamp(_gauss(rng, 46 + quality * 52 - hard * 100, 8.5), 16, 99)

    absent = 0
    late = 0
    p_abs = _clamp((1 - diligence) * 0.34, 0.0, 0.55)
    for _ in range(SESSIONS_HELD):
        r = rng.random()
        if r < p_abs:
            absent += 1
        elif r < p_abs + 0.07:
            late += 1

    p_miss = _clamp((1 - diligence) * 0.42, 0.0, 0.62)
    hw_submitted = sum(1 for _ in range(HOMEWORK_ASSIGNED) if rng.random() > p_miss)
    quizzes = [round(_clamp(_gauss(rng, 42 + quality * 50, 10), 10, 100)) for _ in range(2)]

    return {
        "code": course["code"],
        "name": course["name"],
        "credit": course["credit"],
        "kind": course["kind"],
        "teacher": course["teacher"],
        "period": course["period"],
        "midterm": round(midterm),
        "quizzes": quizzes,
        "absent": absent,
        "late": late,
        "sessions_held": SESSIONS_HELD,
        "hw_submitted": hw_submitted,
        "hw_assigned": HOMEWORK_ASSIGNED,
    }


def _engagement(rng: random.Random, diligence: float) -> dict:
    weekly_logins = max(0, round(_gauss(rng, 3 + diligence * 9, 2.2)))
    video_rate = _clamp(_gauss(rng, 0.32 + diligence * 0.6, 0.13), 0.02, 1.0)
    library_visits = max(0, round(_gauss(rng, diligence * 10 - 1, 3)))
    last_active_days = max(0, round(_gauss(rng, 9 - diligence * 8, 3.5)))
    return {
        "weekly_logins": weekly_logins,
        "video_rate": round(video_rate, 2),
        "library_visits": library_visits,
        "days_since_active": last_active_days,
    }


def build_dataset() -> dict:
    rng = random.Random(SEED)
    raw = _build_students()
    students: list[dict] = []
    for s in raw:
        sub = random.Random(SEED + int(s["id"][-4:]))
        history = _semester_history(sub, s["ability"], s["diligence"])
        courses = [_course_state(sub, s["ability"], s["diligence"], c) for c in COURSES]
        engagement = _engagement(sub, s["diligence"])
        # 已修学分：大三上应修 105（前四学期 + 本学期在修）
        plan_total = 165
        earned = 79 + history["credits_earned"] - history["failed_credits"]
        students.append({
            "id": s["id"],
            "name": s["name"],
            "gender": s["gender"],
            "class_name": s["class_name"],
            "major": s["major"],
            "grade": s["grade"],
            "advisor": s["advisor"],
            "phone_tail": f"{int(s['id'][-4:]) % 10000:04d}",
            "history": history,
            "courses": courses,
            "engagement": engagement,
            "credits": {
                "earned": max(0, earned),
                "in_progress": sum(c["credit"] for c in courses),
                "plan_total": plan_total,
            },
            "term": "2026-2027 秋",
            "week": 8,
        })
    return {
        "students": students,
        "courses": COURSES,
        "classes": CLASSES,
        "term": "2026-2027 秋",
        "week": 8,
        "updated_at": TODAY.isoformat(),
    }


_DB: dict | None = None


def db() -> dict:
    global _DB
    if _DB is None:
        _DB = build_dataset()
    return _DB
