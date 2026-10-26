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
