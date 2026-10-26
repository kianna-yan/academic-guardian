"""成绩走势：把一个人五个学期的分数摆成一条线，并给出能不能看懂的结论。

两条纪律：
1. **口径要对齐**。前四个学期是学期总评，本学期只有期中，两者不能直接比高低；
   所以"趋势"判断只用已完成学期，本学期单独标成"期中"，同时用「班级排名」这个
   跨口径可比的指标兜底 —— 分数降了不一定是退步，班里的位置掉了才是。
2. **图上每个点都能溯源**。每个点都带学期、课程学分、挂科学分、班级均分，
   点一下就能问"这学期为什么掉"。
"""
from __future__ import annotations

from statistics import mean

# 每学期变化多少分算"真的在变"：小于这个幅度更像考试波动
FLAT_BAND = 0.8
COURSE_BAND = 4.0


def _slope(values: list[float]) -> float:
    """最小二乘斜率（分/学期）。比"末减首"稳，个别学期失手不会带偏结论。"""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx, my = mean(xs), mean(values)
    denom = sum((x - mx) ** 2 for x in xs)
    if not denom:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, values)) / denom


def _direction(slope: float) -> str:
    if slope > FLAT_BAND:
        return "up"
    if slope < -FLAT_BAND:
        return "down"
    return "flat"


def _streak(values: list[float]) -> tuple[int, int]:
    """返回 (连续上升期数, 连续下降期数)，都从最后一期往前数。"""
    up = down = 0
    for i in range(len(values) - 1, 0, -1):
        diff = values[i] - values[i - 1]
        if diff > FLAT_BAND and down == 0:
            up += 1
        elif diff < -FLAT_BAND and up == 0:
            down += 1
        else:
            break
    return up, down


def _trend_label(slope: float, up: int, down: int) -> str:
    if slope > FLAT_BAND:
        return f"连续 {up} 个学期上升" if up >= 2 else "上学期回升"
    if slope < -FLAT_BAND:
        return f"连续 {down} 个学期下滑" if down >= 2 else "上学期下滑"
    return "成绩基本持平"


