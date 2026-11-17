"""每日预警日报：聚合全校数据，产出结构化报告（供定时任务、对话问答、Word 导出、PPT 复用）。

设计原则
- 一次聚合多处消费：定时任务落库、对话里直接问「今日日报」、
  exporter 导出 Word、semester_pptx 取数，全部吃这一个函数的输出。
- summary 是「一句人话」：早会时辅导员不用读全篇也知道今天最要紧的事。
"""
from __future__ import annotations

from datetime import datetime


def daily_report(engine, interventions: dict, week: int | str = "-") -> dict:
    """聚合全校当前态势。engine: RiskEngine；interventions: {sid: [items]}。"""
    o = engine.overview()
    rows = engine.roster(None, None)  # 全量，已按风险分排序
    red = [x for x in rows if x["level"] == "red"]
    yellow = [x for x in rows if x["level"] == "yellow"]
    rising = sorted([x for x in rows if x["direction"] == "up"],
                    key=lambda x: -x["delta"])[:6]
    improved = [x for x in rows if x["direction"] == "down"]
    iv_total = sum(len(v) for v in interventions.values())
    today = datetime.now().strftime("%Y-%m-%d")

    by_class = sorted(o["by_class"].items(), key=lambda kv: -kv[1]["red"])[:3]
    red_pct = round(100 * dist_pct(o, "red"), 1)

    # 一句人话：今天最要紧的事
    if rising and red:
        focus = rising[0]
        summary = (f"今天最要紧的事：{focus['name']}（{focus['class_name']}）风险分较上学期"
                   f"{focus['delta']:+.0f} 分、升至 {focus['score']} 分，还没转红，建议今天约谈。")
    elif red:
        summary = f"红色预警 {len(red)} 人，最集中的是{by_class[0][0]}（{by_class[0][1]['red']} 人）。"
    else:
        summary = "当前无红色预警学生，重点转为关注上升名单。"

    body_md = [
        f"### 全校态势",
        f"- 在册 {o['total']} 人：红色预警 **{len(red)}** 人（{red_pct}%），黄色关注 **{len(yellow)}** 人，平均风险分 {o['avg_score']}",
        f"- 风险回落 {len(improved)} 人，上升 {len(rising)} 人，已累计干预 {iv_total} 次",
    ]
    if by_class:
        body_md.append("- 红色最集中的班级：" + "、".join(f"{k}（{v['red']} 人）" for k, v in by_class))
    body_md += ["", f"### 今日重点关注（上升最快）"]
    body_md += [f"- {x['name']}（{x['class_name']}）风险分 {x['score']}，较上学期 {x['delta']:+.0f} 分，主因 {x['top_factor']}"
                for x in rising] or ["- 当前无风险上升学生"]
    body_md += ["", f"### 红色预警名单（前 6）"]
    body_md += [f"- {x['name']}（{x['class_name']}）{x['score']} 分 · {x['pattern_label']}" for x in red[:6]] or ["- 无"]
    body_md += ["", "### 建议动作"]
    body_md += [
        "1. 上升名单里还没转红的学生，本周完成一轮约谈；",
        "2. 红色预警学生的帮扶方案执行情况，本周五复查；",
        "3. 需要家校配合的，直接说「把家长信发给 XX 的家长」。",
    ]

    return {
        "date": today,
        "week": week,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "overview": o,
        "red_pct": red_pct,
        "red_top": red[:6],
        "rising": rising,
        "improved_total": len(improved),
        "interventions_total": iv_total,
        "by_class_top": [{"class": k, **v} for k, v in by_class],
        "summary": summary,
        "body": "\n".join(body_md),
    }


def dist_pct(o: dict, level: str) -> float:
    total = max(o["total"], 1)
    return o["dist"].get(level, 0) / total


