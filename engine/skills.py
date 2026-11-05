"""输入框「+ → Skill」背后的四件事：PPT / PDF / Word 生成，以及图表解读。

设计取舍
- 技能不是一句提示词。点了「PPT 生成」就该拿到一个能打开的 .pptx，
  所以三种文档都由这里现场渲染，接口直接把文件流回去，前端点一下就下载；
- 内容同源：`brief()` 只聚合一次学情（风险、成绩、出勤、建议），
  三种格式各自排版。数字只有一个出处，不会出现「PPT 说 52 分、Word 说 55 分」；
- 图表解读不生成文件：它的输入是一张图（成绩单、折线图截图），
  前端点它直接开图片选择，走已有的视觉识别链路，这里只提供菜单项；
- 报告是「学生的报告」，学生只能导出自己的（角色与 sid 的校验在 app.py）。
"""
from __future__ import annotations

import io
import re
from datetime import datetime

from engine import exporter, simple_pdf, trend

MIME = {
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}

# 菜单顺序就是用户最可能点的顺序。
# kind: file=产出文件 / image=开图片选择 / draft=按模板起草文书 / roleplay=进入演练
# roles: 哪些端能看到（菜单由后端下发，前端不写死，权限也就只有这一处）
CATALOG: list[dict] = [
    {
        "key": "ppt",
        "name": "PPT 生成",
        "icon": "📊",
        "desc": "6 页学情汇报，投屏就能讲",
        "ext": "pptx",
        "kind": "file",
        "roles": ["student", "parent", "counselor", "admin"],
        "hints": {
            "student": "把这学期的情况整理成一份能讲的汇报",
            "parent": "把孩子这学期的情况整理成一份汇报",
            "counselor": "把本班这学期的情况整理成一份汇报",
            "admin": "把全校这学期的情况整理成一份汇报",
        },
    },
    {
        "key": "pdf",
        "name": "PDF 生成",
        "icon": "📄",
        "desc": "一页纸报告，打印、存档都合适",
        "ext": "pdf",
        "kind": "file",
        "roles": ["student", "parent", "counselor", "admin"],
        "hints": {
            "student": "把这学期的学情整理成一页纸，我要打印存档",
            "parent": "把孩子这学期的情况整理成一页纸",
            "counselor": "把今天的预警情况整理成一页纸",
            "admin": "把今天全校的预警情况整理成一页纸",
        },
    },
    {
        "key": "word",
        "name": "Word 生成",
        "icon": "📝",
        "desc": "可编辑的报告，方便加批注",
        "ext": "docx",
        "kind": "file",
        "roles": ["student", "parent", "counselor", "admin"],
        "hints": {
            "student": "把这学期的学情整理成可编辑的报告，我要写批注",
            "parent": "把孩子这学期的情况整理成 Word",
            "counselor": "把今天的预警日报整理成 Word，我要改一改",
            "admin": "把今天的预警日报整理成 Word，我要改一改",
        },
    },
    {
        "key": "chart",
        "name": "图表解读",
        "icon": "📈",
        "desc": "上传成绩单或图表，逐条读数",
        "ext": None,
        "kind": "image",
        "roles": ["student", "parent", "counselor", "admin", "teacher"],
        "hint": "帮我看看这张成绩单，把关键数字读出来",
    },
    {
        "key": "doc",
        "name": "文书辅助",
        "icon": "🗂",
        "desc": "休学 / 免修 / 调课 / 复核等六类",
        "ext": "docx",
        "kind": "draft",
        "roles": ["counselor", "admin"],
        "hint": "按模板起草一份教务文书",
        "note": "只起草，不代提交",
        "subs": [
            {"key": "suspend", "name": "休学申请", "desc": "含审批栏与材料清单"},
            {"key": "adjust", "name": "调课说明", "desc": "临时调课 / 补课安排"},
            {"key": "exempt", "name": "免修申请", "desc": "已修 / 持证免修"},
            {"key": "review", "name": "成绩复核申请", "desc": "卷面 / 平时分 / 登分"},
            {"key": "notice", "name": "教务通知", "desc": "发文格式，含报送时限"},
            {"key": "minutes", "name": "会议纪要", "desc": "议定事项与责任人"},
        ],
    },
    {
        "key": "family",
        "name": "家校沟通",
        "icon": "👪",
        "desc": "四类家长角色扮演，先练再打",
        "ext": None,
        "kind": "roleplay",
        "roles": ["counselor"],
        "hint": "开始一场家长沟通演练",
        "note": "演练，不代替真实沟通",
        "subs": [
            {"key": "anxious", "name": "焦虑型家长", "desc": "情绪先到，反复确认"},
            {"key": "demanding", "name": "强势质问型家长", "desc": "先要说法，再要承诺"},
            {"key": "detached", "name": "放任疏离型家长", "desc": "人在外地，管不了"},
            {"key": "cooperative", "name": "配合型家长", "desc": "愿意配合，缺方法"},
        ],
    },
]

