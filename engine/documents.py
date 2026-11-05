"""文书辅助：按校内模板起草教务文书（草稿）。

三条边界写死在代码里，不靠提示词自觉：

1. **只起草，不提交**。生成物页脚、对话回答、菜单说明三处都写明「未提交至任何业务
   系统」。系统里也没有任何一条能提交教务文书的接口——权限上就做不到越权代办。
2. **模板合规**。申请类给全「基本情况 → 事由 → 时间 → 随附材料 → 审批栏 → 办理提示」，
   通知类给全「发文字号 → 主送 → 事项 → 报送 → 落款」，纪要类给全「议题 → 议定事项 →
   责任人 → 时限」。盖章位、签字栏不省略：文书最终是要走签批的。
3. **不编事实**。姓名、学号、班级、专业、辅导员、学分、风险分来自学情库，能带的都自动
   带出；日期、事由、证明、联系电话这些只有人知道的，一律留「【待填：…】」，不猜。

排版复用 exporter 的公文样式（宋体正文 + 黑体标题 + 页眉校名），产出 .docx。
"""
from __future__ import annotations

import io
from datetime import datetime

from engine import exporter

MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# 占位符统一成这个形状，前端和回答里都靠它数「还有几处要填」
TODO = "【待填：{}】"


def _t(what: str) -> str:
    return TODO.format(what)


# ---------------------------------------------------------------------------
# 六类文书
# ---------------------------------------------------------------------------
KINDS: list[dict] = [
    {
        "key": "suspend",
        "name": "休学申请",
        "desc": "因病 / 因事休学，含审批栏与材料清单",
        "who": "学生提交、教务审核",
        "header": "学生休学申请",
        "title": "学生休学申请表（草稿）",
        "blank": ["申请事由", "休学起止时间", "证明材料", "联系电话"],
        "flow": ["学生填写并签字", "辅导员核实", "院系教学负责人审批", "教务处审核", "分管校领导批准"],
        "tip": "因病休学需附二级甲等以上医院诊断证明；休学期满前 30 日须提交复学申请，逾期按学籍管理规定处理。",
    },
    {
        "key": "adjust",
        "name": "调课说明",
        "desc": "临时调课 / 补课安排，含备案栏",
        "who": "任课教师提交、院系备案",
        "header": "课程调整说明",
        "title": "课程调整说明（草稿）",
        "blank": ["课程与教师", "原上课安排", "调整后安排", "调整原因", "补课措施"],
        "flow": ["任课教师填写", "教研室主任签批", "院系教学负责人审批", "教务处备案"],
        "tip": "临时调课一般须提前 3 个工作日报院系备案；补课不占用考试周，同一天调整超过 2 节需教务处同意。",
    },
    {
        "key": "exempt",
        "name": "免修申请",
        "desc": "已修 / 持证免修，含依据与承诺",
        "who": "学生提交、教务审核",
        "header": "课程免修申请",
        "title": "课程免修申请表（草稿）",
        "blank": ["申请免修课程", "免修依据", "免修方式", "证明材料"],
        "flow": ["学生提交依据材料", "任课教师审核", "教研室主任复核", "院系审批", "教务处认定"],
        "tip": "免修不免考的课程仍须参加期末考核，卷面 ≥ 60 分才记学分；证书类免修以学校当年公布的目录为准。",
    },
    {
        "key": "review",
        "name": "成绩复核申请",
        "desc": "卷面 / 平时分 / 登分差错，含时限",
        "who": "学生提交、教务复核",
        "header": "成绩复核申请",
        "title": "学生成绩复核申请表（草稿）",
        "blank": ["复核课程与原成绩", "复核理由", "复核范围", "申请时限"],
        "flow": ["学生在时限内提交", "院系受理登记", "教务处组织复核", "书面反馈结果"],
        "tip": "复核只查漏评、错评、合分与登分错误，不重新评分；须在成绩公布后 5 个工作日内提出。",
    },
    {
        "key": "notice",
        "name": "教务通知",
        "desc": "发文格式，含主送、事项、报送时限",
        "who": "教务拟稿、领导签发",
        "header": "教务处通知",
        "title": "教务处通知（草稿）",
        "blank": ["事由", "主送单位", "时间安排", "具体要求", "报送时限与联系人"],
        "flow": ["教务拟稿", "处长核稿", "分管校领导签发", "办公室编号印发"],
        "tip": "教务通知要有发文字号、明确主送、可执行的时限和联系人，缺一项办公室不予印发。",
    },
    {
        "key": "minutes",
        "name": "会议纪要",
        "desc": "议题、议定事项、责任人与时限",
        "who": "记录人整理、主持人审定",
        "header": "会议纪要",
        "title": "会议纪要（草稿）",
        "blank": ["会议名称与时间地点", "参会人员", "议题", "议定事项与责任人"],
        "flow": ["记录人整理", "主持人审定", "发参会人员确认", "办公室归档"],
        "tip": "议定事项必须落到责任人和完成时限，否则下次会议无法复盘。",
    },
]

