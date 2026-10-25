"""文书生成：告知函、家长信、谈话要点、班级周报。

模板保证结构合规（事实 → 依据 → 要求 → 复查节点），
接入大模型后可在模板骨架上改写措辞，但不改变事实字段。
"""
from __future__ import annotations

from datetime import date, timedelta

TODAY = date(2026, 10, 21)
CURRENT_WEEK = 8


def _facts(engine, sid: str) -> tuple[dict, dict]:
    s = engine.get(sid)
    r = engine.score(sid)
    return s, r


def _cite(kb, school: str | None, query: str) -> list[dict]:
    return kb.search(query, top_k=2, school=school)


def student_letter(engine, kb, sid: str, school: str | None) -> dict:
    s, r = _facts(engine, sid)
    acts = engine.interventions(sid)[:3]
    hits = _cite(kb, school, "学业预警 告知 帮扶 学分")
    review = (TODAY + timedelta(days=21)).strftime("%Y 年 %m 月 %d 日")

    body = [
        f"**{s['name']}** 同学（学号 {s['id']}，{s['class_name']}）：",
        "",
        f"根据本学期第 {CURRENT_WEEK} 教学周的学情数据，你当前的学业风险综合评分为 "
        f"**{r['score']} 分**，达到**{r['level_label']}**标准。主要依据如下：",
        "",
        f"| 指标 | 实际情况 |",
        f"| --- | --- |",
        f"| 课堂出勤 | 缺勤 {r['raw']['absent']} 次 / {r['raw']['sessions']} 次 |",
        f"| 作业提交 | {r['raw']['hw_submitted']} / {r['raw']['hw_assigned']} 次 |",
        f"| 期中成绩 | 加权均分 {r['raw']['mid_avg']}（班级均分 {r['raw']['cohort_avg']}） |",
        f"| 历史欠账 | 累计不及格 {s['history']['failed_credits']} 学分 |",
        "",
        "**请你在收到本函后完成以下事项：**",
        "",
    ]
    for i, a in enumerate(acts, 1):
        body.append(f"{i}. {a['title']}——{a['detail']}")
    body += [
        "",
        f"学院将于 **{review}** 前后复查上述指标。若届时仍未改善，将按学校规定升级预警等级。",
        "",
        "学业预警不是处分，是提醒。遇到困难请主动联系辅导员或学业导师，学校会提供相应帮扶。",
    ]
    if hits:
        body += ["", f"依据：{hits[0]['citation']}——{hits[0]['text'].strip().splitlines()[0]}"]

    return {
        "type": "student",
        "title": f"学业预警告知函 · {s['name']}",
        "subject": f"关于 {s['name']} 同学本学期学业情况的预警告知",
        "body": "\n".join(body),
        "citations": hits,
        "meta": {"student": s["name"], "sid": s["id"], "level": r["level_label"], "score": r["score"], "review_at": review},
    }


def parent_letter(engine, kb, sid: str, school: str | None) -> dict:
    s, r = _facts(engine, sid)
    hits = _cite(kb, school, "家长 通知 家校沟通 学业预警")
    body = [
        f"尊敬的 {s['name']} 同学家长：",
        "",
        f"您好。{s['name']} 现就读于我校{s['major']}{s['grade']}，班级 {s['class_name']}。"
        f"本学期开学以来，学校通过课堂考勤、作业提交与期中考核等过程性数据，对学生的学业状态进行跟踪。",
        "",
        f"目前该生学业风险评分为 **{r['score']} 分**（{r['level_label']}），需要家校共同关注。具体表现为：",
        "",
        f"1. 课堂出勤：已缺勤 {r['raw']['absent']} 次（本学期已开课 {r['raw']['sessions']} 次）；",
        f"2. 作业提交：应交 {r['raw']['hw_assigned']} 次，实交 {r['raw']['hw_submitted']} 次；",
        f"3. 期中成绩：加权均分 {r['raw']['mid_avg']} 分，低于班级平均 {r['raw']['cohort_avg']} 分；",
        f"4. 历史情况：累计不及格 {s['history']['failed_credits']} 学分。",
        "",
        "学校已安排辅导员与学生谈话，并制定了个别化帮扶方案。恳请您配合做两件事："
        "一是与孩子沟通近期学习状态，了解是否有作息、情绪或生活方面的困难；"
        "二是保持与辅导员的联系，学院会定期反馈进展。",
        "",
        "如果孩子近期遇到实际困难，请及时告知学校，我们会一起想办法。",
        "",
        f"辅导员：{s['advisor']}　　学院教务办公室",
        f"{TODAY.strftime('%Y 年 %m 月 %d 日')}",
    ]
    if hits:
        body += ["", f"依据：{hits[0]['citation']}——{hits[0]['text'].strip().splitlines()[0]}"]
    return {
        "type": "parent",
        "title": f"家校沟通函 · {s['name']}",
        "subject": f"关于 {s['name']} 同学近期学习情况的沟通",
        "body": "\n".join(body),
        "citations": hits,
        "meta": {"student": s["name"], "sid": s["id"], "level": r["level_label"], "score": r["score"]},
    }