def grade_trend(student: dict) -> dict:
    """完整走势：五个学期的点 + 本学期每门课的测评序列 + 一句结论。"""
    terms = student.get("grade_history") or []
    courses = student.get("courses") or []
    if not terms:
        return {"terms": [], "courses": [], "slope": {}, "summary": "", "watch": ""}

    finals = [t for t in terms if t["status"] == "final"]
    f_avgs = [t["avg"] for t in finals]
    slope = round(_slope(f_avgs), 2)
    direction = _direction(slope)
    up, down = _streak(f_avgs)

    first = terms[0]
    last = terms[-1]
    rank_delta = (last["rank"] - first["rank"]) if last.get("rank") and first.get("rank") else 0
    gap = round(last["avg"] - last["cohort_avg"], 1) if last.get("cohort_avg") else 0.0

    # ---- 本学期每门课的测评序列 ----
    course_rows = []
    for c in courses:
        pts = c.get("assessments") or []
        if not pts:
            continue
        scores = [p["score"] for p in pts]
        delta = scores[-1] - scores[0]
        if delta >= COURSE_BAND:
            c_dir, c_label = "up", "越考越好"
        elif delta <= -COURSE_BAND:
            c_dir, c_label = "down", "一路走低"
        else:
            c_dir, c_label = "flat", "基本稳定"
        course_rows.append({
            "code": c["code"],
            "name": c["name"],
            "teacher": c["teacher"],
            "credit": c["credit"],
            "midterm": c["midterm"],
            "cohort_avg": None,          # 由调用方补，避免这里重复算全校统计
            "points": pts,
            "first": scores[0],
            "last": scores[-1],
            "delta": delta,
            "best": max(scores),
            "worst": min(scores),
            "trend": c_dir,
            "trend_label": c_label,
        })
    course_rows.sort(key=lambda r: r["midterm"])

    # ---- 结论句：先给分数，再给班级位置，最后给一句人话 ----
    head = (
        f"大一上 {first['avg']:.1f} 分（班级第 {first['rank']} 名）→ "
        f"本学期期中 {last['avg']:.1f} 分（第 {last['rank']} 名）"
    )
    move = "后退" if rank_delta > 0 else "前进"
    if direction == "down":
        verdict = (
            f"分数在下行通道里，班级名次{move} {abs(rank_delta)} 名"
            if rank_delta > 0
            else "分数在下滑，但班级名次没退，这次更像是全班普遍失手"
        )
    elif direction == "up":
        verdict = (
            f"分数在上行通道里，班级名次{move} {abs(rank_delta)} 名"
            if rank_delta < 0
            else "分数在上升，但同伴涨得更快，名次没跟上"
        )
    elif rank_delta > 2:
        # 历史学期分数没动、但本学期名次明显后退 —— 这种"新出现的变化"最该被看见
        verdict = f"前几个学期分数基本走平，但本学期期中名次后退 {rank_delta} 名，是新出现的变化"
    elif rank_delta < -2:
        verdict = f"前几个学期分数基本走平，本学期期中名次前进了 {-rank_delta} 名"
    else:
        verdict = "分数和名次都稳住了"

    worst = course_rows[0] if course_rows else None
    watch = ""
    if worst:
        watch = (
            f"{worst['name']}是本学期最弱的一门（期中 {worst['midterm']} 分，"
            f"四次测评从 {worst['first']} 到 {worst['last']} 分），"
            f"任课教师 {worst['teacher']}"
        )

    return {
        "terms": terms,
        "courses": course_rows,
        "slope": {
            "per_term": slope,
            "total": round(f_avgs[-1] - f_avgs[0], 1),
            "direction": direction,
            "label": _trend_label(slope, up, down),
            "up_streak": up,
            "down_streak": down,
            "first_label": first["label"],
            "last_final_label": finals[-1]["label"] if finals else "",
        },
        "now": {
            "avg": last["avg"],
            "cohort_avg": last.get("cohort_avg"),
            "gap": gap,
            "rank": last.get("rank"),
            "rank_total": last.get("rank_total"),
            "status": last["status"],
            "note": last.get("note", ""),
        },
        "rank": {
            "from": first.get("rank"),
            "to": last.get("rank"),
            "delta": rank_delta,          # 正数 = 名次后退（变差）
            "total": last.get("rank_total"),
        },
        "summary": f"{head}。{verdict}。",
        "watch": watch,
        "worst_code": worst["code"] if worst else "",
    }


def roster_extra(student: dict) -> dict:
    """名单里用的极简版：一串折线点 + 名次变化，够画一个 sparkline 就行。

    240 人名单不可能每行挂一个图表实例，所以这里只给 5 个数字，前端用纯 SVG 画。
    """
    terms = student.get("grade_history") or []
    if not terms:
        return {
            "trend_points": [],
            "trend_rank_delta": 0,
            "trend_rank": None,
            "trend_rank_total": None,
            "trend_direction": "flat",
            "trend_label": "",
        }
    points = [t["avg"] for t in terms]
    first, last = terms[0], terms[-1]
    rank_delta = (last["rank"] - first["rank"]) if last.get("rank") and first.get("rank") else 0
    finals = [t["avg"] for t in terms if t["status"] == "final"]
    slope = _slope(finals) if len(finals) >= 2 else 0.0
    up, down = _streak(finals) if len(finals) >= 2 else (0, 0)

    # 名单上的颜色/箭头由**名次**决定，而不是分数：名次是跨口径可比的，
    # 分数会受"期中本来就比总评低几分"的影响。名次没怎么动时才回退到分数斜率。
    direction, label = _direction(slope), _trend_label(slope, up, down)
    if rank_delta >= 4:
        direction, label = "down", f"名次后退 {rank_delta} 名"
    elif rank_delta <= -4:
        direction, label = "up", f"名次前进 {-rank_delta} 名"

    return {
        "trend_points": points,
        "trend_rank_delta": rank_delta,
        "trend_rank": last.get("rank"),
        "trend_rank_total": last.get("rank_total"),
        "trend_direction": direction,
        "trend_label": label,
    }