BY_KEY = {x["key"]: x for x in KINDS}

# 申请类文书要带学生的在校情况；通知与纪要不涉及具体学生
STUDENT_KINDS = {"suspend", "exempt", "review"}


def context(engine, sid: str | None, profile: dict | None, note: str = "") -> dict:
    """把「谁在起草、给谁起草、今天几号」收成一个 ctx，六类模板共用。

    note 是用户在输入框里补的那句话，只作参考，不会当成事实写进文书。
    """
    student = None
    if sid:
        try:
            s = engine.get(sid)
            r = engine.score(sid)
            student = {
                "name": s.get("name") or "",
                "sid": s.get("id") or sid,
                "class_name": s.get("class_name") or "",
                "major": s.get("major") or "",
                "grade": s.get("grade") or "",
                "term": s.get("term") or "",
                "advisor": s.get("advisor") or "",
                "credits": s.get("credits") or {},
                "history": s.get("history") or {},
                "risk": {"score": r.get("score"), "level_label": r.get("level_label")},
                "courses": len(s.get("courses") or []),
            }
        except KeyError:
            student = None
    p = profile or {}
    return {
        "school": exporter.SCHOOL_NAME,
        "today": datetime.now().strftime("%Y 年 %m 月 %d 日"),
        "year": datetime.now().strftime("%Y"),
        "student": student,
        "operator": {
            "name": p.get("name") or "",
            "role": p.get("role") or "",
            "class_name": p.get("class_name") or "",
        },
        "note": (note or "").strip(),
    }


def _student_rows(st: dict) -> list[str]:
    return [
        "| 姓名 | {} | 学号 | {} |".format(st.get("name") or "", st.get("sid") or ""),
        "| 班级 | {} | 专业 | {} |".format(st.get("class_name") or "", st.get("major") or ""),
        "| 年级 | {} | 学期 | {} |".format(st.get("grade") or "", st.get("term") or ""),
        "| 辅导员 | {} | 联系电话 | {} |".format(st.get("advisor") or "", _t("本人手机号")),
    ]


def _approval(head: list[str], blank_row: bool = False) -> list[str]:
    """审批栏：表头 + 分隔行。

    blank_row 只给「后面不自己加行」的调用方用（如调课说明的四栏签批）；
    其余模板紧跟着逐行 append，多垫一行空行会印出一条多余的横线格。
    """
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    if blank_row:
        # 空单元格会被排成一条细线，垫一个全角空格撑出一行签名的高度
        lines.append("|" + " |".join(["\u3000"] * len(head)) + " |")
    return lines