def counselor_brief(engine, kb, sid: str, school: str | None) -> dict:
    s, r = _facts(engine, sid)
    acts = engine.interventions(sid)
    weakest = min(s["courses"], key=lambda c: c["midterm"])
    hits = _cite(kb, school, "帮扶 跟踪 谈话 预警")
    body = [
        f"### 谈话前需要知道的",
        f"- 风险分 {r['score']}（{r['level_label']}），较上学期{r['trend']['label']}（{r['trend']['delta']:+} 分）",
        f"- 最弱一科：《{weakest['name']}》期中 {weakest['midterm']} 分（班均 {engine.course_stats[weakest['code']]['mean']}）",
        f"- 关键行为：缺勤 {r['raw']['absent']} 次，作业少交 {r['raw']['hw_assigned'] - r['raw']['hw_submitted']} 次，平台已 {s['engagement']['days_since_active']} 天未活跃",
        "",
        "### 建议的谈话顺序",
        "1. **先问状态，别先报数字。** “这学期感觉怎么样？”让他自己说，别一上来就念缺勤次数。",
        f"2. **再对事实。** 把缺勤 {r['raw']['absent']} 次、作业少交 {r['raw']['hw_assigned'] - r['raw']['hw_submitted']} 次摆出来，问是哪一环卡住了。",
        "3. **区分三类原因。** 能力问题（听不懂）、动力问题（不想学）、生活问题（作息/经济/情绪）——三类对应完全不同的处理。",
        "4. **只约定一件事。** 一次谈三件等于没谈，挑最容易做到的那件。",
        "",
        "### 可以当场承诺的支持",
    ]
    for a in acts[:3]:
        body.append(f"- {a['title']} —— {a['detail']}")
    body += [
        "",
        "### 跟进节点",
        f"- 一周后：看他是否完成第一件事（{acts[0]['deadline']}）",
        f"- 三周后：复查期中考后的小测与作业，决定是否升级预警",
    ]
    if hits:
        body += ["", f"依据：{hits[0]['citation']}——{hits[0]['text'].strip().splitlines()[0]}"]
    return {
        "type": "counselor",
        "title": f"谈话要点 · {s['name']}",
        "subject": f"{s['name']}（{s['class_name']}）学业谈话提纲",
        "body": "\n".join(body),
        "citations": hits,
        "meta": {"student": s["name"], "sid": s["id"], "score": r["score"]},
    }


def class_report(engine, class_name: str) -> dict:
    rows = engine.roster(class_name)
    red = [r for r in rows if r["level"] == "red"]
    yellow = [r for r in rows if r["level"] == "yellow"]
    rising = [r for r in rows if r["direction"] == "up" and r["level"] != "red"]
    body = [
        f"### {class_name} 第 8 教学周学情简报",
        "",
        f"- 在册 {len(rows)} 人，红色预警 **{len(red)}** 人，黄色关注 **{len(yellow)}** 人",
        f"- 风险上升 {len(rising)} 人，平均风险分 {round(sum(r['score'] for r in rows) / len(rows), 1)}",
        "",
        "### 需要本周谈话",
    ]
    for r in red[:5]:
        body.append(f"- {r['name']}（{r['score']} 分）主因：{r['top_factor']}，缺勤 {r['absent']} 次")
    if not red:
        body.append("- 本周无红色预警学生")
    body += ["", "### 值得关注的变化"]
    for r in rising[:4]:
        body.append(f"- {r['name']}：较上学期上升 {r['delta']:+.0f} 分，尚未进入红色，建议提前提醒")
    if not rising:
        body.append("- 无明显异常波动")
    return {
        "type": "report",
        "title": f"{class_name} 周报",
        "subject": f"{class_name} 第 8 教学周学业风险简报",
        "body": "\n".join(body),
        "citations": [],
        "meta": {"class_name": class_name, "red": len(red), "yellow": len(yellow)},
    }