BY_KEY = {x["key"]: x for x in CATALOG}
BY_SUB = {(x["key"], s["key"]): s for x in CATALOG for s in (x.get("subs") or [])}


def hint_for(item: dict, role: str | None) -> str:
    """同一个技能在五个端说不一样的话。

    以前提示语只有一句（学生口吻），导员端点了「PPT 生成」拿到的是
    「给我一个这学期的补救计划」——文案和端口对不上，就是这个原因。
    """
    hints = item.get("hints") or {}
    if role and hints.get(role):
        return hints[role]
    if item.get("hint"):
        return item["hint"]
    return hints.get("student") or (next(iter(hints.values())) if hints else "")


def catalog(role: str | None = None) -> list[dict]:
    """给前端菜单用：按端过滤 + 按端取提示语，深拷贝一份，不把内部常量递出去。"""
    out: list[dict] = []
    for item in CATALOG:
        roles = item.get("roles") or []
        if role and roles and role not in roles:
            continue
        row = {k: v for k, v in item.items() if k != "hints"}
        row["hint"] = hint_for(item, role)
        if item.get("subs"):
            row["subs"] = [dict(x) for x in item["subs"]]
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# 内容：一次聚合，三种格式共用
# ---------------------------------------------------------------------------
def _avg(nums: list[float]) -> float | None:
    vals = [n for n in nums if isinstance(n, (int, float))]
    return round(sum(vals) / len(vals), 1) if vals else None