# ---------------------------------------------------------------------------
# 各类正文
# ---------------------------------------------------------------------------
def _suspend(ctx: dict) -> list[str]:
    st = ctx["student"] or {}
    c = st.get("credits") or {}
    h = st.get("history") or {}
    rk = st.get("risk") or {}
    lines = ["### 一、申请人基本情况"]
    lines += _student_rows(st)
    lines += [
        "",
        "### 二、申请事由",
        f"本人因{_t('如“确诊××疾病，需连续治疗三个月”')}，无法坚持正常学习，经与家长商量，"
        "申请休学。（提示：事由须与所附证明材料一致；因病休学需附二级甲等以上医院诊断证明及病历。）",
        "",
        "### 三、申请休学时间",
        f"自{_t('20×× 年 ×× 月')}起至{_t('20×× 年 ×× 月')}止，共{_t('1')}学年。",
        "（提示：休学一般以学年为期，累计不得超过学校学籍管理规定的最长年限。）",
        "",
        "### 四、在校学业情况（系统自动带出）",
        f"- 已修学分：{c.get('earned', '—')} / 培养方案 {c.get('plan_total', '—')} 学分",
        f"- 本学期在修课程：{st.get('courses', '—')} 门；累计不及格 {h.get('failed_credits', '—')} 学分",
        f"- 当前学业风险：{rk.get('score', '—')} 分（{rk.get('level_label', '—')}）",
        "",
        "### 五、随附材料（缺一不予受理）",
        "1. 本人书面申请（签名并按手印）；",
        f"2. 证明材料：{_t('诊断证明 / 入伍通知书 / 其他')}；",
        "3. 家长知情同意书（家长签字）；",
        "4. 学生证复印件。",
        "",
        "### 六、审批意见",
    ]
    lines += _approval(["环节", "意见", "签字", "日期"])
    for step in ["辅导员", "院系教学负责人", "教务处", "分管校领导"]:
        lines.append(f"| {step} | | | |")
    lines += [
        "",
        "### 七、办理提示",
        "1. 本表填写完整后交院系教学秘书，由院系统一报教务处；",
        "2. 休学期满前 30 日须提交复学申请，逾期按学籍管理规定处理；",
        "3. 本表一式三份：学生本人、院系、教务处各存一份。",
    ]
    return lines


def _adjust(ctx: dict) -> list[str]:
    return [
        "### 一、课程与教师",
        "| 课程名称 | " + _t("课程名") + " | 课程代码 | " + _t("代码") + " |",
        "| 任课教师 | " + _t("姓名") + " | 上课班级 | " + _t("班级") + " |",
        "| 学分 / 学时 | " + _t("如 3 学分 / 48 学时") + " | 修课人数 | " + _t("人数") + " |",
        "",
        "### 二、原上课安排",
        f"- 时间：{_t('第 × 周 星期 × 第 ×–× 节')}",
        f"- 地点：{_t('教学楼 ×××')}",
        "",
        "### 三、调整后安排",
        f"- 时间：{_t('第 × 周 星期 × 第 ×–× 节')}",
        f"- 地点：{_t('教学楼 ×××')}",
        f"- 方式：随堂顺延 / 集中补课 / 线上补课{_t('三选一')}",
        "",
        "### 四、调整原因",
        f"{_t('如“任课教师因公出差”“教室设备检修”')}；属临时调课的，请注明是否已向院系报备。",
        "",
        "### 五、对教学进度的影响与补救",
        f"- 受影响课时：{_t('×')} 学时；",
        f"- 补救措施：{_t('顺延一周 / 周末补课 / 线上答疑')}；",
        f"- 已通知学生方式：课堂口头 / 班级群 / 教务系统公告{_t('三选一')}。",
        "",
        "### 六、审批与备案",
    ] + _approval(["任课教师", "教研室主任", "院系教学负责人", "教务处备案"], blank_row=True)


def _exempt(ctx: dict) -> list[str]:
    st = ctx["student"] or {}
    lines = ["### 一、申请人"]
    lines += _student_rows(st)
    lines += [
        "",
        "### 二、申请免修课程",
        "| 课程名称 | " + _t("课程名") + " | 课程代码 | " + _t("代码") + " |",
        "| 学分 | " + _t("学分") + " | 开课学期 | " + _t("学期") + " |",
        "",
        "### 三、申请依据（勾选其一并附证明）",
        "□ 已修读同名或相近课程且成绩合格（附成绩单）；",
        "□ 取得与课程对应的职业资格 / 等级证书（附证书）；",
        "□ 转学、转专业前已修读并考核合格（附原校成绩单）；",
        f"□ 其他：{_t('说明')}。",
        "",
        "### 四、免修方式",
        "□ 免修不免考：参加期末考核，卷面 ≥ 60 分记学分；",
        "□ 直接认定学分（限学校认定的证书类课程）。",
        "",
        "### 五、承诺",
        "本人承诺所提交材料真实有效；如经查实弄虚作假，同意按学校学籍管理规定处理。",
        "",
        "### 六、审批",
    ] + _approval(["任课教师（是否同意）", "教研室主任", "院系教学负责人", "教务处认定"], blank_row=True)
    return lines