def teacher_report(engine, teacher_name: str, week: int | str = "-") -> dict:
    """任课教师视角的汇报：只统计「他课上」的学生，不把全校数字塞给老师。

    教务/导员的口径是全校与全班，教师的口径是「我教的这几门课、我班上的学生」，
    所以这里不复用 daily_report 的 overview，而是按 teacher_view 的名单重新聚合：
    - 名单与课程取自 engine.teacher_view（同一处口径，不会和教师端首页对不上）；
    - 风险分、等级、上升幅度取 roster 的行，字段与日报完全一致，
      这样 semester_pptx / daily_report_docx / PDF 三套排版可以原样复用；
    - 正文措辞改成第一人称的任课教师口吻。
    """
    from datetime import datetime

    tv = engine.teacher_view(teacher_name)
    ids = {s["id"] for s in (tv.get("students") or [])}
    rows = [r for r in engine.roster(None, None) if r["id"] in ids]
    courses = tv.get("courses") or []

    n = len(rows)
    dist = {"red": 0, "yellow": 0, "green": 0}
    for r in rows:
        if r["level"] in dist:
            dist[r["level"]] += 1
    by_class: dict[str, dict] = {}
    for r in rows:
        c = r.get("class_name") or "-"
        slot = by_class.setdefault(c, {"total": 0, "red": 0, "yellow": 0, "avg_score": 0.0})
        slot["total"] += 1
        slot["red"] += 1 if r["level"] == "red" else 0
        slot["yellow"] += 1 if r["level"] == "yellow" else 0
        slot["avg_score"] += r["score"]
    for slot in by_class.values():
        slot["avg_score"] = round(slot["avg_score"] / max(slot["total"], 1), 1)

    pressure: dict[str, float] = {}
    for r in rows:
        try:
            for p in engine.score(r["id"])["factors"]:
                pressure[p["label"]] = pressure.get(p["label"], 0) + p["points"]
        except Exception:  # noqa: BLE001
            continue
    top_factors = sorted(
        [{"label": k, "points": round(v / max(n, 1), 1)} for k, v in pressure.items()],
        key=lambda x: -x["points"],
    )

    red = [x for x in rows if x["level"] == "red"]
    yellow = [x for x in rows if x["level"] == "yellow"]
    rising = sorted([x for x in rows if x["direction"] == "up"], key=lambda x: -x["delta"])[:6]
    improved = [x for x in rows if x["direction"] == "down"]
    avg_score = round(sum(r["score"] for r in rows) / n, 1) if n else 0

    overview = {
        "total": n,
        "dist": dist,
        "dist_pct": {k: round(v / max(n, 1) * 100, 1) for k, v in dist.items()},
        "by_class": by_class,
        "top_factors": top_factors,
        "rising_count": len(rising),
        "avg_score": avg_score,
        "teacher": teacher_name,
    }
    red_pct = round(100 * dist["red"] / max(n, 1), 1)
    today = datetime.now().strftime("%Y-%m-%d")
    course_names = "、".join(f"{c.get('name')}" for c in courses[:4]) or "本学期的课"

    if rising and red:
        f0 = rising[0]
        summary = (f"我课上最要紧的是 {f0['name']}（{f0['class_name']}）：风险分 {f0['score']} 分，"
                   f"较上学期 {f0['delta']:+.0f} 分，还没转红，这周得找ta聊一次。")
    elif red:
        summary = f"我课上有 {len(red)} 人已经红标，先盯课堂出勤和作业缺交这两条。"
    else:
        summary = "我课上暂时没有红标学生，重点看上升名单。"

    body = [
        "### 我课上的整体情况",
        f"- 任课：{course_names}；学生 {n} 人"
        f"（红标 {dist['red']} 人 / 黄标 {dist['yellow']} 人），平均风险分 {avg_score}",
        f"- 风险回落 {len(improved)} 人，上升 {len(rising)} 人",
    ]
    if by_class:
        body.append("- 按班分布：" + "、".join(
            f"{k}（{v['red']} 红 / 共 {v['total']} 人）" for k, v in by_class.items()))
    if top_factors:
        body.append("- 主要风险来源：" + "、".join(
            f"{x['label']}（{x['points']} 分）" for x in top_factors[:3]))
    body += ["", "### 需要先聊的（风险上升）"]
    body += [f"- {x['name']}（{x['class_name']}）风险分 {x['score']}，较上学期 {x['delta']:+.0f} 分，主因 {x['top_factor']}"
             for x in rising] or ["- 当前无风险上升学生"]
    body += ["", "### 红标名单"]
    body += [f"- {x['name']}（{x['class_name']}）{x['score']} 分 · {x['pattern_label']}"
             for x in red[:8]] or ["- 无"]
    body += ["", "### 课堂上的三个动作"]
    body += [
        "1. 出勤率低于 75% 的，下次课上点名后单独留两分钟；",
        "2. 作业缺交 2 次以上的，当堂提醒并在课后补交；",
        "3. 需要辅导员/家长一起管的，把名单交给辅导员跟进。",
    ]

    return {
        "date": today,
        "week": week,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "overview": overview,
        "red_pct": red_pct,
        "red_top": red[:6],
        "rising": rising,
        "improved_total": len(improved),
        "interventions_total": len(tv.get("students") or []),
        "by_class_top": [{"class": k, **v} for k, v in
                         sorted(by_class.items(), key=lambda kv: -kv[1]["red"])[:3]],
        "summary": summary,
        "body": "\n".join(body),
        "scope": "teacher",
        "teacher": teacher_name,
        "courses": courses,
    }