def brief(engine, sid: str) -> dict:
    """把一名学生的学情聚成报告需要的形状。找不到人时抛 KeyError，由接口转 404。"""
    s = engine.get(sid)
    r = engine.score(sid)
    adv = engine.advice(sid, r)
    tr = trend.grade_trend(s)
    raw = r.get("raw") or {}

    courses = []
    probs = {x["code"]: x for x in (r.get("pass_probability") or [])}
    for c in s.get("courses") or []:
        code = c.get("code")
        p = probs.get(code) or {}
        courses.append({
            "name": c.get("name") or code,
            "teacher": c.get("teacher") or "",
            "credit": c.get("credit"),
            "midterm": c.get("midterm"),
            "cohort": p.get("cohort_avg"),
            "fail": p.get("fail_probability"),
        })
        if len(courses) >= 8:
            break

    factors = sorted(r.get("factors") or [], key=lambda f: -float(f.get("points") or 0))[:3]

    return {
        "name": s.get("name") or "同学",
        "sid": s.get("id"),
        "class_name": s.get("class_name") or "",
        "major": s.get("major") or "",
        "grade": s.get("grade") or "",
        "term": s.get("term") or "",
        "advisor": s.get("advisor") or "",
        "risk": {
            "score": r.get("score"),
            "level": r.get("level"),
            "level_label": r.get("level_label"),
            "delta": (r.get("trend") or {}).get("delta"),
            "trend_label": (r.get("trend") or {}).get("label"),
            "factors": [
                {"label": f.get("label"), "points": f.get("points")} for f in factors
            ],
            "absent": raw.get("absent"),
            "sessions": raw.get("sessions"),
            "hw_submitted": raw.get("hw_submitted"),
            "hw_assigned": raw.get("hw_assigned"),
            "mid_avg": raw.get("mid_avg"),
            "cohort_avg": raw.get("cohort_avg"),
        },
        "history": s.get("history") or {},
        "credits": s.get("credits") or {},
        "engagement": s.get("engagement") or {},
        "track": {
            "summary": tr.get("summary") or "",
            "slope": tr.get("slope"),
            "rank": tr.get("rank"),
        },
        "courses": courses,
        "advice": {
            "headline": adv.get("headline") or "",
            "diagnosis": adv.get("diagnosis") or "",
            "steps": list((adv.get("root") or {}).get("steps") or adv.get("first_steps") or [])[:4],
            "support": list(adv.get("support") or [])[:3],
        },
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _sign(v, unit: str = "") -> str:
    if not isinstance(v, (int, float)):
        return "—"
    return f"{v:+.1f}{unit}" if v > 0 else f"{v:.1f}{unit}"


def _support_lines(items: list) -> list[str]:
    """求助资源是 {kind, text, contact} 的字典，不能直接 str——会印出一串花括号。"""
    out: list[str] = []
    for x in items or []:
        if isinstance(x, dict):
            kind = str(x.get("kind") or "").strip()
            text = str(x.get("text") or "").strip()
            contact = str(x.get("contact") or "").strip()
            body = f"{kind}：{text}" if kind and text else (text or kind)
            if contact and contact not in body:
                body = f"{body}（{contact}）"
            if body:
                out.append(body)
        elif x:
            out.append(str(x))
    return out


def as_markdown(b: dict) -> str:
    """Word 版：走 exporter 的受限 markdown，列表与表格都能落成真正的段落/表格。"""
    rk = b["risk"]
    lines = [
        f"**{b['class_name']} · {b['grade']} · {b['major']} · {b['term']}**",
        "",
        "### 一、风险态势",
        f"- 当前风险分 **{rk['score']}**，等级：{rk['level_label']}；较上次 {_sign(rk['delta'])} 分，趋势「{rk['trend_label'] or '—'}」。",
    ]
    if rk["factors"]:
        lines.append(
            "- 主导因素：" + "、".join(f"{f['label']}（贡献 {f['points']} 分）" for f in rk["factors"]) + "。"
        )
    lines += [
        f"- 课堂出勤：缺勤 {rk['absent']} 次 / 共 {rk['sessions']} 节；作业提交 {rk['hw_submitted']}/{rk['hw_assigned']} 次。",
        f"- 期中均分 {rk['mid_avg']}，班均 {rk['cohort_avg']}，差 {_sign(round((rk['mid_avg'] or 0) - (rk['cohort_avg'] or 0), 1))} 分。",
        "",
        "### 二、课程画像",
    ]
    if b["courses"]:
        lines.append("| 课程 | 期中 | 班均 | 预计挂科风险 |")
        lines.append("| --- | --- | --- | --- |")
        for c in b["courses"]:
            fail = c["fail"]
            fail_txt = f"{round(float(fail) * 100)}%" if isinstance(fail, (int, float)) else "—"
            lines.append(f"| {c['name']} | {c['midterm'] if c['midterm'] is not None else '—'} | "
                         f"{c['cohort'] if c['cohort'] is not None else '—'} | {fail_txt} |")
    else:
        lines.append("- 本学期暂无课程成绩记录。")

    hist = b["history"]
    cred = b["credits"]
    lines += [
        "",
        "### 三、学分与投入",
        f"- 上学期均分 {hist.get('avg', '—')}，GPA {hist.get('gpa', '—')}，挂科学分 {hist.get('failed_credits', '—')}。",
        f"- 已修学分 {cred.get('earned', '—')} / 计划 {cred.get('plan_total', '—')}，本学期在修 {cred.get('in_progress', '—')}。",
        f"- 学习投入：近一周登录 {b['engagement'].get('weekly_logins', '—')} 次，"
        f"视频完成率 {round(float(b['engagement'].get('video_rate') or 0) * 100)}%，"
        f"已 {b['engagement'].get('days_since_active', '—')} 天没有新的学习行为。",
        "",
        "### 四、下一步怎么做",
    ]
    if b["advice"]["diagnosis"]:
        lines.append(b["advice"]["diagnosis"])
    for i, step in enumerate(b["advice"]["steps"], 1):
        lines.append(f"{i}. {step}")
    support = _support_lines(b["advice"]["support"])
    if support:
        lines.append("- 可以找谁：" + "；".join(support))
    lines += [
        "",
        f"数据来源：教务系统学情库 · 生成时间 {b['generated_at']} · 学业护航智能体自动生成，供参考，"
        "不替代辅导员与任课教师的判断。",
    ]
    return "\n".join(lines)


def as_sections(b: dict) -> list[tuple[str, list[str]]]:
    """PDF 版：自带排版器只认「小标题 + 条目」，直接给结构化列表。"""
    rk = b["risk"]
    hist = b["history"]
    cred = b["credits"]
    eng_ = b["engagement"]

    sec: list[tuple[str, list[str]]] = []
    sec.append(("一、风险态势", [
        f"当前风险分 {rk['score']}，等级：{rk['level_label']}；较上次 {_sign(rk['delta'])} 分，"
        f"趋势「{rk['trend_label'] or '—'}」。",
        "- 主导因素：" + ("、".join(f"{f['label']}贡献 {f['points']} 分" for f in rk["factors"]) or "—"),
        f"- 课堂出勤：缺勤 {rk['absent']} 次 / 共 {rk['sessions']} 节；"
        f"作业提交 {rk['hw_submitted']}/{rk['hw_assigned']} 次。",
        f"- 期中均分 {rk['mid_avg']}，班均 {rk['cohort_avg']}。",
    ]))

    course_lines = []
    for c in b["courses"]:
        fail = c["fail"]
        fail_txt = f"，预计挂科风险 {round(float(fail) * 100)}%" if isinstance(fail, (int, float)) else ""
        course_lines.append(
            f"- {c['name']}：期中 {c['midterm'] if c['midterm'] is not None else '—'}"
            f"（班均 {c['cohort'] if c['cohort'] is not None else '—'}）{fail_txt}"
        )
    sec.append(("二、课程画像", course_lines or ["本学期暂无课程成绩记录。"]))

    sec.append(("三、学分与投入", [
        f"- 上学期均分 {hist.get('avg', '—')}，GPA {hist.get('gpa', '—')}，"
        f"挂科学分 {hist.get('failed_credits', '—')}。",
        f"- 已修学分 {cred.get('earned', '—')} / 计划 {cred.get('plan_total', '—')}，"
        f"在修 {cred.get('in_progress', '—')}。",
        f"- 近一周登录 {eng_.get('weekly_logins', '—')} 次，"
        f"视频完成率 {round(float(eng_.get('video_rate') or 0) * 100)}%，"
        f"{eng_.get('days_since_active', '—')} 天没有新的学习行为。",
    ]))

    steps = [f"- {x}" for x in b["advice"]["steps"]] or ["- 暂无建议"]
    next_sec = ([b["advice"]["diagnosis"]] if b["advice"]["diagnosis"] else []) + steps
    support = _support_lines(b["advice"]["support"])
    if support:
        next_sec += ["  " + s for s in support]
    sec.append(("四、下一步怎么做", next_sec))
    return sec


# ---------------------------------------------------------------------------
# 三种格式的渲染
# ---------------------------------------------------------------------------
def _docx(b: dict) -> bytes:
    doc = exporter._new_doc("学业护航 · 学情报告")
    exporter._title(doc, f"学情报告 · {b['name']}",
                    f"{b['class_name']} · {b['term']} · 生成于 {b['generated_at']}")
    exporter.md_to_docx(doc, as_markdown(b))
    exporter._sign(doc, who="学业护航智能体（自动生成）")
    return exporter._docx_bytes(doc).getvalue()


def _pdf(b: dict) -> bytes:
    return simple_pdf.build_pdf(
        f"学情报告 · {b['name']}",
        f"{b['class_name']} · {b['grade']} · {b['major']} · {b['term']} · 生成于 {b['generated_at']}",
        as_sections(b),
        footer="学业护航 · 数据来自教务系统学情库，供参考",
    )


def _pptx(b: dict) -> bytes:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.util import Emu, Inches, Pt

    BRAND = RGBColor(0xC2, 0x41, 0x0C)
    INK = RGBColor(0x3B, 0x2E, 0x24)
    MUTED = RGBColor(0x8E, 0x7A, 0x66)
    RED = RGBColor(0xDC, 0x26, 0x26)
    GREEN = RGBColor(0x15, 0x80, 0x3D)
    PAPER = RGBColor(0xFA, 0xF6, 0xF1)
    FONT = "微软雅黑"

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    W, H = prs.slide_width, prs.slide_height
    blank = prs.slide_layouts[6]

    def slide():
        s = prs.slides.add_slide(blank)
        bg = s.shapes.add_shape(1, 0, 0, W, H)
        bg.fill.solid()
        bg.fill.fore_color.rgb = PAPER
        bg.line.fill.background()
        return s

    def text(s, left, top, width, height, body, size=18, color=INK, bold=False,
             align=PP_ALIGN.LEFT, line=1.35):
        box = s.shapes.add_textbox(left, top, width, height)
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.TOP
        lines = body.split("\n") if isinstance(body, str) else body
        for i, ln in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align
            p.line_spacing = line
            r = p.add_run()
            r.text = ln
            r.font.size = Pt(size)
            r.font.bold = bold
            r.font.color.rgb = color
            r.font.name = FONT
        return box

    def bar(s, left, top, width, color=BRAND):
        shp = s.shapes.add_shape(1, left, top, width, Emu(38100))  # 3pt 细条
        shp.fill.solid()
        shp.fill.fore_color.rgb = color
        shp.line.fill.background()

    rk = b["risk"]
    # 1 封面 -----------------------------------------------------------------
    s = slide()
    color = RED if rk["level"] == "red" else (RGBColor(0xCA, 0x8A, 0x04) if rk["level"] == "yellow" else GREEN)
    text(s, Inches(0.9), Inches(2.2), Inches(11.5), Inches(0.5),
         "学业护航 · 学情报告", size=16, color=BRAND, bold=True)
    text(s, Inches(0.9), Inches(2.7), Inches(11.5), Inches(1.4), b["name"], size=54, bold=True)
    text(s, Inches(0.9), Inches(4.1), Inches(11.5), Inches(0.8),
         f"{b['class_name']} · {b['grade']} · {b['major']}", size=20, color=MUTED)
    bar(s, Inches(0.9), Inches(5.05), Inches(1.6))
    text(s, Inches(0.9), Inches(5.3), Inches(8), Inches(0.6),
         f"{b['term']} · 生成于 {b['generated_at']}", size=13, color=MUTED)
    # 大字号必须单倍行距：64pt × 1.35 的行高会把下面那行「黄色关注」顶穿
    text(s, Inches(10.2), Inches(2.45), Inches(2.4), Inches(1.0),
         f"{rk['score']}", size=64, bold=True, color=color, align=PP_ALIGN.RIGHT, line=1.0)
    text(s, Inches(10.2), Inches(3.62), Inches(2.4), Inches(0.5),
         rk["level_label"], size=15, color=color, align=PP_ALIGN.RIGHT)

    # 2 风险态势 -------------------------------------------------------------
    s = slide()
    text(s, Inches(0.9), Inches(0.7), Inches(11), Inches(0.6), "风险态势", size=30, bold=True)
    bar(s, Inches(0.9), Inches(1.46), Inches(1.1))
    text(s, Inches(0.9), Inches(1.7), Inches(5.4), Inches(1.2),
         f"{rk['score']} 分 · {rk['level_label']}", size=32, bold=True, color=color)
    trend_txt = f"较上次 {_sign(rk['delta'])} 分，{rk['trend_label'] or '—'}"
    text(s, Inches(0.9), Inches(2.7), Inches(5.4), Inches(0.6), trend_txt, size=16, color=MUTED)
    text(s, Inches(0.9), Inches(3.5), Inches(5.2), Inches(0.4), "主导因素", size=13, color=BRAND, bold=True)
    top = Inches(4.0)
    for f in rk["factors"]:
        text(s, Inches(0.9), top, Inches(3.6), Inches(0.45),
             f"{f['label']}", size=15)
        text(s, Inches(4.5), top, Inches(1.6), Inches(0.45),
             f"{f['points']} 分", size=15, color=MUTED)
        top += Inches(0.55)
    # 右侧三个数字块
    blocks = [
        ("缺勤", f"{rk['absent']} 次", f"共 {rk['sessions']} 节课"),
        ("作业提交", f"{rk['hw_submitted']}/{rk['hw_assigned']}", "按次统计"),
        ("期中均分", f"{rk['mid_avg']}", f"班均 {rk['cohort_avg']}"),
    ]
    top = Inches(1.8)
    for label, big, small in blocks:
        box = s.shapes.add_shape(1, Inches(7.6), top, Inches(4.8), Inches(1.35))
        box.fill.solid()
        box.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        box.line.color.rgb = RGBColor(0xE8, 0xDF, 0xD4)
        text(s, Inches(7.9), top + Inches(0.16), Inches(2.2), Inches(0.4), label, size=13, color=MUTED)
        text(s, Inches(7.9), top + Inches(0.55), Inches(2.4), Inches(0.7), big, size=26, bold=True)
        text(s, Inches(10.4), top + Inches(0.62), Inches(1.9), Inches(0.5), small, size=13, color=MUTED)
        top += Inches(1.6)

    # 3 课程画像 -------------------------------------------------------------
    s = slide()
    text(s, Inches(0.9), Inches(0.7), Inches(11), Inches(0.6), "课程画像", size=30, bold=True)
    bar(s, Inches(0.9), Inches(1.46), Inches(1.1))
    text(s, Inches(0.9), Inches(1.55), Inches(11), Inches(0.5),
         "期中成绩与班级均分对照，右侧是预计挂科风险", size=14, color=MUTED)
    rows = b["courses"][:6] or []
    head_y = Inches(2.2)
    for label, x, w in [("课程", 0.9, 4.6), ("期中", 5.6, 1.6), ("班均", 7.3, 1.6), ("挂科风险", 9.0, 2.0)]:
        text(s, Inches(x), head_y, Inches(w), Inches(0.4), label, size=13, color=BRAND, bold=True)
    y = head_y + Inches(0.5)
    for c in rows:
        text(s, Inches(0.9), y, Inches(4.5), Inches(0.42), c["name"], size=15)
        text(s, Inches(5.6), y, Inches(1.6), Inches(0.42),
             f"{c['midterm'] if c['midterm'] is not None else '—'}", size=15)
        text(s, Inches(7.3), y, Inches(1.6), Inches(0.42),
             f"{c['cohort'] if c['cohort'] is not None else '—'}", size=15, color=MUTED)
        fail = c["fail"]
        if isinstance(fail, (int, float)):
            pct = round(float(fail) * 100)
            text(s, Inches(9.0), y, Inches(2.0), Inches(0.42), f"{pct}%", size=15,
                 color=RED if pct >= 60 else (MUTED if pct < 30 else RGBColor(0xCA, 0x8A, 0x04)))
        else:
            text(s, Inches(9.0), y, Inches(2.0), Inches(0.42), "—", size=15, color=MUTED)
        y += Inches(0.52)
    if not rows:
        text(s, Inches(0.9), Inches(2.9), Inches(11), Inches(0.5), "本学期暂无课程成绩记录。", size=16, color=MUTED)

    # 4 学分与投入 -----------------------------------------------------------
    s = slide()
    text(s, Inches(0.9), Inches(0.7), Inches(11), Inches(0.6), "学分与学习投入", size=30, bold=True)
    bar(s, Inches(0.9), Inches(1.46), Inches(1.1))
    hist = b["history"]
    cred = b["credits"]
    eng_ = b["engagement"]
    left_items = [
        ("上学期均分", str(hist.get("avg", "—"))),
        ("上学期 GPA", str(hist.get("gpa", "—"))),
        ("挂科学分", str(hist.get("failed_credits", "—"))),
    ]
    right_items = [
        ("已修 / 计划学分", f"{cred.get('earned', '—')} / {cred.get('plan_total', '—')}"),
        ("本周登录", f"{eng_.get('weekly_logins', '—')} 次"),
        ("视频完成率", f"{round(float(eng_.get('video_rate') or 0) * 100)}%"),
    ]
    y = Inches(2.0)
    for (l1, v1), (l2, v2) in zip(left_items, right_items):
        for x, label, val in [(0.9, l1, v1), (6.9, l2, v2)]:
            box = s.shapes.add_shape(1, Inches(x), y, Inches(5.2), Inches(1.15))
            box.fill.solid()
            box.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            box.line.color.rgb = RGBColor(0xE8, 0xDF, 0xD4)
            text(s, Inches(x + 0.25), y + Inches(0.12), Inches(2.6), Inches(0.4), label, size=12, color=MUTED)
            text(s, Inches(x + 0.25), y + Inches(0.48), Inches(4.6), Inches(0.55), val, size=22, bold=True)
        y += Inches(1.35)
    text(s, Inches(0.9), Inches(6.4), Inches(11), Inches(0.5),
         f"已 {eng_.get('days_since_active', '—')} 天没有新的学习行为，学习节奏是这学期最该补的一环。",
         size=13, color=MUTED)

    # 5 行动建议 -------------------------------------------------------------
    s = slide()
    text(s, Inches(0.9), Inches(0.7), Inches(11), Inches(0.6), "下一步怎么做", size=30, bold=True)
    bar(s, Inches(0.9), Inches(1.46), Inches(1.1))
    if b["advice"]["headline"]:
        text(s, Inches(0.9), Inches(1.7), Inches(11.4), Inches(0.8),
             b["advice"]["headline"], size=17, color=MUTED, line=1.4)
    y = Inches(2.7)
    for i, step in enumerate(b["advice"]["steps"] or ["先把缺的课补上，再谈提分"], 1):
        num = s.shapes.add_shape(9, Inches(0.9), y + Inches(0.06), Inches(0.42), Inches(0.42))
        num.fill.solid()
        num.fill.fore_color.rgb = BRAND
        num.line.fill.background()
        tf = num.text_frame
        tf.text = str(i)
        tf.paragraphs[0].alignment = PP_ALIGN.CENTER
        tf.paragraphs[0].runs[0].font.size = Pt(13)
        tf.paragraphs[0].runs[0].font.bold = True
        tf.paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        text(s, Inches(1.55), y, Inches(10.6), Inches(0.9), step, size=16, line=1.45)
        y += Inches(0.95)

    # 6 结尾 ---------------------------------------------------------------
    s = slide()
    text(s, Inches(0.9), Inches(2.4), Inches(11), Inches(0.6),
         "数据与免责", size=24, bold=True, color=BRAND)
    bar(s, Inches(0.9), Inches(3.05), Inches(1.1))
    text(s, Inches(0.9), Inches(3.35), Inches(11.2), Inches(2.2),
         "本报告由学业护航智能体根据教务系统学情库自动生成：风险分来自出勤、作业、\n"
         "期中成绩、学习投入、历史欠账与学分进度六项加权，不是预测，也不替代辅导员的判断。\n"
         "如某项记录与实际不符，可在「成绩与作业 → 复议与异议」里提出，辅导员会核实。",
         size=15, color=MUTED, line=1.6)
    text(s, Inches(0.9), Inches(6.3), Inches(11), Inches(0.5),
         f"{b['name']} · {b['class_name']} · {b['generated_at']}", size=12, color=MUTED)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def filename(key: str, b: dict) -> str:
    ext = BY_KEY[key]["ext"]
    day = datetime.now().strftime("%Y%m%d")
    safe = b["name"].replace(" ", "")
    return f"学情报告_{safe}_{day}.{ext}"


def render(key: str, engine, sid: str) -> tuple[bytes, str, str]:
    """返回 (文件字节, 文件名, MIME)。未知 key 抛 KeyError。"""
    meta = BY_KEY[key]
    if not meta.get("ext"):
        raise KeyError(f"{key} 不是文件类技能")
    b = brief(engine, sid)
    data = {"docx": _docx, "pdf": _pdf, "pptx": _pptx}[meta["ext"]](b)
    return data, filename(key, b), MIME[meta["ext"]]


# ---------------------------------------------------------------------------
# 没有具体学生时：辅导员 / 教务导的是「班级·全校」这一层
# ---------------------------------------------------------------------------
def _plain(line: str) -> str:
    """去掉 markdown 的强调标记：PDF 里没有粗体语义，留着 ** 只会印出来。"""
    out = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
    out = re.sub(r"__(.+?)__", r"\1", out)
    return out.replace("`", "")


def _md_sections(md: str) -> list[tuple[str, list[str]]]:
    """把日报的 markdown 正文切成「小标题 + 条目」，给 PDF 排版器用。"""
    secs: list[tuple[str, list[str]]] = []
    title, buf = "总览", []
    for raw in (md or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("### "):
            # 日报正文用的是三级标题（### 全校态势），两种都当小节切
            if buf:
                secs.append((title, buf))
            title, buf = _plain(line[4:].strip()), []
        elif line.startswith("## "):
            if buf:
                secs.append((title, buf))
            title, buf = _plain(line[3:].strip()), []
        else:
            buf.append(_plain(line if line.lstrip().startswith("- ") else line.strip()))
    if buf:
        secs.append((title, buf))
    return secs or [("总览", ["暂无内容"])]


def render_class(key: str, rep: dict, engine) -> tuple[bytes, str, str]:
    """班级 / 全校视角的导出：PPT 走既有的学期汇报，Word 走日报，PDF 现场排版。"""
    meta = BY_KEY[key]
    ext = meta.get("ext")
    if not ext:
        raise KeyError(f"{key} 不是文件类技能")
    day = datetime.now().strftime("%Y%m%d")
    if ext == "pptx":
        return (
            exporter.semester_pptx(rep, engine).getvalue(),
            f"学业预警学期汇报_{day}.pptx",
            MIME["pptx"],
        )
    if ext == "docx":
        return (
            exporter.daily_report_docx(rep).getvalue(),
            f"每日预警日报_{rep.get('date', day)}.docx",
            MIME["docx"],
        )
    # 日报的 summary 是一句话，不是字典
    head = rep.get("summary") or ""
    if not isinstance(head, str):
        head = str(head)
    pdf = simple_pdf.build_pdf(
        "学业预警日报",
        f"{rep.get('date', '')} · 第 {rep.get('week', '-')} 教学周 · 生成于 {rep.get('generated_at', '')}",
        _md_sections(rep.get("body", "")),
        footer=f"学业护航 · {head[:60]}" if head else "学业护航",
    )
    return pdf, f"每日预警日报_{rep.get('date', day)}.pdf", MIME["pdf"]