def _review(ctx: dict) -> list[str]:
    st = ctx["student"] or {}
    lines = ["### 一、申请人"]
    lines += _student_rows(st)
    lines += [
        "",
        "### 二、申请复核的课程与成绩",
        "| 课程名称 | " + _t("课程名") + " | 课程代码 | " + _t("代码") + " |",
        "| 学分 | " + _t("学分") + " | 原成绩 | " + _t("分数") + " |",
        "| 考核方式 | " + _t("考试 / 考查") + " | 成绩公布日期 | " + _t("日期") + " |",
        "",
        "### 三、复核理由",
        f"{_t('如“卷面第三题得分与本人作答不符”“平时分未计入”')}；请具体到题号或计分项，"
        "不要只写“觉得分数低”。",
        "",
        "### 四、复核范围（勾选）",
        "□ 卷面漏评、错评、合分错误；",
        "□ 平时成绩（作业、实验、考勤）漏记或计算错误；",
        "□ 登分、录入错误；",
        f"□ 其他：{_t('说明')}。",
        "",
        "### 五、申请时限确认",
        f"本人已知悉：成绩复核应在成绩公布后{_t('×')}个工作日内提出，逾期不再受理；"
        "复核结果为最终成绩，不再重复受理。",
        "",
        "### 六、受理与复核结果",
    ] + _approval(["受理人", "受理日期", "复核人", "复核结论", "反馈日期"], blank_row=True)
    return lines


def _notice(ctx: dict) -> list[str]:
    op = ctx["operator"]
    return [
        f"**{ctx['school']} 教务处**",
        "",
        f"教务〔{ctx['year']}〕{_t('××')} 号",
        "",
        "### 一、事由",
        f"{_t('如“关于开展 2026—2027 学年第一学期期中教学检查的通知”')}",
        "",
        "### 二、主送",
        f"{_t('各院（系、部）、各教学班')}：",
        "",
        "### 三、正文",
        f"为{_t('目的')}，现将有关事项通知如下：",
        "",
        "（一）时间安排",
        f"{_t('起止日期、关键节点')}",
        "",
        "（二）对象与范围",
        f"{_t('涉及年级、专业、班级')}",
        "",
        "（三）具体要求",
        f"1. {_t('要求一')}",
        f"2. {_t('要求二')}",
        "",
        "（四）材料报送",
        f"请于{_t('日期')}前将{_t('材料名称')}报教务处（联系人：{_t('姓名')}，"
        f"电话：{_t('办公电话')}，邮箱：{_t('邮箱')}）。",
        "",
        "### 四、其他",
        "本通知自发布之日起执行，由教务处负责解释。",
        "",
        f"拟稿：{op.get('name') or _t('拟稿人')}　　核稿：{_t('核稿人')}　　签发：{_t('签发人')}",
    ]


def _minutes(ctx: dict) -> list[str]:
    return [
        "### 一、会议基本情况",
        "| 会议名称 | " + _t("会议名称") + " | 会议时间 | " + _t("日期 时段") + " |",
        "| 会议地点 | " + _t("地点") + " | 会议形式 | 线下 / 线上 / 混合 |",
        "| 主持人 | " + _t("姓名") + " | 记录人 | " + _t("姓名") + " |",
        "| 参会人员 | " + _t("姓名、部门") + " | 缺席人员 | " + _t("姓名及原因") + " |",
        "",
        "### 二、议题",
        f"1. {_t('议题一')}",
        f"2. {_t('议题二')}",
        "",
        "### 三、汇报与讨论要点",
        f"- {_t('发言要点，按人记录，只记观点不记原话')}",
        "",
        "### 四、议定事项",
        "| 序号 | 议定事项 | 责任人 | 完成时限 |",
        "|---|---|---|---|",
        "| 1 |  |  |  |",
        "| 2 |  |  |  |",
        "",
        "### 五、跟踪与归档",
        f"- 下次会议时间：{_t('日期')}；",
        f"- 本纪要于{_t('日期')}前发参会人员确认，无异议后归档；",
        "- 议定事项纳入下次会议第一项议题复盘。",
    ]


