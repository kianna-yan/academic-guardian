"""证据链元数据：把「这次查了什么」变成可展示的事实。

每一条 trace 都要能回答三个问句——查的哪张表、命中几条、什么时候查的。
前端把它渲染成时间线（工具 → 参数 → 耗时 → 产出行数），
用户顺着它能把回答里的每个数字追回出处；评委问「这个 68.8 分哪来的」时，
证据链本身就是答案。

工具名 → （数据来源, 用到的表/索引, 计量单位）。
新增工具时在这里补一行即可，前端无需改动。
"""
from __future__ import annotations

import time

TOOL_META: dict[str, tuple[str, str, str]] = {
    "risk_score": ("风险引擎", "students · risk_score()", "名学生"),
    "interventions": ("干预建议库", "advice · 规则模板", "条建议"),
    "retrieve_policy": ("校规知识库", "knowledge/*.md · BM25 索引", "条条款"),
    "search_policy": ("校规知识库", "knowledge/*.md · BM25 索引", "条条款"),
    "roster": ("风险名单", "students · 按风险分排序", "名学生"),
    "campus_overview": ("全校聚合", "students · 分布统计", "名学生"),
    "grade_trend": ("成绩库", "grades · 学期序列", "个学期"),
    "homework_detail": ("作业库", "homework · 逐次作业记录", "行明细"),
    "attendance_detail": ("考勤库", "attendance · 逐次考勤记录", "行明细"),
    "course_list": ("教务课表", "courses · 在修课程", "门课程"),
    "score_detail": ("成绩库", "courses · 期中卷面 + 班内排名", "门课程"),
    "class_score_detail": ("成绩库", "students · 按期中均分排名", "名学生"),
    "classroom_stats": ("课堂学情", "classroom · 本课程统计", "门课程"),
    "contact_detail": ("教师档案", "courses · teacher_profile", "位老师"),
    "counselor_brief": ("谈话要点", "students + advice 合成", "条要点"),
    "teacher_view": ("课堂数据", "classroom · 考勤与作业", "名学生"),
    "record_intervention": ("干预台账", "interventions · 写入", "条记录"),
    "export_file": ("文书中心", "letters · Word 模板", "份文书"),
    "send_letter": ("家校消息", "messages · 推送给家长", "条消息"),
    "send_parent_letter": ("家校消息", "messages · 家长信", "条消息"),
    "daily_report": ("预警日报", "students · 每日聚合", "名学生"),
    # 路由分支（模型自己挑工具）用的工具名
    "get_student": ("学生库", "students · 单条详情", "名学生"),
    "get_attendance": ("考勤库", "attendance · 逐次记录", "条记录"),
    "get_homework": ("作业库", "homework · 逐次记录", "条记录"),
    "get_risk": ("风险引擎", "students · risk_score()", "名学生"),
    "get_courses": ("教务课表", "courses · 课程与教师档案", "门课程"),
    "get_timetable": ("教务课表", "checkin · calendar() 逐节日历", "节课"),
    "get_final_forecast": ("成绩试算", "simulator · 考核权重与期末试算", "门课程"),
    "get_todos": ("通知中心", "notifications · 本账号未读与待办", "条"),
    "get_letter": ("文书中心", "letters · 告知函正文", "份文书"),
    "get_curriculum": ("培养方案", "curriculum · 课程档案与学分要求", "门课程"),
    "get_interventions": ("干预台账", "interventions · 已记录动作", "条记录"),
    "get_class_report": ("班级简报", "report · 班级学情聚合", "条要点"),
    "get_messages": ("家校消息", "messages · 会话记录", "条消息"),
    "get_appeals": ("异议中心", "appeals · 处理进度", "条异议"),
    "get_scores": ("成绩库", "courses · 期中卷面 + 班内排名", "门课程"),
    "get_class_scores": ("成绩库", "students · 按期中均分排名", "名学生"),
    "get_learning_track": ("学习轨迹", "checkins · 课后自评断点", "门课程"),
    "list_roster": ("风险名单", "students · 按风险分排序", "名学生"),
    "get_overview": ("全校聚合", "students · 分布统计", "名学生"),
    "llm_polish": ("大模型", "LLM 润色", "段回答"),
}


def count_rows(result) -> int:
    """一条工具结果算「命中几条」：列表取长度，字典优先取它自报的总数。"""
    if isinstance(result, list):
        return len(result)
    if isinstance(result, dict):
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        for box in (result, data):
            for key in ("total", "count"):
                v = box.get(key)
                if isinstance(v, int):
                    return v
            for key in ("rows", "items", "students", "semesters", "条款", "记录"):
                v = box.get(key)
                if isinstance(v, list):
                    return len(v)
        return 1
    if result is None:
        return 0
    return 1


def build(name: str, result, elapsed_ms: float = 0.0) -> dict:
    """组装一项 trace 的证据元数据。耗时也进来：查得慢本身就是证据的一部分。"""
    source, table, unit = TOOL_META.get(name, ("运行时", "—", "条"))
    ev = {
        "source": source,
        "table": table,
        "rows": count_rows(result),
        "unit": unit,
        "ts": time.strftime("%H:%M:%S"),
        "ms": round(elapsed_ms, 1),
    }
    # 校规检索再补一句「命中了哪几条」，这是最容易被追问的一环
    if name in ("retrieve_policy", "search_policy") and isinstance(result, list) and result:
        ids = [str(h.get("id") or h.get("citation") or "") for h in result if isinstance(h, dict)]
        ev["detail"] = "、".join(i for i in ids if i)
    return ev