_BUILDERS = {
    "suspend": _suspend,
    "adjust": _adjust,
    "exempt": _exempt,
    "review": _review,
    "notice": _notice,
    "minutes": _minutes,
}

FOOTNOTE = ("本文件由「学业护航」按校内模板自动起草，仅供内部流转，**未提交至任何业务系统**。"
            "正式提交前须经教务人工审核、签字盖章，并按学校流程办理。")


def filename(key: str, ctx: dict) -> str:
    meta = BY_KEY[key]
    day = datetime.now().strftime("%Y%m%d")
    # 只有申请类文书是「某个学生的」；调课/通知/纪要是教务自己的文书，
    # 挂上学生名会让归档的人以为这是给学生开的。
    who = (ctx.get("student") or {}).get("name") if key in STUDENT_KINDS else ""
    return f"{meta['name']}_{who or '教务'}_{day}.docx"


def brief(key: str, ctx: dict) -> dict:
    """起草说明：给对话回答用，和文件同源。

    auto: 系统已经带出的字段；blank: 还需要人工补的；flow: 这份文书要走的签批链。
    """
    meta = BY_KEY[key]
    st = ctx.get("student") or {}
    auto: list[tuple[str, str]] = []
    if st:
        auto = [
            ("姓名", st.get("name") or ""),
            ("学号", st.get("sid") or ""),
            ("班级", st.get("class_name") or ""),
            ("专业", st.get("major") or ""),
            ("辅导员", st.get("advisor") or ""),
        ]
    if key in STUDENT_KINDS and st:
        rk = st.get("risk") or {}
        auto.append(("当前风险", f"{rk.get('score', '—')} 分（{rk.get('level_label', '—')}）"))
    auto = [(k, v) for k, v in auto if v]
    return {
        "key": key,
        "name": meta["name"],
        "title": meta["title"],
        "file": filename(key, ctx),
        "auto": auto,
        "blank": list(meta["blank"]),
        "flow": list(meta["flow"]),
        "operator": (ctx.get("operator") or {}).get("name") or "",
    }


def render(key: str, ctx: dict) -> tuple[bytes, str, str]:
    """返回 (docx 字节, 文件名, MIME)。未知 key 抛 KeyError。"""
    meta = BY_KEY[key]
    doc = exporter._new_doc(meta["header"])  # noqa: SLF001 - 与其它文书复用同一套公文样式
    # 副标题只写「这份文书属于谁」：申请类写学生，通知/纪要写拟稿人或科室
    who = ""
    if key in STUDENT_KINDS:
        who = (ctx.get("student") or {}).get("name") or ""
    if not who:
        who = (ctx.get("operator") or {}).get("name") or ""
    sub = " · ".join(x for x in [who, ctx.get("today") or ""] if x)
    exporter._title(doc, meta["title"], sub)  # noqa: SLF001
    exporter.md_to_docx(doc, "\n".join(_BUILDERS[key](ctx)))
    # 起草声明：放在落款之前，读文件的人第一眼就知道这不是已生效的正式文书
    p = doc.add_paragraph()
    exporter._set_font(p.add_run("— 以下为起草说明 —"), size=9, color=exporter.MUTED)  # noqa: SLF001
    exporter.md_to_docx(doc, FOOTNOTE)
    exporter._sign(doc, who="学业护航 · 文书辅助（草稿）")  # noqa: SLF001
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue(), filename(key, ctx), MIME_DOCX
