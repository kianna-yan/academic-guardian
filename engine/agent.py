"""Agent 编排层：意图识别 → 指代消解 → 工具调用 → 事实拼装 →（可选）大模型润色。

设计原则
- 智能体为主：对话是主入口，页面只是它的仪表盘。每个角色都能在对话里完成
  「查、问、生成文书、记录动作」四件事，不必点页面。
- 事实由工具提供：没有大模型 key 时走确定性链路，回答里的每个数字都来自工具
  返回，不会出现"模型编造分数"；接入模型后只负责组织语言。
- 多轮记忆：按账号保留最近几轮，"他呢 / 为什么 / 第 3 个是谁"这类指代
  靠它消解；记忆同时喂给大模型做上下文。
- 思考链：关键判断（在说谁、走哪条路）通过 thought 事件实时推给前端。
"""
from __future__ import annotations

import re
import time

from . import actions as actions_mod
from . import llm, trend as trend_mod
from .evidence import build as build_evidence
from .letters import counselor_brief
from .memory import ConversationMemory, memory_key
from .rag import KnowledgeBase

POLICY_WORDS = ["校规", "规定", "政策", "教育部", "降级", "劝退", "退学", "学分要求",
                "多少学分", "几门", "预警线", "通知家长", "什么时候", "多久", "文件",
                "红色预警", "黄色预警", "绿色预警", "预警等级", "红黄绿", "区别",
                "保研", "推免", "考研", "升学", "毕业要求"]
WHY_WORDS = ["为什么", "原因", "怎么回事", "怎么算", "依据", "评估", "风险分", "多少分", "严重",
             "表现", "最近怎么样", "状态", "情况怎么样", "学得怎么样"]
ADVICE_WORDS = ["怎么办", "建议", "提高", "计划", "补救", "行动", "帮我", "如何", "怎么改", "来得及",
               "能做什么", "做什么", "帮上忙", "帮什么忙", "在家", "配合", "怎么帮", "能帮", "家长能"]
ROSTER_WORDS = ["谁", "名单", "哪些", "班级", "几个人", "多少人", "学生"]
OVERVIEW_WORDS = ["整体", "全校", "概况", "分布", "统计", "总览", "情况如何"]
# 文书意图只认具体文书名；裸「通知」曾把「学校什么情况下会通知家长」
# 抢成 letter（1.8 > policy 1.2），导致学生端答成风险分——已修
LETTER_WORDS = ["告知函", "家长信", "通知书", "信件", "周报", "报告"]
# 成绩走势单独成类：「我退步了吗」「这学期在涨还是掉」都要能答
TREND_WORDS = ["趋势", "走势", "成绩变化", "退步", "进步", "下滑", "上升", "名次",
               "排名", "排第几", "曲线", "起伏", "越来越", "涨", "掉", "变化"]
# 成绩查询：分数、单科强弱、班内名次。
# 之前这一整类没有意图，全落 unknown→模型，而模型手里没有任何能取分数的工具，
# 只能答「系统里没有显示具体的课程成绩信息」——学生端、家长端、辅导员端全中招。
SCORE_WORDS = ["成绩", "分数", "考了", "考得", "多少分", "平均分", "均分", "单科",
               "哪门课", "哪一科", "最好的课", "最差的课", "最好", "最差", "最强", "最弱",
               "排名", "名次", "排第几", "第几名", "高分段", "及格率", "满分", "挂了几门"]
# 课表：哪天有课、第几节、在哪间教室。
# 页面「我的课表」一直有这份数据，但改造前没有任何工具能取到节次与教室，
# 学生问「明天有没有数据结构课」只能得到「系统里没有具体时间安排」。
SCHEDULE_WORDS = ["课表", "上课", "有课", "没课", "第几节", "几节课", "教室", "调课",
                  "哪天有", "哪天没", "在哪上", "第几周"]
# 期末试算：还没考的那场到底要拿多少分
FORECAST_WORDS = ["期末", "才不挂", "能过", "能不能过", "要考多少", "拿多少分才能",
                  "目标分", "想拿", "还有救", "稳过"]
# 课程资料：老师上传的真题 / 讲义。和「期末能过吗」要分开——前者问往年试卷内容，
# 后者问成绩预测，一个该去检索资料，一个该算分。
MATERIAL_WORDS = ["真题", "试卷", "往年", "历年", "考了什么", "考什么", "考点",
                  "讲义", "课件", "网课", "复习资料", "老师发的", "上传的资料", "题目"]
# 待办与通知：铃铛和待办列表里的东西
TODO_WORDS = ["待办", "未读", "消息", "提醒", "待处理", "要做的事", "新通知", "有没有通知"]
# 培养方案：毕业学分、必修选修
PLAN_WORDS = ["培养方案", "毕业", "总学分", "还差多少学分", "要修多少学分",
              "选修课", "必修课", "课程档案"]
# 异议：对考勤/作业记录提出的申诉，现在处理到哪一步
APPEAL_WORDS = ["异议", "申诉", "复核", "受理", "撤销记录", "提的意见"]
# 家校消息：家长与辅导员之间的往来
MSG_WORDS = ["消息", "私信", "聊天记录", "回了", "回复我", "有没有联系", "给我发"]
# 谈话要点：辅导员在对话里直接要一份提纲，不用去页面点
BRIEF_WORDS = ["谈话要点", "谈话提纲", "谈话大纲", "生成谈话", "谈一下", "怎么跟他谈",
               "怎么谈", "谈话建议", "给我一份谈话"]
# 记录动作：把谈话结果写回系统，对话即操作
RECORD_WORDS = ["记录一下", "记录", "登记", "已谈", "谈过了", "谈完了", "刚谈完",
                "已经谈话", "做了辅导", "已联系"]
# 指代与追问：这些词本身不带主题，得靠上一轮的记忆补全
PRONOUN_WORDS = ["他", "她", "这个学生", "这孩子", "那孩子", "这位同学"]
# 任课老师与联系方式：数据在每门课的 teacher_profile 里，不在校规库里
# 「几点」太泛：问「机房几点关门」也命中，答成任课老师联系方式就很离谱。
# 只留明确指向老师的词。
CONTACT_WORDS = ["老师", "任课", "教师", "电话", "邮箱", "联系方式", "办公室",
                 "答疑", "上课时间", "办公时间", "怎么联系", "office hour"]
# 考勤明细：问的是「哪几次没去」，要落到具体日期，不是风险分
ATTENDANCE_WORDS = ["缺勤", "旷课", "没去", "迟到", "考勤", "出勤", "几次课",
                    "哪天没", "请假", "缺席"]
# 作业明细：哪次没交、什么时候截止
HOMEWORK_WORDS = ["作业", "没交", "未交", "漏交", "少交", "补交", "迟交", "截止"]
# 课表与学分统计：这学期有什么课、修了多少学分
COURSE_WORDS = ["课表", "这学期有什么课", "哪些课", "修了什么", "几门课", "学分",
                "选课", "在读"]
# 导出与触达：把事实落成文件（Word/PPT）或发出去（邮件）
EXPORT_WORDS = ["导出", "下载", "打印", "word", "docx", "word文档", "成文档", "存档",
                "ppt", "pptx", "汇报", "总结", "发邮件", "发给家长", "发送", "邮件",
                "通知书", "日报", "台账导出"]
ORDINAL_RE = re.compile(r"第\s*([0-9一二三四五六七八九十]+)\s*(个|位|名|人)")
_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

# ---------------------------------------------------------------------------
# 五端人设：同一个引擎，五个端各自有不同的身份、口吻与内容边界。
# 学生端像学长辅导本人，家长端像家校沟通桥梁，导员端是同事级工作助手，
# 教务端是数据导向的管理助手——回答永远偏向对应端口该关心的事。
# ---------------------------------------------------------------------------
_BASE_RULES = ("只能使用给定的事实与条款，不得编造数字或政策。用简体中文回答，"
               "保留所有具体数字，不要使用 Markdown 标题。"
               "注意结合最近对话理解指代（比如“他”指的是谁）。")

PERSONAS: dict[str, str] = {
    "student": (
        "你是学生本人的学业辅导助手，像一位有经验又亲切的学长。"
        "只围绕这名学生自己的数据（出勤、作业、成绩、风险分）说话。"
        "语气亲切、先一句话安抚，再给出 1-2 个今天就能做的小步骤；鼓励但不夸张，不评判学生。"
        "绝不出现「约谈该学生」「写进台账」「给他生成文书」等管理视角的说法。"
        + _BASE_RULES
    ),
    "parent": (
        "你是面向家长的学业沟通助手。解释孩子的整体状况、学校的预警逻辑与相关规定，"
        "重点说家长在家能怎么配合（作息、沟通方式、督学建议）。"
        "语气平和体谅，不给孩子贴标签，不拿别的学生作比较，不透露任何其他学生的信息。"
        + _BASE_RULES
    ),
    "counselor": (
        "你是辅导员的工作助手，同事间的口吻，简洁高效、偏操作。"
        "聚焦名单研判、谈话准备、干预台账、文书生成与家校沟通要点，"
        "回答尽量给「先做什么、再做什么」的行动顺序，并点明可直接使用的指令"
        "（如「给某某生成谈话要点」「记录：已完成谈话」）。"
        "不做心理诊断，情况严重时建议转介学校心理中心。"
        + _BASE_RULES
    ),
    "admin": (
        "你是教务管理助手，正式、数据导向。"
        "聚焦全校分布、班级对比、政策条款与流程合规，"
        "回答给出结构化的数据结论和管理建议。"
        + _BASE_RULES
    ),
    "teacher": (
        "你是任课老师的教学助手，像一位备课组同事。"
        "只围绕这位老师自己教的课、以及修这些课的学生说话——考勤、作业、期中成绩、挂科风险，"
        "绝不谈论该老师未任课的班级或其他课程。"
        "语气专业务实，先给数据结论（谁缺勤最多、谁作业没交、班均多少），"
        "再给教学层面可落地的下一步（重点关注谁、作业布置是否调整、是否反馈给辅导员）。"
        "需要辅导员介入时直说「建议联系辅导员」，不替辅导员做谈话安排。"
        + _BASE_RULES
    ),
}


# 规则引擎「明确承认自己答不了」时用的话术。命中任意一句，说明本轮并没有
# 真正取到有效事实——这种情况交模型重试，比把同一段清单再念一遍有用。
_FALLBACK_MARKS = ("答不准", "我擅长帮你", "我擅长帮您看", "可以问我：")


class Agent:
    def __init__(self, engine, kb: KnowledgeBase, store,
                 memory: ConversationMemory | None = None,
                 recorder=None, mailer=None, reporter=None, checkins=None):
        self.engine = engine
        self.kb = kb
        self.store = store
        self.memory = memory
        # recorder(sid, title, note, status) -> item：把对话里的记录写回干预台账
        self.recorder = recorder
        # mailer(sid) -> {mode, ok, ...}：家长信邮件发送（SMTP 或 .eml）
        self.mailer = mailer
        # reporter() -> report dict：每日日报聚合（定时任务同款）
        self.reporter = reporter
        # checkins：学生课后自评记录库，只用于「学习轨迹」这个工具，不进风险分
        self.checkins = checkins
        # 姓名索引：240 个学生两三个字的中文姓名，直接建 dict，最长匹配优先
        self._names: dict[str, dict] = {s["name"]: s for s in engine.students}
        self._classes: list[str] = sorted({s["class_name"] for s in engine.students})
        # 教师名与课程名：用来判断「问联系方式」这句话到底有没有指向具体对象
        self._teacher_names: list[str] = sorted({
            c["teacher"] for s in engine.students for c in s["courses"] if c.get("teacher")})
        self._course_names: list[str] = sorted({
            c["name"] for s in engine.students for c in s["courses"] if c.get("name")})

    def _contact_supported(self, text: str) -> bool:
        """问联系方式时，句子里总得有个老师名或课名，否则就是关键词误命中。

        「学校机房几点关门」里有个「几点」，旧的关键词表会把它判成问老师联系方式，
        然后答出一整页办公室和邮箱——答非所问的典型。这里兜一层。
        """
        if any(n in text for n in self._teacher_names):
            return True
        if any(n in text for n in self._course_names):
            return True
        return any(k in text for k in ("老师", "教师", "任课", "邮箱", "办公室",
                                       "联系方式", "答疑", "电话", "教授"))

    # ---------- 工具 ----------
    def t_risk(self, sid: str) -> dict:
        return self.engine.score(sid)

    def t_profile(self, sid: str) -> dict:
        s = self.engine.get(sid)
        r = self.engine.score(sid)
        return {
            "id": s["id"], "name": s["name"], "class_name": s["class_name"],
            "gpa": s["history"]["gpa"], "failed_credits": s["history"]["failed_credits"],
            "credits": s["credits"], "risk": r,
        }

    # ---------- 学生本人档案：每轮回答前先把这笔账重新翻一遍 ----------
    # 风险分、考勤、作业都是会变的；上一轮说过的话不能当这一轮的事实用。
    # 用户问的往往还不是自己（「挂一科还能考研吗」问的是制度），但回答里要说
    # 「对照你的情况」，就必须先知道他现在到底什么处境，否则只能讲空话。
    _FACT_KW = {
        "risk": ["风险", "预警", "扣分", "等级", "多少分"],
        "study": ["挂", "补考", "重修", "考研", "保研", "绩点", "gpa", "成绩", "均分",
                  "毕业", "降级", "退学", "学位", "推免"],
        "attend": ["考勤", "旷课", "缺课", "迟到", "出勤", "点名", "请假"],
        "homework": ["作业", "未交", "迟交", "提交", "实验报告"],
        "credit": ["学分", "培养方案", "选课"],
        "course": ["课表", "几门课", "哪门课", "在修", "上课", "老师"],
    }

    def student_facts(self, sid: str, role: str = "student", message: str = "",
                      intent: str = "") -> dict:
        """实时查一遍学生本人的档案，返回可直接下发的结构化结果。

        字段与来源逐条标明，是为了让「它凭什么这么说」可核查：
        风险分来自六因素加权，出勤来自逐节打卡，作业来自作业平台。
        """
        t0 = time.time()
        s = self.engine.get(sid)
        r = self.engine.score(sid)
        h = s.get("history") or {}
        cr = s.get("credits") or {}
        courses = s.get("courses") or []

        absent = sum(int(c.get("absent") or 0) for c in courses)
        late = sum(int(c.get("late") or 0) for c in courses)
        held = sum(int(c.get("sessions_held") or 0) for c in courses)
        hw_all = sum(int(c.get("hw_assigned") or 0) for c in courses)
        hw_done = sum(int(c.get("hw_submitted") or 0) for c in courses)
        attend_rate = round((held - absent) / held * 100, 1) if held else 100.0
        hw_rate = round(hw_done / hw_all * 100, 1) if hw_all else 100.0
        factors = (r.get("factors") or [])[:2]
        worst = min(courses, key=lambda c: c.get("midterm") or 0) if courses else None
        trend = r.get("trend") or {}
        scope = {"student": "本人", "parent": "孩子"}.get(role, "该生")

        items = [
            {"key": "who", "label": "身份",
             "value": f"{s['name']} · {s['class_name']} · {s['major']}{s['grade']}",
             "source": "accounts · 学籍档案"},
            {"key": "risk", "label": "风险分",
             "value": f"{r.get('score')} 分 · {r.get('level_label')}"
                      + (f"（{trend.get('label')}）" if trend.get("label") else ""),
             "source": "risk_score() · 六因素加权"},
            {"key": "factor", "label": "主要扣分",
             "value": "、".join(f"{f.get('label')} {f.get('points')}" for f in factors) or "—",
             "source": "risk_score() · 因素拆解"},
            {"key": "study", "label": "学业",
             "value": f"GPA {h.get('gpa', '—')} · 均分 {h.get('avg', '—')} · "
                      f"累计挂科 {h.get('failed_credits', '—')} 学分",
             "source": "scores · 历史成绩"},
            {"key": "credit", "label": "学分",
             "value": f"已修 {cr.get('earned', '—')}/{cr.get('plan_total', '—')} · "
                      f"本学期在修 {cr.get('in_progress', '—')}",
             "source": "curriculum · 培养方案"},
            {"key": "attend", "label": "考勤",
             "value": f"出勤率 {attend_rate}% · 旷课 {absent} 次 · 迟到 {late} 次",
             "source": "checkins · 逐节打卡"},
            {"key": "homework", "label": "作业",
             "value": f"提交率 {hw_rate}%（{hw_done}/{hw_all}）",
             "source": "homework · 作业平台"},
            {"key": "course", "label": "在修课程",
             "value": f"{len(courses)} 门" + (
                 f"，最低 {worst.get('name')} {worst.get('midterm')} 分" if worst else ""),
             "source": "courses · 本学期课表"},
        ]

        text = (message or "").lower()
        hit = {k: any(w in text for w in ws) for k, ws in self._FACT_KW.items()}
        # 问制度 / 问原因 / 问怎么办时，答案一定要「对照他自己」，
        # 所以风险分与扣分项算这一问真的用到了，不该在界面上灰掉。
        if intent in ("policy", "why", "advice", "trend"):
            for k in ("risk", "factor", "study"):
                hit[k] = True
        for it in items:
            it["hit"] = bool(hit.get(it["key"]))
        if not any(hit.values()):          # 没点名字段就按「体检」给：风险 + 学业
            for it in items:
                it["hit"] = it["key"] in ("risk", "study")

        return {
            "who": s["name"],
            "sid": sid,
            "scope": scope,
            "query": (message or "")[:40],
            "fields": [it["label"] for it in items if it["hit"]],
            "items": items,
            "brief": (f"风险 {r.get('score')} 分（{r.get('level_label')}）、"
                      f"累计挂科 {h.get('failed_credits', '—')} 学分、"
                      f"出勤 {attend_rate}%、作业 {hw_rate}%"),
            "as_of": time.strftime("%m-%d %H:%M"),
            "ms": round((time.time() - t0) * 1000, 2),
        }

    def t_actions(self, sid: str) -> list[dict]:
        return self.engine.interventions(sid)

    def t_policy(self, query: str, school: str | None = None,
                 context: str = "", top_k: int = 4,
                 min_score: float = 0.3, kind: str | None = None,
                 limit: int = 3) -> list[dict]:
        # policy 检索跨全库：评委/学生问的是通用规则，不该被学校名挡住具体条款
        # （如「挂多少学分会被降级」应召回华南理工「降级试读条件·25 学分」，
        #  而非只剩教育部通用政策）。school 参数保留兼容调用，内部不限定。
        # context 是上一轮用户原话，交给 query 改写补全「那保研呢」这类省略句。
        # kind="resource" 只留教师上传的真题/讲义，用来和校规条款分开；
        # limit 是最终给模型看的条数——课程资料常被切成一题一段，要多给几条。
        hits = self.kb.search(query, top_k=top_k, school=None,
                              min_score=min_score, context=context)
        if kind:
            hits = [h for h in hits if h.get("kind") == kind]
        return hits[:limit]

    def _recall_material(self, mkey: str, question: str) -> tuple[str, dict | None, str]:
        """这一轮没带附件，但用户说的是「刚才那张图」。把材料记忆翻出来。

        两层：先把上次的识别结果原文回灌（够答大部分追问）；问到具体数字 /
        行 / 名字这类细节时，再把原图重新送一次视觉模型按新问题复核——
        这样答的是图上写的，不是模型对上一轮的模糊回忆。
        """
        from . import media_memory as mm
        from . import multimodal

        store = mm.media_memory()
        rec = store.latest(mkey)
        if not rec or not mm.wants_recall(question):
            return "", None, ""

        reread = ""
        trace: dict | None = None
        images = rec.get("images") or []
        if images and mm.wants_detail(question):
            prompt = (
                f"用户之前上传了这张图片，现在追问：{question}\n"
                "请只回答这个追问：照图片里能看到的原文、数字、行次回答，"
                "结论在前、不要复述整张图；图片里确实没有的信息就直接说看不到。"
            )
            res = multimodal.vision([i["data"] for i in images], prompt)
            if res.get("ok"):
                reread = res["text"]
                trace = {
                    "tool": "recall_material",
                    "label": "重看上次的图",
                    "args": {"images": len(images), "question": question[:40]},
                    "ms": res.get("ms", 0),
                    "evidence": {
                        "source": "会话材料记忆",
                        "table": f"{len(images)} 张原图 · {res.get('model', '')}",
                        "rows": len(images),
                        "unit": "张图",
                        "ts": time.strftime("%H:%M:%S"),
                        "ms": res.get("ms", 0),
                        "detail": "追问细节时按原图复核，不靠上一轮的概括",
                    },
                }
            else:
                trace = {
                    "tool": "recall_material",
                    "label": "重看上次的图失败",
                    "args": {"images": len(images)},
                    "ms": res.get("ms", 0),
                    "evidence": {
                        "source": "会话材料记忆",
                        "table": "原图复核",
                        "rows": 0,
                        "unit": "张图",
                        "ts": time.strftime("%H:%M:%S"),
                        "ms": res.get("ms", 0),
                        "detail": res.get("note") or "",
                    },
                }
        return mm.as_block(rec, question, reread), trace, reread

    def t_roster(self, class_name: str | None = None, level: str | None = None, limit: int = 8) -> list[dict]:
        return self.engine.roster(class_name, level)[:limit]

    def t_overview(self) -> dict:
        return self.engine.overview()

    def t_trend(self, sid: str) -> dict:
        """成绩走势：只回结论和数字，具体图表由前端画。"""
        gt = trend_mod.grade_trend(self.engine.get(sid))
        return {
            "summary": gt["summary"],
            "slope": gt["slope"],
            "now": gt["now"],
            "rank": gt["rank"],
            "watch": gt["watch"],
            "courses": [
                {
                    "name": c["name"],
                    "scores": [p["score"] for p in c["points"]],
                    "delta": c["delta"],
                    "label": c["trend_label"],
                }
                for c in gt["courses"]
            ],
        }

    def t_brief(self, sid: str, school: str | None = None) -> dict:
        """谈话要点：直接复用文书模块，对话里要提纲不用切页面。"""
        return counselor_brief(self.engine, self.kb, sid, school)

    def t_teacher_view(self, teacher_name: str) -> dict:
        """任课教师视角：他教的课 + 课上的学生（含风险分与该课明细）。"""
        return self.engine.teacher_view(teacher_name)

    def t_record(self, sid: str, title: str, note: str, status: str = "已完成") -> dict:
        if not self.recorder:
            return {"ok": False, "message": "当前会话未接入台账，请在学生页手动添加记录"}
        return {"ok": True, "item": self.recorder(sid, title, note, status)}

    # ---------- 导出与触达 ----------
    def _export_kind(self, text: str) -> str:
        """从问法判断要导什么。"""
        if any(w in text for w in ["家长信"]):
            return "parent"
        if any(w in text for w in ["通知书"]):
            return "notice"
        if any(w in text for w in ["谈话要点", "谈话提纲", "提纲"]):
            return "brief"
        if any(w in text for w in ["台账"]):
            return "interventions"
        if any(w in text for w in ["日报"]):
            return "daily"
        if any(w in text for w in ["汇报", "ppt", "总结"]):
            return "semester"
        return "student_letter"

    def _compose_export(self, res: dict, who: str = "") -> str:
        if not res.get("ok"):
            return res.get("message", "导出失败。")
        tail = f"（{who}）" if who else ""
        return (f"**{res['label']}**{tail} 已按当前数据排版生成：\n\n"
                f"[点击下载]({res['url']})\n\n"
                f"文件可打印归档；打印盖章后送教务存档即可。")

    def t_export(self, kind: str, sid: str | None = None) -> dict:
        """产出可下载文件：家长信/告知函/谈话要点/通知书/台账/日报 → docx，学期汇报 → pptx。
        URL 由前端补 ag_token 后可直接 <a> 下载。"""
        catalog = {
            "parent": ("/api/export/letter/{sid}?type=parent", "家长信（Word）"),
            "student_letter": ("/api/export/letter/{sid}?type=student", "学业预警告知函（Word）"),
            "brief": ("/api/export/letter/{sid}?type=counselor", "谈话要点（Word）"),
            "notice": ("/api/export/notice/{sid}", "学业预警通知书（Word，含回执）"),
            "interventions": ("/api/export/interventions", "干预台账（Word）"),
            "daily": ("/api/export/daily-report", "每日预警日报（Word）"),
            "semester": ("/api/export/semester", "学期汇报（PPT）"),
        }
        if kind not in catalog:
            return {"ok": False, "message": f"暂不支持的导出类型：{kind}"}
        path, label = catalog[kind]
        url = path.format(sid=sid) if sid else path
        return {"ok": True, "kind": kind, "url": url, "label": label}

    def t_send_letter(self, sid: str) -> dict:
        """把家长信发给家长。SMTP 已配置就真发；未配置返回 .eml 下载（收件人已填好）。"""
        if not self.mailer:
            return {"ok": False, "message": "当前会话未接入邮件通道"}
        return self.mailer(sid)

    def t_daily_report(self) -> dict:
        """每日预警日报的数据面：定时任务与对话问答共用同一份聚合。"""
        if not self.reporter:
            return {"ok": False, "message": "当前会话未接入日报聚合"}
        return self.reporter()

    def _compose_trend(self, t: dict) -> str:
        lines = [f"**成绩走势**：{t['summary']}"]
        if t["courses"]:
            down = [c for c in t["courses"] if c["delta"] <= -4]
            up = [c for c in t["courses"] if c["delta"] >= 4]
            if down:
                lines.append("在往下走的是：" + "、".join(
                    f"{c['name']}（{'→'.join(str(s) for s in c['scores'])}）" for c in down[:3]))
            if up:
                lines.append("还在往上走的是：" + "、".join(
                    f"{c['name']}（{c['delta']:+d} 分）" for c in up[:3]))
        if t["watch"]:
            lines.append(f"最该盯住：{t['watch']}。")
        return "\n".join(f"- {x}" if i else x for i, x in enumerate(lines))

    # ---------- 指代消解：这轮在说谁 ----------
    def _match_name(self, text: str) -> dict | None:
        """消息里出现学生姓名 → 直接定位。最长名优先，避免「王芳」误吃「王小芳」。"""
        best = None
        for name in self._names:
            if name in text and (best is None or len(name) > len(best)):
                best = name
        return self._names[best] if best else None

    def _match_class(self, text: str) -> str | None:
        for c in self._classes:
            if c in text:
                return c
        # 「3班」「2405班」这类口语指法
        m = re.search(r"(\d{2,4})\s*班", text)
        if m:
            tail = m.group(1)
            for c in self._classes:
                if c.endswith(tail):
                    return c
        # 「软件2401」这类专业名对不上库里的「计科2401」：
        # 交给 scores.class_name_of 按班号/近似度认一次，认不出才返回 None。
        # 不认的话会静默变成"全部班级"，用户以为在问一个班，拿到的是全校。
        try:
            from . import scores as scores_mod
            hit, _cands = scores_mod.class_name_of(self.engine, text)
            if hit:
                return hit
        except Exception:  # noqa: BLE001
            pass
        return None

    def _match_ordinal(self, text: str) -> int | None:
        m = ORDINAL_RE.search(text)
        if not m:
            return None
        raw = m.group(1)
        if raw.isdigit():
            return int(raw)
        if raw in _CN_NUM:
            return _CN_NUM[raw]
        return None

    def resolve_target(self, text: str, role: str, sid: str | None, last: dict | None):
        """返回 (sid, thought)：thought 是给用户看的思考链。

        学生/家长身份固定；辅导员/教务按 姓名 → 序数 → 代词 → 上一轮 依次消解。
        名单/全校类问题不绑定上一轮的学生，否则"谁的风险上升最快"会被记忆带偏。
        """
        if role in ("student", "parent"):
            return sid, None

        named = self._match_name(text)
        if named:
            other = f"，不是上一轮说的那位" if last and last.get("sid") not in (None, named["id"]) else ""
            return named["id"], f"这句话里出现了「{named['name']}」（{named['class_name']}），就按他来查。"

        cls = self._match_class(text)
        if cls:
            return None, f"问的是「{cls}」整个班的情况，我去拉这个班的名单。"

        n = self._match_ordinal(text)
        if n and last and last.get("roster"):
            roster = last["roster"]
            if 1 <= n <= len(roster):
                row = roster[n - 1]
                return row["id"], f"「第{n}个」指的是上一轮名单里的 {row['name']}（{row['class_name']}）。"
            return None, f"上一轮名单里只有 {len(roster)} 个人，没有第 {n} 个。"

        # 名单/全局类问法：不绑定上一轮学生，问题本身就是"一批人"
        if any(w in text for w in ROSTER_WORDS + OVERVIEW_WORDS):
            return None, None

        if any(w in text for w in PRONOUN_WORDS) and last and last.get("sid"):
            s = self.engine.get(last["sid"])
            return last["sid"], f"「他」说的是上一轮的 {s['name']}，接着他的数据说。"

        if last and last.get("sid"):
            s = self.engine.get(last["sid"])
            return last["sid"], f"没提到具体姓名，默认继续聊上一轮的 {s['name']}。"
        return sid, None

    # ---------- 意图 ----------
    def _intent(self, msg: str) -> str:
        text = msg.lower()
        def hit(words):
            return sum(1 for w in words if w in text)
        scores = {
            "policy": hit(POLICY_WORDS) * 1.2,
            "why": hit(WHY_WORDS),
            "advice": hit(ADVICE_WORDS),
            "roster": hit(ROSTER_WORDS),
            "overview": hit(OVERVIEW_WORDS) * 1.5,
            "letter": hit(LETTER_WORDS) * 1.8,
            "trend": hit(TREND_WORDS) * 1.3,
            "brief": hit(BRIEF_WORDS) * 2.2,
            "record": hit(RECORD_WORDS) * 2.6,
            "export": hit(EXPORT_WORDS) * 2.4,
            "contact": hit(CONTACT_WORDS) * 1.8,
            "attendance": hit(ATTENDANCE_WORDS) * 1.8,
            "homework": hit(HOMEWORK_WORDS) * 1.8,
            "course": hit(COURSE_WORDS) * 1.8,
            "score": hit(SCORE_WORDS) * 1.25,
            "timetable": hit(SCHEDULE_WORDS) * 1.6,
            "forecast": hit(FORECAST_WORDS) * 1.5,
            "material": hit(MATERIAL_WORDS) * 2.6,
            "todo": hit(TODO_WORDS) * 1.4,
            "plan": hit(PLAN_WORDS) * 1.5,
            "appeal": hit(APPEAL_WORDS) * 2.6,
            "message": hit(MSG_WORDS) * 1.6,
            "class_report": 0.0,
        }
        if "怎么办" in text or "建议" in text:
            scores["advice"] += 1.5
        # 「去年期末考了什么」问的是往年试卷，不是「期末能过吗」的成绩预测：
        # material 命中时把 forecast 压下去，否则资料检索永远轮不到。
        if hit(MATERIAL_WORDS):
            scores["forecast"] -= 2.0
        if "降级" in text or "劝退" in text or "规定" in text:
            scores["policy"] += 2
        # 「风险分是怎么算的」「红黄绿怎么划」问的是系统的评分口径，
        # 答案在知识库的系统规则里，不该模型凭印象讲——让它走检索，带出处。
        # 但「把某人风险分改成 20」是要求改数据，不是问口径，必须排除。
        if (any(w in text for w in ["风险分", "评分口径", "预警等级", "阈值", "红黄绿",
                                    "怎么算出来的", "如何计算"])
                and not any(w in text for w in ["改", "设成", "调成", "提高", "降低",
                                                "加", "减", "变成", "写成", "重算"])
                # 「我的风险分为什么这么高」是问自己的情况，不是问口径
                and not any(w in text for w in ["为什么", "这么高", "怎么回事", "怎么办"])):
            scores["policy"] += 2.5
            scores["score"] -= 1.0
        # "我这学期在涨还是在掉" 这类问法，trend 必须压过 why/advice
        if any(w in text for w in ["趋势", "走势", "退步", "进步", "名次", "成绩变化"]):
            scores["trend"] += 2.5
        # 纯记录句式（"记录：今天谈过了"）别被 why 抢走
        if re.search(r"记录[:：]", text) or text.startswith("记录"):
            scores["record"] += 3
        # 明确要文件的动作词，export 压过 letter（letter 只是"看看文书"）
        if any(w in text for w in ["导出", "下载", "打印", "word", "docx", "ppt", "发邮件", "发给家长"]):
            scores["export"] += 3
        # 「学校什么情况下会通知家长」是问制度，必须走 policy 检索条款，
        # 不能被任何文书/风险类词抢走
        if "通知" in text and any(w in text for w in ["家长", "什么情况", "什么时候", "什么条件", "多久"]):
            scores["policy"] += 3
        # 「这学期修了多少学分」是学分统计；只有带「降级/退学」语境才是政策条款
        if "学分" in text and not any(w in text for w in ["降级", "劝退", "退学", "规定", "要求"]):
            scores["course"] += 1.2
        # 「哪门课最好/考了多少分」问的是分数本身，不是走势也不是名单。
        # 出现涨/掉/趋势这类词时不算——「我的成绩涨还是掉」问的是走势，要让 trend 赢，
        # 否则会被这里的加权抢走，答成一堆静态分数。
        if (any(w in text for w in ["成绩", "分数", "哪门课", "哪一科", "最好的课", "最差的课",
                                    "平均分", "考了", "考得", "分最高", "最高分", "多少分"])
                and not any(w in text for w in ["涨", "掉", "趋势", "走势", "退步", "进步",
                                                "下滑", "上升", "变化", "排名变化"])):
            scores["score"] += 1.4
        # 老师联系方式必然伴随课程或「老师」本身，别让「数据结构」里的「结构」类词干扰
        if any(w in text for w in ["电话", "邮箱", "联系方式", "办公室", "答疑"]):
            scores["contact"] += 2
        # 「明天有没有课 / 周三第几节在哪上」：属于课表，不能被「课」类词带走
        if any(w in text for w in ["课表", "有课", "没课", "上课", "第几节", "几节课",
                                   "教室", "调课"]):
            scores["timetable"] += 2.2
        elif any(w in text for w in ["明天", "后天", "今天", "下周", "这周", "本周",
                                     "周一", "周二", "周三", "周四", "周五", "周末"]) and "课" in text:
            scores["timetable"] += 1.8
        # 「答疑几点」问的是老师，「周二几点上课」问的是课表——后者不能被联系方式抢走
        if any(w in text for w in ["答疑", "办公室", "邮箱", "电话", "联系方式", "office"]):
            scores["contact"] += 1.5
            scores["timetable"] -= 2.5
        # 期末试算：「我期末要考多少才不挂」既含「多少分」也含「期末」，要落在试算上
        if "期末" in text or any(w in text for w in ["才不挂", "能不能过", "还有救", "要考多少"]):
            scores["forecast"] += 2.2
            if not any(w in text for w in ["已经考", "考了多少", "分数是"]):
                scores["score"] -= 1.0
        # 待办与通知：只有明确说「待办 / 未读 / 消息 / 提醒」才走这条；
        # 「学校什么情况下会通知家长」是问制度，上面已经给 policy 加过分
        if any(w in text for w in ["待办", "未读", "消息", "提醒", "待处理", "新通知"]):
            scores["todo"] += 2.2
        # 「还有谁的异议没处理」：一出现「异议/申诉」就该走异议中心，不能被「谁」抓成名单
        if any(w in text for w in ["异议", "申诉", "复核"]):
            scores["appeal"] += 2.6
            scores["roster"] -= 1.5
        # 「计科2401 班有几个人在红色预警」：问的是人数分布，不是条款。
        # 「红色预警」进 POLICY_WORDS 之后这类问法会被抢走，这里把人数问法顶回来。
        # 「全校一共多少人」问的是总览，别被人数词拉到班级名单上。
        if (any(w in text for w in ["几个人", "多少人", "几人", "几个学生", "多少学生"])
                and not any(w in text for w in ["全校", "整体", "学校总共", "学校一共"])):
            scores["roster"] += 1.8
            scores["policy"] -= 1.0
        # 「帮我看看谁最危险」：带「谁 + 危险/风险」问的是名单，不是行动建议；
        # 否则会输给 ADVICE_WORDS 里的「帮我」，答成一堆通用建议。
        if any(w in text for w in ["谁最", "谁的风险", "谁的预警", "哪些人", "哪几个人"]) and any(
                w in text for w in ["危险", "风险", "预警", "挂科", "出问题"]):
            scores["roster"] += 2.8
            scores["advice"] -= 1.2
        # 但「申诉的流程/时限/要什么材料」问的是制度条款，不是某条异议的进度，
        # 这时候必须让 policy 反超，否则答出来是一串不存在异议的处理状态。
        if any(w in text for w in ["申诉", "复核", "异议"]) and any(
                w in text for w in ["流程", "时限", "期限", "几天", "多久", "材料", "条件",
                                    "怎么规定的", "规定", "办法", "能不能申诉", "可以申诉"]):
            scores["policy"] += 4.0
            scores["appeal"] -= 3.0
        # 家校消息：家长问「辅导员有没有发消息」，和系统通知是两回事
        if any(w in text for w in ["消息", "私信", "聊天记录", "回复我"]):
            scores["message"] += 2.6
        # 「计科2402 这周整体怎么样」是班情简报，不是全校概览
        if (any(c.lower() in text for c in self._classes)
                and any(w in text for w in ["整体", "简报", "情况", "怎么样", "如何", "报告"])
                and not any(w in text for w in ["成绩", "分数", "排名", "谁", "课表", "作业",
                                                "考勤", "旷课", "风险分"])):
            scores["class_report"] += 3.0
        # 培养方案：「毕业要修多少学分」不能落进校规检索
        if any(w in text for w in ["培养方案", "总学分", "要修多少学分", "选修课",
                                   "必修课", "课程档案"]):
            scores["plan"] += 2.4
        elif "毕业" in text and "学分" in text:
            scores["plan"] += 2.0
        best = max(scores, key=scores.get)
        # 没有任何学业关键词命中时返回 unknown，让各端走兜底说「答不准」，
        # 而不是默认 why 把「今天天气怎么样」也答成风险分
        return best if scores[best] > 0 else "unknown"

    # ---------- 生成 ----------
    def _risk_sentence(self, s: dict, r: dict) -> str:
        top = r["factors"][:3]
        parts = "、".join(f"{p['label']}（{p['points']:.0f} 分）" for p in top)
        return (f"{s['name']}当前风险分 **{r['score']}**，属于{r['level_label']}。"
                f"主要来自：{parts}。")

    def _factor_detail(self, s: dict, r: dict) -> list[str]:
        raw = r["raw"]
        out = []
        for p in r["factors"][:4]:
            k = p["key"]
            if k == "attendance":
                out.append(f"出勤：缺勤 {raw['absent']} 次 / 共 {raw['sessions']} 次课，缺勤率 {raw['absence_ratio']:.0%}")
            elif k == "homework":
                out.append(f"作业：应交 {raw['hw_assigned']} 次，实交 {raw['hw_submitted']} 次")
            elif k == "exam":
                gap = round(raw["cohort_avg"] - raw["mid_avg"], 1)
                # cohort_avg 是「全年级同学分课程的加权均分」，不是本班均分——
                # 标成「班级均分」会和 engine/scores.py 的班级均分（79.9）打架，
                # 同一个回答里出现两个班均，用户会当成算错。
                tail = f"，低于年级均分 {gap} 分" if gap > 0 else "，高于年级均分"
                out.append(f"期中：加权均分 {raw['mid_avg']}，年级均分 {raw['cohort_avg']}{tail}")
            elif k == "engagement":
                out.append(f"投入：平台每周登录 {s['engagement']['weekly_logins']} 次，视频完成率 {s['engagement']['video_rate']:.0%}，已 {s['engagement']['days_since_active']} 天未活跃")
            elif k == "history":
                out.append(f"历史：上学期 GPA {s['history']['gpa']}，累计挂科 {s['history']['failed_credits']} 学分")
            elif k == "credit":
                out.append(f"学分：已修 {s['credits']['earned']} / 培养方案 {s['credits']['plan_total']} 学分")
        return out

    def _compose_policy(self, hits: list[dict]) -> str:
        if not hits:
            return "知识库里没有检索到直接对应的条款。可以换个说法，比如“挂多少学分会被降级”。"
        lines = ["查到以下规定："]
        for i, h in enumerate(hits, 1):
            body = re.sub(r"\s*\n\s*", " ", h["text"]).strip()
            if len(body) > 160:
                body = body[:158] + "…"
            tag = f"（{h['school']}·{h.get('score_pct', '')}）" if h.get("school") else ""
            lines.append(f"[{i}] **{h['path']}**{tag}：{body}")
        lines.append("\n以上条款来自知识库原文，可在下方引用里核对。")
        return "\n".join(lines)

    def _compose_material(self, hits: list[dict]) -> str:
        """教师上传的真题/讲义：和校规条款分开措辞，学生一看就知道是课程资料。

        命中的常是「全文」「封面」这种只有一行标题的段——学生问「这份卷子考了什么」，
        只回一句「A 卷」等于没答。所以把同一份资料的其余章节按原顺序补在后面。
        """
        if not hits:
            return ""
        seen = {h.get("id") for h in hits}
        files = {h.get("file") for h in hits}
        extra = [c for c in self.kb.chunks
                 if c.get("file") in files and c.get("id") not in seen]
        extra.sort(key=lambda c: c.get("order", 0))
        rows = list(hits) + extra[:4]

        lines = ["课程资料里查到："]
        for i, h in enumerate(rows[:6], 1):
            body = re.sub(r"\s*\n\s*", " ", h.get("text") or "").strip()
            if len(body) > 200:
                body = body[:198] + "…"
            tag = f" · 相关度 {h['score_pct']}" if h.get("score_pct") else ""
            lines.append(f"[{i}] **{h['path']}**{tag}：{body}")
        lines.append("\n以上是老师上传的资料原文，可在下方引用里核对；要原文件可以到「学习资源」下载。")
        lines.append("（只依据上面的原文回答。原文里只有题目、没有答案时，就直说「资料里只有题目、"
                     "没写答案」，不要凭印象补一个答案；原文没提到就说不确定。）")
        return "\n".join(lines)

    def _compose_record(self, text: str, s: dict) -> tuple[str, str, str]:
        """从口语里抽出记录内容 → (title, note, status)。"""
        m = re.search(r"记录[:：]\s*(.+)", text)
        body = m.group(1).strip() if m else text.strip()
        body = re.sub(r"^(已经|刚|今天)?(谈过|谈完|完成|做了)", "", body).strip() or "完成谈话"
        title = body if len(body) <= 18 else body[:17] + "…"
        status = "已完成"
        if any(w in body for w in ["约了", "下次", "待", "计划"]):
            status = "进行中"
        return title, body, status

    # ---------- 明细类问答：考勤/作业/老师/课表，数据都在学生课表里 ----------
    def _compose_contact(self, sid: str, message: str, who: str = "") -> list[str]:
        """任课老师与联系方式。消息里提到具体课程就只给那位老师，否则列全部。"""
        s = self.engine.get(sid)
        named = [c for c in s["courses"] if c["name"] in message or c["code"] in message]
        picked = named or s["courses"]
        lines = []
        for c in picked:
            tp = c.get("teacher_profile") or {}
            line = f"**{c['name']}**（{c['credit']} 学分·{c['kind']}·{c['period']}）—— {c['teacher']}"
            if tp:
                line += (f"，{tp.get('title', '')}，{tp.get('dept', '')}"
                         f"\n  办公室：{tp.get('office', '—')}｜邮箱：{tp.get('email', '—')}"
                         f"｜电话：{tp.get('phone', '—')}｜答疑时间：{tp.get('office_hour', '—')}")
            lines.append(line)
        head = f"{who}{'的' if who else ''}任课老师" + (f"（{named[0]['name']}）：" if named else f"一共 {len(s['courses'])} 位：")
        return [head] + [f"- {x}" for x in lines] + ["有问题优先去答疑时间找老师；邮件里说明班级姓名和具体问题，回复会更快。"]

    def _compose_attendance(self, sid: str, who: str = "") -> list[str]:
        """考勤明细：落到「哪周星期几第几节」，不是一句「缺勤17次」。"""
        s = self.engine.get(sid)
        lines = []
        total_abs = total_late = 0
        for c in s["courses"]:
            if c["absent"] or c["late"]:
                total_abs += c["absent"]
                total_late += c["late"]
                bad = [a for a in c["attendance"] if a["status"] in ("absent", "late")]
                detail = "；".join(
                    f"第{a['week']}周{a['weekday']}{a['period']}（{'旷课' if a['status'] == 'absent' else a['note']}）"
                    for a in bad[:4])
                more = f" 等 {len(bad)} 次" if len(bad) > 4 else ""
                lines.append(f"- **{c['name']}**：旷课 {c['absent']} 次、迟到 {c['late']} 次（已上 {c['sessions_held']} 节）——{detail}{more}")
        if not lines:
            return [f"{who}的考勤是满勤，一门课都没缺过，这项没有扣分。"]
        head = f"{who}的考勤合计：旷课 {total_abs} 次、迟到 {total_late} 次。落到具体记录："
        return [head] + lines + ["明细可在「课堂考勤」页逐条核对；哪条记录有出入，点那一条的「异议」提交给辅导员。"]

    def _compose_homework(self, sid: str, who: str = "") -> list[str]:
        """作业明细：哪次没交、什么时候截止，按未交在前。"""
        s = self.engine.get(sid)
        lines = []
        for c in s["courses"]:
            bad = [h for h in c["homework"] if h["status"] in ("missing", "late")]
            for h in bad:
                if h["status"] == "missing":
                    state = f"未交（截止 {h['due']}，已过截止日）"
                else:
                    state = f"迟交（{h['submitted_at'][:10]} 交的，截止 {h['due']}）"
                lines.append(f"- **{c['name']}**「{h['title']}」：{state}")
        if not lines:
            return [f"{who}的作业全部按时提交，这项没有扣分。"]
        return [f"{who}目前的作业问题是："] + lines + [
            "作业提交率在风险分里占 20% 的权重，把未交的先补上最划算；明细可在「作业平台」核对。"]

    def _compose_courses(self, sid: str, who: str = "") -> list[str]:
        """课表与学分统计。"""
        s = self.engine.get(sid)
        cr = s["credits"]
        total = sum(c["credit"] for c in s["courses"])
        lines = [f"- {c['name']}（{c['credit']} 学分·{c['kind']}·{c['teacher']}·{c['period']}）"
                 for c in s["courses"]]
        return ([f"{who}本学期在修 {len(s['courses'])} 门课、共 {total} 学分："] + lines +
                [f"培养方案要求 {cr['plan_total']} 学分，已修 {cr['earned']}，本学期在读 {cr['in_progress']}。"])

    # ---------- 四类通用取数（五端共用，数据全部来自 tools 层）----------
    def _compose_timetable(self, res: dict, who: str = "") -> list[str]:
        """课表：日期 + 节次 + 教室。和「我的课表」页面同一份 calendar()。"""
        if not res.get("ok"):
            return [res.get("note") or "课表查不到。"]
        d = res.get("data") or {}
        rows = d.get("范围内的课") or []
        when = d.get("查询范围") or "本周"
        if not rows:
            return [f"{who}{when}没有排课。" + (d.get("说明") or "")]
        total = d.get("范围内课次") or len(rows)
        more = f"，只列前 {len(rows)} 节" if total > len(rows) else ""
        out = [f"{who}{when}共 {total} 节课（今天是 {d.get('今天', '')}{more}）："]
        for r in rows:
            tail = "" if r.get("状态") == "还没上" else "，已上过"
            out.append(f"- **{r['日期']} {r['节次']}** {r['课程']}"
                       f"（{r['教师']}，{r['教室']}{tail}）")
        if d.get("说明"):
            out.append(d["说明"])
        return out

    def _compose_forecast(self, res: dict, who: str = "") -> list[str]:
        """期末试算：当前总评 + 期末要考多少才不挂（或达到目标分）。"""
        if not res.get("ok"):
            return [res.get("note") or "成绩构成查不到。"]
        d = res.get("data") or {}
        rows = d.get("课程") or []
        if not rows:
            return ["没有查到这门课的成绩构成。"]
        target = d.get("目标总评")
        head = (f"{who}本学期各课的考核构成（及格线 60 分，期末卷面还要过 45 分）"
                + (f"，按目标总评 {target:g} 分算：" if target else "："))
        out = [head]
        for c in rows:
            need = c.get("目标所需期末") or c.get("及格所需期末") or ""
            out.append(f"- **{c['课程']}**：当前总评 {c['当前总评']} 分，期末占 {c['期末占比']}，{need}")
        if d.get("最需要补的一门"):
            out.append(f"最该先补的是 **{d['最需要补的一门']}**。")
        out.append(d.get("口径") or "")
        return [x for x in out if x]

    def _compose_todo(self, res: dict, who: str = "") -> list[str]:
        """本账号的未读通知与未完成待办。"""
        if not res.get("ok"):
            return [res.get("note") or "待办查不到。"]
        d = res.get("data") or {}
        out = [f"{who}当前有 **{d.get('未读通知', 0)}** 条未读通知、"
               f"**{d.get('未完成待办', 0)}** 条未完成待办。"]
        for n in d.get("通知") or []:
            out.append(f"- 通知：{n.get('标题')}——{n.get('内容')}")
        for t in d.get("待办") or []:
            out.append(f"- 待办：**{t.get('事项')}**——{t.get('说明')}")
        if d.get("说明"):
            out.append(d["说明"])
        return out

    def _compose_plan(self, res: dict, who: str = "") -> list[str]:
        """培养方案：学分要求与课程性质。"""
        if not res.get("ok"):
            return [res.get("note") or "培养方案查不到。"]
        d = res.get("data") or {}
        rows = d.get("本学期开设课程") or []
        out = [f"{who}本学期开设 {len(rows)} 门课、共 {d.get('课程总学分')} 学分："]
        out += [f"- {r['课程']}（{r['学分']} 学分·{r['性质']}·{r['教师']}·{r['上课节次']}·{r['周次']}）"
                for r in rows]
        if d.get("学分进度"):
            out.append(d["学分进度"] + "。")
        return out

    def _compose_appeals(self, res: dict, who: str = "") -> list[str]:
        """异议处理进度。"""
        if not res.get("ok"):
            return [res.get("note") or "异议查不到。"]
        d = res.get("data") or {}
        rows = d.get("明细") or []
        if not rows:
            return [d.get("说明") or "没有异议记录。"]
        total = d.get("异议", d.get("异议总数", len(rows)))
        pending = d.get("待处理")
        head = f"{who}共 {total} 条异议" + (f"，其中 {pending} 条还没处理" if pending is not None else "") + "："
        out = [head]
        for r in rows:
            tail = f"，答复：{r['答复']}" if r.get("答复") else ""
            out.append(f"- {r.get('学生', '')}{r.get('课程', '')}·{r.get('类型', '')}："
                       f"{r.get('理由', '')}（{r.get('状态', '')}{tail}）")
        if d.get("说明"):
            out.append(d["说明"])
        return out

    def _compose_messages(self, res: dict, who: str = "") -> list[str]:
        """家校消息往来。"""
        if not res.get("ok"):
            return [res.get("note") or "消息查不到。"]
        d = res.get("data") or {}
        rows = d.get("最近消息") or d.get("最近会话") or []
        if not rows:
            return [d.get("说明") or "还没有家校消息往来。"]
        peer = d.get("对方") or d.get("学生") or ""
        head = (f"{who}与{peer}共 {d.get('消息数', len(rows))} 条消息："
                if d.get("消息数") is not None else f"{who}最近的会话：")
        out = [head]
        for m in rows[:6]:
            if "内容" in m:
                out.append(f"- {m.get('方向')}：{m.get('内容')}（{m.get('时间')}）")
            else:
                out.append(f"- {m.get('学生')}：{m.get('最后一条')}（{m.get('时间')}）")
        if d.get("未读"):
            out.append(f"其中未读 {d['未读']} 条。")
        return out

    def _compose_class_report(self, res: dict, who: str = "") -> list[str]:
        """班级学情简报（原样给出，不做改写）。"""
        if not res.get("ok"):
            return [res.get("note") or "班级简报查不到。"]
        d = res.get("data") or {}
        body = (d.get("简报") or "").replace("### ", "").replace("**", "")
        return [body] if body else ["这份班级简报是空的。"]

    def _compose_scores(self, sid: str, who: str = "") -> list[str]:
        """单科成绩与班内位置。数字全部来自 engine.scores，和风险引擎同一套口径。"""
        from . import scores as scores_mod
        s = self.engine.get(sid)
        d = scores_mod.student_scores(self.engine, s)
        rows = sorted(d["各课成绩"], key=lambda x: -x["期中卷面"])
        lines = [f"- {r['课程']}：期中 {r['期中卷面']:.0f} 分（本课班均 {r['班级均分']}，"
                 f"班内第 {r['班内排名']}，{r['与班均相比']}）" for r in rows]
        out = [f"{who}本学期 {len(rows)} 门课的期中成绩，按分数从高到低："] + lines
        out.append(f"学分加权期中均分 **{d['学分加权期中均分']}**，"
                   f"班内第 {d['班内排名']}（班级均分 {d['班级均分']}）。")
        if d.get("分数最高的课"):
            b = d["分数最高的课"]
            out.append(f"分数最高的是 **{b['课程']}**（{b['期中卷面']:.0f} 分，{b['与班均相比']}）。")
        if d.get("相对最弱的课"):
            w = d["相对最弱的课"]
            out.append(f"相对班均最吃力的是 **{w['课程']}**（{w['期中卷面']:.0f} 分，{w['与班均相比']}）。")
        if d.get("上学期班级名次"):
            out.append(f"作为参照，上学期{d['上学期均分']} 分、GPA {d['上学期GPA']}，"
                       f"班级第 {d['上学期班级名次']}。")
        return out

    def _compose_class_scores(self, cls: str | None = None, course: str | None = None,
                              who_limit: list[str] | None = None) -> list[str]:
        """班级成绩排序。cls 为空时给各班横向对比。"""
        from . import scores as scores_mod
        engine = self.engine
        if not cls:
            classes = sorted({x["class_name"] for x in engine.students})
            if who_limit:
                classes = [c for c in classes if c in who_limit]
            rows = []
            for c in classes:
                one = scores_mod.class_scores(engine, c, course, top_n=1)
                top = (one.get("前几名") or [{}])[0]
                rows.append((c, one.get("班均"), top.get("姓名"), top.get("分数"), one.get("总人数")))
            rows.sort(key=lambda x: -(x[1] or 0))
            head = (f"按{('「' + course + '」期中卷面') if course else '学分加权期中均分'}"
                    f"排，各班情况：")
            out = []
            # 结论拆成几条独立事实，别写死成「成绩最好的是 X」当第一句——
            # 用户问「哪个班最差」时，模型照抄这句会先报一个最好的人，答非所问。
            # 只给一张表也不行，润色那一步会以为"还没查到具体人"，反问"请问是哪个班级"。
            if rows:
                best = max(rows, key=lambda x: (x[3] or 0))
                worst_cls = rows[-1]
                out.append(f"个人最高分：{best[2]}（{best[0]}）{best[3]} 分。")
                out.append(f"班均最高：{rows[0][0]}（{rows[0][1]} 分）；"
                           f"班均最低：{worst_cls[0]}（{worst_cls[1]} 分）。")
            return (out + [head] +
                    [f"- {c}（{n} 人）：班均 {avg} 分，第一 {name} {score} 分"
                     for c, avg, name, score, n in rows] +
                    ["回答方式：先直接回答用户问的那一项（谁成绩最好 / 哪个班最差 / 平均分多少），"
                     "再按班列；不要只反问「请问是哪个班级」而不给结论，也不要把「个人最高分」"
                     "当成每个问题的固定开头。"])

        d = scores_mod.class_scores(engine, cls, course)
        head = (f"{cls} 共 {d['总人数']} 人，按{d['筛选']['口径']}排："
                f"班均 {d['班均']} 分，最高 {d['最高']}，最低 {d['最低']}。")
        lines = [f"- 第 {x['名次']} 名 {x['姓名']}：{x['分数']} 分" for x in d["前几名"]]
        out = [head, "前几名：\n" + "\n".join(lines)]
        if d.get("末几名"):
            out.append("需要盯的几位：\n" + "\n".join(
                f"- 第 {x['名次']} 名 {x['姓名']}：{x['分数']} 分" for x in d["末几名"]))
        if d.get("说明"):
            out.append(d["说明"] + "。")
        return out

    def _compose_classroom(self, rep: dict, message: str) -> list[str]:
        """教师端的课堂统计口径：单位是「我教的这门课」，不是一个学生、也不是一个行政班。

        「我这门课平均分多少」如果落到班级排名，给出来的是各班学分加权均分（79.x），
        与本课程期中卷面均分（77.3）不是一个口径——老师一眼就知道不对。
        这里直接取 engine/classroom.py 的 report，与教师端页面完全同源，避免两处对不上。
        """
        courses = rep.get("courses") or []
        if not courses:
            return ["系统里没有查到你任教的课程。"]
        # 问题里点了课名就用那门；老师通常只教一门，默认第一门
        c = next((x for x in courses if x["name"] in message), courses[0])

        low = next((d["count"] for d in c["dist"] if d["label"].startswith("60 分以下")), 0)
        out = [
            f"**{c['name']}**（修课 {c['students']} 人，以下均为本课程范围）："
            f"期中卷面均分 {c['mid_avg']} 分，及格率 {c['pass_rate']}%（{low} 人不及格），"
            f"中位 {c['median']}，最高 {c['highest']}，最低 {c['lowest']}，标准差 {c['std']}。",
            "分数分布：" + "、".join(
                f"{d['label']} {d['count']} 人（{d['pct']}%）" for d in c["dist"]) + "。",
            f"出勤率 {c['attend']['rate']}%（缺课 {c['attend']['absent']} 人次、"
            f"迟到 {c['attend']['late']} 人次），作业提交率 {c['hw']['rate']}%。",
        ]
        if c.get("classes"):
            out.append("分班对比（与本课均分 %s 相比）：" % c["mid_avg"] + "、".join(
                f"{x['class_name']} {x['mid_avg']}（{x['gap']:+.1f}）" for x in c["classes"]) + "。")
        if c.get("grade_avg"):
            out.append(f"本课均分比年级加权均分 {c['grade_avg']} 分"
                       f"{'高' if c['gap_grade'] >= 0 else '低'} {abs(c['gap_grade'])} 分。")
        if len(courses) > 1:
            out.append("你任教的其他课程：" + "、".join(
                f"{x['name']}（均分 {x['mid_avg']}，及格率 {x['pass_rate']}%）"
                for x in courses if x["code"] != c["code"]) + "。")
        return out

    def answer(self, role: str, sid: str | None, message: str, school: str | None = None,
               emit=None, profile: dict | None = None,
               attachments: list[dict] | None = None,
               skill: str | None = None, sub: str | None = None) -> dict:
        """生成回答。

        emit: 可选回调 emit(kind, payload)，用于把中间过程推给流式接口。
              kind 取值 meta / thought / tool / delta；不传则行为与原来完全一致。
        profile: 登录身份，用来定位会话记忆；不给则不开多轮能力。
        attachments: 本轮附带的图片 / 语音 / 视频。识别结果作为「用户说了什么」
              拼在提问前面走同一条链路；材料里出现的分数与姓名不作学情数据，
              真实数字仍然只能来自工具查询。
        """
        t0 = time.time()
        trace: list[dict] = []
        citations: list[dict] = []
        risk_seen: dict = {}        # 本轮查到的那份风险评分，用来生成「数据依据」引用
        roster_seen: dict = {}      # 本轮查到的名单，名单类回答也用得上
        overview_seen: dict = {}    # 全校聚合
        teacher_seen: dict = {}     # 课堂数据
        blocks: list[str] = []
        thoughts: list[str] = []
        # 本轮对话里实际列过的名单（供下一轮"第 N 个"指代）
        listed: list[dict] | None = None
        # 用户亲手打的字：记忆里存这个，不存识别出来的长段材料描述
        raw_message = (message or "").strip()

        def think(text: str) -> None:
            thoughts.append(text)
            if emit:
                emit("thought", {"text": text})

        # ---- 点了 Skill：这一轮交给技能自己回答 ----
        # 预填的提问不是用户自己组织的话，让 _intent 去打分只会串端：
        # 学生口吻的「补救计划」在导员端一个关键词都命中不了，最后落进兜底话术。
        # 演练中的下一句也走这里——那是对家长说的话，不是新提问。
        from . import skillflow

        routed = skillflow.answer(self, role, sid, message, school, profile, emit,
                                  skill=skill, sub=sub)
        if routed:
            return routed

        # ---- 多模态：先把附件认出来，再当成"用户说的话"接进同一条链路 ----
        if attachments:
            from . import multimodal

            kinds = {str((a or {}).get("kind") or "") for a in attachments}
            label = "、".join(
                {"image": "图片", "audio": "语音", "video": "视频", "text": "文本"}.get(k, "附件")
                for k in sorted(kinds) if k
            ) or "附件"
            think(f"用户带了{label}，先看清内容再判断该查什么。")
            media_block, media_trace, media_problems = multimodal.as_text_block(attachments)
            for item in media_trace:
                trace.append(item)
                if emit:
                    emit("tool", item)
            if media_block:
                message = (media_block + "\n\n" + raw_message).strip()
                # 材料进会话记忆：下一轮追问「刚才那张图」时才有得翻
                if profile:
                    from . import media_memory as mm
                    mm.media_memory().remember(
                        memory_key(profile), attachments, media_block)
            if media_problems:
                self._last_media_problems = media_problems

        reread = ""
        # ---- 材料记忆：这轮没带附件，问的是「刚才那张图」 ----
        # 放在意图判定之前：追问「图里第三行是多少」本身不带业务关键词，
        # 让意图判断先看到材料原文，才可能落到「查成绩 / 查分数」这些分支上。
        if profile and not attachments and raw_message:
            recalled, mat_trace, reread = self._recall_material(memory_key(profile), raw_message)
            if recalled:
                think("这轮没带附件，但问的是之前发过的材料，先把那次的识别结果取回来。")
                message = (recalled + "\n\n" + message).strip()
                if mat_trace:
                    trace.append(mat_trace)
                    if emit:
                        emit("tool", mat_trace)

        intent = self._intent(message)

        if emit:
            emit("meta", {"intent": intent})

        # ---- 老师上传的真题/讲义优先 ----
        # 必须放在「交给模型自己判断」之前：一旦进了模型路由，它多半凭记忆讲一个
        # 「差不多的版本」，而课程资料的价值恰恰是「按老师发的那份原文答」。
        # 0.45 的阈值够挡住寒暄（「你好」只有 0.22），不会把闲聊也塞满引用。
        if intent in ("unknown", "material") and not citations:
            mat_hits = self.t_policy(message, min_score=0.35 if intent == "material" else 0.45,
                                     kind="resource", top_k=8, limit=5)
            if mat_hits:
                citations = mat_hits
                blocks.append(self._compose_material(mat_hits))
                intent = "material"
                think(f"老师上传的资料里有相关内容（{mat_hits[0].get('score_pct', '')}），按原文答。")

        # ---- 学生本人档案：每轮都实时翻一遍，再决定怎么答 ----
        # 放在校规检索与模型路由之前：先知道「他是谁、现在什么处境」，
        # 制度条款才能落到人身上，回答里那句「对照你的情况」也才有来路。
        # 档案是会变的（打卡、交作业、成绩录入），所以每轮重查，不吃上一轮的旧数。
        facts: dict | None = None

        def fetch_facts(who_sid: str) -> str:
            """实时查一次学生本人档案：写进轨迹，并返回给模型看的事实段落。"""
            nonlocal facts
            try:
                f = self.student_facts(who_sid, role, raw_message or message, intent)
            except Exception:  # noqa: BLE001 - 查不到档案不能挡住回答
                return ""
            facts = f
            think(f"先把{f['scope']}的账翻一遍：{f['brief']}。")
            item = {
                "tool": "retrieve_student",
                "label": f"检索{f['scope']}档案",
                "args": {"sid": f["sid"], "fields": len(f["fields"])},
                "ms": f["ms"],
                "evidence": {"source": "students / checkins / homework 表",
                             "table": f"{f['scope']}档案（实时查询）",
                             "rows": len(f["items"]), "unit": "项",
                             "ts": f["as_of"], "ms": f["ms"],
                             "detail": "每轮回答前重新查一次，不用上一轮的旧数"},
                "profile": f,
            }
            trace.append(item)
            if emit:
                emit("tool", item)
            return (f"{f['scope']}档案（本轮实时检索结果，以此为准，不要再问用户要这些信息）：\n"
                    + "\n".join(f"- {it['label']}：{it['value']}" for it in f["items"]))

        facts_ctx = ""
        # 学生/家长端：问什么都是先看本人，所以每轮无条件查，不做关键词过滤
        if sid and role in ("student", "parent"):
            facts_ctx = fetch_facts(sid)

        # ---- 规则引擎认不出的问题，交给模型自己判断该查什么 ----
        # 这是「问几个不同问题却回同一句话」的根因修复：原来所有 unknown
        # 都落到下面同一个 else 分支，输出的是硬编码的那段能力清单。
        # 模型路由失败时 route() 返回 None，继续走原来的确定性链路，
        # 所以断网、额度用完、key 没配这几种情况下行为和改造前完全一致。
        if intent == "unknown" and llm.available():
            from . import router as router_mod
            routed = router_mod.route(self, role, sid, message, school, profile, emit)
            if routed:
                # 本人档案这条轨迹要跟着走：路由结果自带一份 trace，
                # 直接返回会把它冲掉，界面上就只剩「模型选工具」了。
                if trace:
                    routed["trace"] = trace + list(routed.get("trace") or [])
                    routed["thoughts"] = thoughts + list(routed.get("thoughts") or [])
                return routed

        # ---- 多轮：取上一轮记忆，消解这轮在说谁 ----
        last: dict | None = None
        mkey = memory_key(profile) if (profile and self.memory) else None
        if mkey:
            hist = self.memory.history(mkey)
            if hist:
                last = hist[-1]

        target_sid = sid
        # 人名消解只看用户亲手打的字：上传的成绩单、名单截图上印着的名字
        # 是材料内容，不是「要查谁」，拿它去匹配会查错人。
        name_src = raw_message or ""
        if role in ("counselor", "admin"):
            target_sid, thought = self.resolve_target(name_src, role, sid, last)
            if thought:
                think(thought)
        elif role in ("student", "parent") and target_sid:
            # 学生/家长只能看本人，但系统之前是「静默换成自己」——问别人的名字，
            # 拿回来的是自己的数据，用户以为查到的是对方。这里必须先说清楚。
            me = self.engine.get(target_sid)["name"]
            others = [n for n in self._names if n in name_src and n != me]
            if others:
                think(f"问的是 {others[0]}，但当前账号只能看 {me} 本人，按权限只答本人。")
                who = "孩子" if role == "parent" else "本人"
                blocks.append(
                    f"（说明：你问的是 **{others[0]}**，这个账号只能查看{who}的数据，"
                    f"下面给的是 **{me}** 的情况。要看 {others[0]}，得用辅导员或教务账号。）")
        elif role == "teacher" and (profile or {}).get("name"):
            # 教师也一样：问到自己任教范围外的班级/专业，不能静默换成自己那门课来答，
            # 否则用户会以为这就是他要的那个班。
            mine = {s["class_name"] for s in self.engine.students
                    if any(c.get("teacher") == profile["name"] for c in s.get("courses") or [])}
            asked = [c for c in self._classes if c in name_src]
            outside = [c for c in asked if c not in mine]
            if outside:
                think(f"问的 {outside[0]} 不在 {profile['name']} 任教的班里，先说清范围。")
                blocks.append(
                    f"（说明：**{outside[0]}** 不在你任教的班里——你带的是 "
                    f"{'、'.join(sorted(mine))}，跨班数据要辅导员或教务账号才看得到。"
                    f"下面是你自己课上的情况。）")
            elif "软件工程" in name_src or "大三" in name_src:
                # 「大三软件工程班」这类说法对不上库里的班级名，别硬套到自己课上
                think("问的班级在教务系统里找不到对应，说明范围后按自己的课回答。")
                blocks.append(
                    "（说明：库里没有叫「大三软件工程班」的班级——现有班级是 "
                    f"{'、'.join(self._classes)}。下面是你能看到的范围：你自己任教的课。）")


        # 辅导员/教务/教师问到具体某个学生：同样先翻他的档案
        # （名单、全校统计这类问的是一群人，不查；查了也只是噪音）
        if (not facts_ctx and target_sid and role in ("counselor", "admin", "teacher")
                and intent in ("policy", "why", "advice", "unknown", "score", "trend",
                               "attendance", "homework")):
            facts_ctx = fetch_facts(target_sid)

        def call(name, fn, **kwargs):
            start = time.time()
            result = fn(**kwargs)
            ms = round((time.time() - start) * 1000, 1)
            item = {
                "tool": name,
                "args": {k: v for k, v in kwargs.items() if v is not None},
                "ms": ms,
                # 证据链：这张表 / 命中几条 / 查询时刻，随 trace 一起下发
                "evidence": build_evidence(name, result, ms),
            }
            trace.append(item)
            if name == "risk_score":
                risk_seen["r"] = result      # 留给「数据依据」引用分组
            elif name == "roster":
                roster_seen["rows"] = result
            elif name == "campus_overview":
                overview_seen["o"] = result
            elif name == "teacher_view":
                teacher_seen["tv"] = result
            if emit:
                emit("tool", item)
            return result

        def call_rag(query: str, school: str | None = None, kind: str | None = None,
                     min_score: float = 0.3, top_k: int = 4,
                     limit: int = 3) -> list[dict]:
            """检索校规库（混合检索），并把「怎么召回的」一起写进轨迹。

            只记「查了校规库」说服力不够：评委问「这条规定哪来的」，
            轨迹里得能看到改写后的查询、两路通道多少候选、每条的相关度
            与命中原因，才叫可核查的检索。

            kind="resource" 时只保留教师上传的真题/讲义——课程内容问题
            要的是老师发的那份材料，不能被校规条款挤掉。
            """
            start = time.time()
            hist_ctx = ""
            if mkey and self.memory:
                prev = self.memory.history(mkey)
                if prev and prev[-1].get("message"):
                    hist_ctx = str(prev[-1]["message"])[:80]
            hits = self.t_policy(query=query, school=school, context=hist_ctx,
                                 min_score=min_score, kind=kind, top_k=top_k, limit=limit)
            ms = round((time.time() - start) * 1000, 1)
            meta = self.kb.meta()
            item = {
                "tool": "retrieve_policy",
                "args": {"query": query, "top_k": 3},
                "ms": ms,
                "evidence": build_evidence("retrieve_policy", hits, ms),
                "retrieval": {
                    "query": query,
                    "rewritten": meta.get("rewritten") or "",
                    "added_terms": meta.get("added_terms") or [],
                    "channel": meta.get("channel") or "",
                    "candidates": meta.get("candidates") or 0,
                    "ms": meta.get("ms"),
                    "hits": [
                        {
                            "rank": i,
                            "path": h.get("path") or "",
                            "school": h.get("school") or "",
                            "score": h.get("score_pct") or "",
                            "why": h.get("why") or "",
                        }
                        for i, h in enumerate(hits, 1)
                    ],
                },
            }
            trace.append(item)
            if emit:
                emit("tool", item)
            return hits

        # ---- 改数据类请求：分数与预警等级是算出来的，没有手工写入口 ----
        # 这类请求以前会落到「查风险分」的确定性分支上，答出一堆明细，
        # 用户以为我们同意改了。必须是明确拒绝 + 给出正当的替代路径。
        if (any(w in raw_message for w in ["风险分", "预警等级", "预警级别", "评分"])
                and re.search(r"(?:改|设|调|写|变成)(?:成|为)?\s*\d+", raw_message)):
            think("用户要求手工改风险分——这是改数据，直接说明做不到，并给正当路径。")
            reply = (
                "风险分不能手工改。它是六个因素按权重算出来的结果，"
                "改一个数字等于改结论；系统和我的接口里都没有写入口，我也不会为了好看去动它。\n\n"
                "如果确实是这套分数不合理，能做的两件事：\n"
                "1. **改口径**：在「系统设置」里调整六项权重与红黄绿阈值，改完对全校重新计算；\n"
                "2. **改原始记录**：病假、缓考这类情况走考勤 / 成绩异议更正，由教务改记录，"
                "风险分随后自动重算。"
            )
            if mkey and self.memory:
                self.memory.append(mkey, {
                    "message": raw_message[:200], "reply": reply[:400],
                    "sid": target_sid, "intent": "refuse", "roster": None,
                })
            return {
                "reply": reply,
                "intent": "refuse",
                "citations": [],
                "trace": trace,
                "thoughts": thoughts,
                "action": None,
                "elapsed_ms": round((time.time() - t0) * 1000, 1),
                "suggestions": self._suggestions(role, "why", target_sid),
            }

        # ---- 与角色无关的四类问题：课表 / 期末试算 / 待办 / 培养方案 ----
        # 这四件事页面上都有数据，但改造前既没有工具也没有意图，五端问到都只能答
        # 「系统里没有」——学生的「明天有没有课」就是这么答错的。
        # 放在角色分支之前统一处理：五端问法一样，没必要各写一遍。
        generic_done = False
        if intent in ("timetable", "forecast", "todo", "plan",
                      "appeal", "message", "class_report"):
            from . import tools as tools_mod

            tool_name = {"timetable": "get_timetable", "forecast": "get_final_forecast",
                         "todo": "get_todos", "plan": "get_curriculum",
                         "appeal": "get_appeals", "message": "get_messages",
                         "class_report": "get_class_report"}[intent]
            # 家校消息只有家长/辅导员/教务有通道，其他角色退回通知与待办
            if intent == "message" and role not in ("parent", "counselor", "admin"):
                intent = "todo"
                tool_name = "get_todos"
            t_args: dict = {}
            # 把整句丢给工具，让它自己解析「明天 / 周三 / 第 8 周 / 下一节课」
            if intent == "timetable":
                t_args["when"] = message
            if intent in ("timetable", "forecast", "plan") and target_sid:
                t_args["name"] = self.engine.get(target_sid)["name"]

            if intent in ("appeal", "message") and target_sid:
                t_args["name"] = self.engine.get(target_sid)["name"]
            if intent == "class_report":
                cls = self._match_class(message)
                if cls:
                    t_args["class_name"] = cls
            if intent == "forecast":
                m = re.search(r"(?:拿|考|要到|目标)\s*(\d{2,3})\s*分", message)
                if m:
                    t_args["target"] = float(m.group(1))
                for cname in self._course_names:
                    if cname in message:
                        t_args["course"] = cname
                        break
            t_name = (profile or {}).get("name") or ""
            res = call(tool_name, lambda **_: tools_mod.run(
                self, role, sid, tool_name, t_args, t_name, profile))
            if role == "student":
                who = "你"
            elif role == "parent":
                who = "孩子"
            elif target_sid:
                who = self.engine.get(target_sid)["name"] + " "
            else:
                who = ""
            if intent == "timetable":
                think("问的是课表，按日期 + 节次 + 教室取，和「我的课表」页面同一份数据。")
                blocks.extend(self._compose_timetable(res, who))
            elif intent == "forecast":
                think("问的是期末要考多少，按考核权重正算，不是拿期中分硬估。")
                blocks.extend(self._compose_forecast(res, who))
            elif intent == "todo":
                think("问的是通知与待办，按当前账号取。")
                blocks.extend(self._compose_todo(res, who))
            elif intent == "appeal":
                think("问的是异议处理进度，去异议中心查。")
                blocks.extend(self._compose_appeals(res, who))
            elif intent == "message":
                think("问的是家校消息，按会话查。")
                blocks.extend(self._compose_messages(res, who))
            elif intent == "class_report":
                think("问的是班级整体情况，按班级现场聚合一份简报。")
                blocks.extend(self._compose_class_report(res, who))
            else:
                think("问的是培养方案与学分要求。")
                blocks.extend(self._compose_plan(res, who))
            generic_done = True

        if generic_done:
            pass
        elif role == "student" and sid:
            s = self.engine.get(sid)
            r = call("risk_score", self.t_risk, sid=sid)
            if intent == "export":
                kind = self._export_kind(message)
                if kind in ("daily", "semester", "interventions"):
                    blocks.append("这类全校文书由辅导员或教务端导出。学生端可以导：**我的告知函**、**学业预警通知书**，说一声就行。")
                else:
                    think(f"要导文件，给 {s['name']} 排一份 Word，数据即取即排。")
                    res = call("export_file", self.t_export, kind=kind, sid=sid)
                    blocks.append(self._compose_export(res, s["name"]))
            if intent in {"why", "advice", "letter"}:
                blocks.append(self._risk_sentence(s, r))
                if intent == "why":
                    blocks.append("拆开看是这样：\n" + "\n".join(f"- {x}" for x in self._factor_detail(s, r)))
                    if r["overrides"]:
                        blocks.append("另外触发了硬性规则：" + "；".join(r["overrides"]))
            if intent == "trend":
                think(f"问的是走势，拉 {s['name']} 五个学期的成绩序列和各科测评。")
                t = call("grade_trend", self.t_trend, sid=sid)
                blocks.append(self._compose_trend(t))
                blocks.append(self._risk_sentence(s, r))
            if intent == "advice":
                acts = call("interventions", self.t_actions, sid=sid)
                blocks.append("接下来按这个顺序做：\n" + "\n".join(
                    f"{i+1}. **{a['title']}** —— {a['detail']}（{a['deadline']}）"
                    for i, a in enumerate(acts[:3])))
            if intent == "policy":
                think("这问的是制度条款，去校规知识库里检索。")
                hits = call_rag(message, school=school)
                citations = hits
                blocks.append(self._compose_policy(hits))
                blocks.append(f"对照你的情况：风险分 {r['score']}，累计挂科学分 {s['history']['failed_credits']}。")
            if intent == "contact":
                think("问的是任课老师，从课表里带出老师的档案与联系方式。")
                blocks.extend(call("contact_detail", self._compose_contact, sid=sid, message=message, who=""))
            if intent == "attendance":
                think("问的是考勤明细，落到每一次异常记录。")
                blocks.extend(call("attendance_detail", self._compose_attendance, sid=sid))
            if intent == "homework":
                think("问的是作业明细，把未交和迟交的挑出来。")
                blocks.extend(call("homework_detail", self._compose_homework, sid=sid))
            if intent == "course":
                think("问的是课表或学分，直接给在修课程清单。")
                blocks.extend(call("course_list", self._compose_courses, sid=sid))
            if intent == "score":
                think("问的是分数，按每门课的期中卷面 + 本课班均 + 班内排名给。")
                if any(w in message for w in ["我们班", "班里", "同学", "全班", "谁成绩"]):
                    blocks.append("（说明：学生账号只能看本人成绩，班里其他同学的名次不提供，"
                                  "只能告诉你在本班排第几。）")
                blocks.extend(call("score_detail", self._compose_scores, sid=sid))
            if intent == "material":
                think("问的是课程资料，去老师上传的真题/讲义里检索。")
            if not blocks:
                # 没听懂的问题：先试知识库；检索不到就直说不会，绝不拿风险分充数
                think("没匹配到已知问法，先去校规知识库试一次。")
                hits = call_rag(message, school=school)
                if hits:
                    citations = hits
                    blocks.append(self._compose_policy(hits))
                    blocks.append(f"对照你的情况：风险分 {r['score']}，累计挂科学分 {s['history']['failed_credits']}。")
                else:
                    blocks.append("这个问题我暂时答不准，系统里查不到这类信息，也不想瞎猜误事。我擅长这些：")
                    blocks.append("- 考勤与作业明细：「我哪次作业没交」「我缺了几次课」")
                    blocks.append("- 任课老师联系：「数据结构老师的邮箱」「我的老师都有谁」")
                    blocks.append("- 风险与走势：「我的风险分为什么这么高」「我的成绩走势怎么样」")
                    blocks.append("- 校规条款：「挂多少学分会被降级」「学校什么情况下会通知家长」")
        elif role == "parent" and sid:
            s = self.engine.get(sid)
            r = call("risk_score", self.t_risk, sid=sid)
            if intent == "export":
                kind = self._export_kind(message)
                if kind in ("parent", "student_letter", "notice"):
                    think(f"家长要导文书，给 {s['name']} 排一份 Word。")
                    res = call("export_file", self.t_export,
                               kind="parent" if kind == "parent" else kind, sid=sid)
                    blocks.append(self._compose_export(res, s["name"]))
                else:
                    blocks.append("家长端可以导出孩子的家长信、告知函与通知书（Word）；其他文书请联系辅导员。")
            if intent == "trend":
                blocks.append(self._compose_trend(call("grade_trend", self.t_trend, sid=sid)))
                blocks.append(f"对照 {s['name']} 当前的风险分 {r['score']}（{r['level_label']}）。")
            if intent in ("contact", "attendance", "homework", "course"):
                # 家长问孩子的课表、老师、作业、考勤：给明细，口吻用「孩子」
                think(f"家长在问孩子的{ {'contact': '老师与联系方式', 'attendance': '考勤明细', 'homework': '作业明细', 'course': '课表学分'}[intent] }。")
                if intent == "contact":
                    blocks.extend(call("contact_detail", self._compose_contact, sid=sid, message=message, who="孩子"))
                elif intent == "attendance":
                    blocks.extend(call("attendance_detail", self._compose_attendance, sid=sid, who="孩子"))
                elif intent == "homework":
                    blocks.extend(call("homework_detail", self._compose_homework, sid=sid, who="孩子"))
                else:
                    blocks.extend(call("course_list", self._compose_courses, sid=sid, who="孩子"))
            if intent == "score":
                think("家长问孩子的分数，给每门课的期中分和班内位置。")
                blocks.extend(call("score_detail", self._compose_scores, sid=sid, who="孩子"))
            if intent in ("trend", "score"):
                # 成绩走势/成绩单已经答完了，不再叠一段政策，家长一次只吸收一件事
                pass
            elif intent == "advice":
                think("家长在问能做什么，给在家能落地的配合方式。")
                blocks.append(f"{s['name']} 目前的状态：{r['level_label']}，风险分 {r['score']}，主导因素是{r['factors'][0]['label']}。")
                blocks.append("在家能帮上忙的三件事：")
                blocks.append("1. 固定作息——缺勤和迟交大多从作息乱掉开始，先保证上课日的起床时间。")
                blocks.append("2. 每周看一次作业平台——不用盯着做，只确认「这周的都交了」。")
                blocks.append("3. 和任课老师建立联系——用答疑时间当面问一次，比微信上问十次有效。")
                blocks.append(f"学校的告知函会写明 {s['name']} 的具体问题与补救路径，需要的话我可以导一份家长信给您。")
            elif intent == "policy" or any(w in message for w in ["通知", "规定", "政策", "什么时候", "多少", "几门", "降级", "毕业", "退学"]):
                think("家长在问学校政策，检索制度库里关于家长通知的条款。")
                hits = call_rag(message + " 家长 学业预警", school=school)
                citations = hits
                blocks.append(self._compose_policy(hits))
                blocks.append(
                    f"对照 {s['name']} 的情况：风险分 {r['score']}（{r['level_label']}），"
                    f"累计挂科 {s['history']['failed_credits']} 学分，目前处于关注与帮扶阶段，尚未触发处分线。")
            elif intent == "unknown":
                blocks.append("这个问题我答不准，也不想瞎猜——系统里查不到这类信息。我擅长帮您看这些：")
                blocks.append("- 孩子的出勤与作业：「孩子哪次作业没交」「孩子缺了几次课」")
                blocks.append("- 任课老师联系：「数据结构老师怎么联系」")
                blocks.append("- 孩子的成绩走势与风险：「孩子成绩怎么样」「孩子的风险分」")
                blocks.append("- 学校关于家校通知的规定：「学校什么情况下会通知家长」")
            else:
                hits = call_rag("家长 通知 学业预警", school=school)
                citations = hits[:1]
                blocks.append(f"{s['name']}（{s['class_name']}）本学期状态：{r['level_label']}，风险分 {r['score']}。")
                blocks.append("具体情况：\n" + "\n".join(f"- {x}" for x in self._factor_detail(s, r)[:3]))
                if hits:
                    blocks.append(f"关于家校沟通：{hits[0]['text'].strip().split(chr(10))[0]}")
        elif role == "teacher":
            teacher_name = (profile or {}).get("advisor") or (profile or {}).get("name") or ""
            tv = call("teacher_view", self.t_teacher_view, teacher_name=teacher_name)
            my_students = tv["students"]
            # 在「我教的学生」范围内解析指代：姓名越界要拦住，序数走上一轮名单
            named = self._match_name(message)
            t_sid = None
            if named:
                if any(st["id"] == named["id"] for st in my_students):
                    t_sid = named["id"]
                    think(f"「{named['name']}」是你课上的学生，按他来查。")
                else:
                    blocks.append(f"「{named['name']}」不在你本学期任课的学生名单里，我只能看你教的学生。")
                    think(f"姓名命中但不在该老师课上，已拦住避免越权。")
            if not t_sid:
                n = self._match_ordinal(message)
                if n and last and last.get("roster") and 1 <= n <= len(last["roster"]):
                    row = last["roster"][n - 1]
                    if any(st["id"] == row["id"] for st in my_students):
                        t_sid = row["id"]
                        think(f"「第{n}个」指上一轮名单里的 {row['name']}。")
            target_sid = t_sid
            listed = my_students[:8]

            def _my_row(sid):
                return next((st for st in my_students if st["id"] == sid), None)

            # 「我教的学生里谁分最高」问的是分数，别被「我教」「学生」带进风险名单
            if (intent == "roster" and
                    any(w in message for w in ["成绩", "分数", "分最高", "最高分", "考得"]) and
                    "风险" not in message):
                intent = "score"
            mine_scope = any(w in message for w in
                             ["我这门课", "我的课", "我教", "这门课", "我的课堂", "我班的课"])
            who_ask = any(w in message for w in ["谁", "哪个学生", "第一", "排名", "名单"])

            if intent == "course" or any(w in message for w in ["教的课", "教什么课", "几门课", "我教什么"]):
                think("问的是自己教的课，给课程清单。")
                cs = tv["courses"]
                blocks.append(f"你本学期教 {len(cs)} 门课：")
                blocks.append("\n".join(f"- **{c['name']}**（{c.get('credit','')} 学分·{c.get('kind','')}·{c.get('period','')}）" for c in cs))
                blocks.append(f"修这些课的学生共 {len(my_students)} 人，要看名单就说「我课上的学生」。")
            elif any(w in message for w in ["班均", "平均", "成绩"]) and not t_sid and intent != "score":
                think("问的是班级成绩，给各课期中班均。")
                for c in tv["courses"]:
                    scs = [st["courses"][0]["midterm"] for st in my_students
                           if st["courses"] and st["courses"][0]["code"] == c["code"]
                           and st["courses"][0].get("midterm") is not None]
                    if scs:
                        blocks.append(f"- **{c['name']}** 期中班均 {round(sum(scs) / len(scs), 1)}，最高 {max(scs)}，最低 {min(scs)}。")
                blocks.append("想看某位学生的明细，说名字或「第 N 个」。")
            elif intent == "score":
                from . import classroom as classroom_mod
                # 「我这门课平均分多少 / 及格率怎么样」是教师端特有的课堂口径：
                # 均分 77.3、及格率 96.2% 只在本课程范围内成立。若落到行政班排名，
                # 给出来的是各班班均 79.x，同一个问题两个答案，老师一眼就知道算错了。
                if mine_scope and not who_ask:
                    think("问的是我教的这门课的课堂统计，取本课程口径（均分/及格率/分布/分班）。")
                    rep = call("classroom_stats", lambda **_: classroom_mod.report(
                        self.engine, teacher_name, profile))
                    blocks.extend(self._compose_classroom(rep, message))
                else:
                    # 老师问「谁成绩最好」：按期中卷面排，不再拿风险分名单搪塞
                    think("问的是分数，按你任教的班级给出期中排名。")
                    mine_classes = sorted({st["class_name"] for st in my_students})
                    want_course = next((c["name"] for c in tv["courses"] if c["name"] in message), None)
                    cls = self._match_class(message)
                    if cls and cls not in mine_classes:
                        blocks.append(f"{cls} 不在你任教的班里——你带的是 {'、'.join(mine_classes)}，"
                                      f"跨班成绩要辅导员或教务账号才看得到。下面是你能看到的范围：")
                        cls = None
                    blocks.extend(call("class_score_detail", self._compose_class_scores,
                                       cls=cls, course=want_course, who_limit=mine_classes))
            elif intent in ("roster", "overview") or any(w in message for w in ["课上", "我教", "我的学生", "谁"]):
                think("问的是自己课上的学生，按风险分给名单。")
                if not my_students:
                    blocks.append("你本学期没有任课记录（教师档案未关联到课程）。")
                else:
                    rows = my_students[:8]
                    blocks.append(f"修你课的学生共 {len(my_students)} 人，按风险分排序：")
                    blocks.append("\n".join(
                        f"- {x['name']}（{x['class_name']}）风险分 {x['score']}（{x['level_label']}），主因 {x['top_factor']}"
                        for x in rows))
                    if len(my_students) > 8:
                        blocks.append(f"… 共 {len(my_students)} 人，想看某位说名字或「第 N 个」。")
                    if any(w in message for w in ["班均", "平均", "成绩"]):
                        for c in tv["courses"]:
                            scs = [st["courses"][0]["midterm"] for st in my_students
                                   if st["courses"] and st["courses"][0]["code"] == c["code"]
                                   and st["courses"][0].get("midterm") is not None]
                            if scs:
                                blocks.append(f"- **{c['name']}** 期中班均 {round(sum(scs) / len(scs), 1)}，最高 {max(scs)}，最低 {min(scs)}。")
                        blocks.append("想看某位学生的明细，说名字或「第 N 个」。")
            elif intent == "attendance" and t_sid:
                row = _my_row(t_sid)
                think(f"问的是 {row['name']} 在你课上的考勤明细。")
                for c in row["courses"]:
                    bad = [a for a in c.get("attendance", []) if a["status"] in ("absent", "late")]
                    if c["absent"] or c.get("late"):
                        detail = "；".join(
                            f"第{a['week']}周{a['weekday']}{a['period']}（{'旷课' if a['status'] == 'absent' else a.get('note', '迟到')}）"
                            for a in bad[:4])
                        more = f" 等 {len(bad)} 次" if len(bad) > 4 else ""
                        blocks.append(f"- **{c['name']}**：旷课 {c['absent']} 次、迟到 {c.get('late', 0)} 次（已上 {c.get('sessions_held', 0)} 节）——{detail}{more}")
                blocks.append("考勤异常想反馈给辅导员，可以直接说「建议联系辅导员」。")
            elif intent == "homework" and t_sid:
                row = _my_row(t_sid)
                think(f"问的是 {row['name']} 在你课上的作业明细。")
                found = False
                for c in row["courses"]:
                    bad = [h for h in c.get("homework", []) if h["status"] in ("missing", "late")]
                    for h in bad:
                        found = True
                        state = (f"未交（截止 {h['due']}）" if h["status"] == "missing"
                                 else f"迟交（{h.get('submitted_at', '')[:10]} 交，截止 {h['due']}）")
                        blocks.append(f"- **{c['name']}**「{h['title']}」：{state}")
                if not found:
                    blocks.append(f"{row['name']} 在你课上的作业全部按时提交，这项没问题。")
            elif intent == "why" and t_sid:
                row = _my_row(t_sid)
                think(f"问的是 {row['name']} 的风险分，从他在这门课的表现拆。")
                blocks.append(f"**{row['name']}**（{row['class_name']}）当前风险分 {row['score']}（{row['level_label']}）。")
                blocks.append("他在你课上的表现：")
                for c in row["courses"]:
                    co = c.get("cohort_avg")
                    gap = f"，低于班均 {round(co - c['midterm'], 1)} 分" if (co and c.get("midterm") is not None and c["midterm"] < co) else ""
                    blocks.append(f"- **{c['name']}**：期中 {c.get('midterm', '—')}，缺勤 {c.get('absent', 0)} 次，作业 {c.get('hw_submitted', 0)}/{c.get('hw_assigned', 0)}{gap}。")
                if row["score"] >= 55:
                    blocks.append("风险偏高，主因可能在出勤或作业。建议联系辅导员一起盯，或下节课后单独谈一次。")
            elif intent == "advice":
                think("问的是教学层面的建议，从风险最高的学生给重点名单。")
                red = [x for x in my_students if x["level"] == "red"]
                yel = [x for x in my_students if x["level"] == "yellow"]
                blocks.append(f"你课上的学生里，红色预警 {len(red)} 人、黄色关注 {len(yel)} 人。")
                if red:
                    blocks.append("建议重点关注的（红色）：")
                    blocks.append("\n".join(f"- {x['name']}（{x['class_name']}）风险分 {x['score']}，主因 {x['top_factor']}" for x in red[:5]))
                blocks.append("教学层面可做：①缺勤集中的章节下次上课前提一句考勤；②作业未交的在下节课前补交截止；③红色学生建议联系辅导员联动。")
            elif intent == "policy":
                think("问的是校规条款，去知识库检索。")
                hits = call_rag(message, school=school)
                citations = hits
                blocks.append(self._compose_policy(hits))
            elif intent == "contact":
                any_sid = my_students[0]["id"] if my_students else self.engine.students[0]["id"]
                think("问的是任课老师联系方式，从课表带出档案。")
                blocks.extend(self._compose_contact(any_sid, message, who=""))
            elif t_sid:
                row = _my_row(t_sid)
                think(f"没有更具体指令，给 {row['name']} 在你课上的概览。")
                blocks.append(f"**{row['name']}**（{row['class_name']}）风险分 {row['score']}（{row['level_label']}）。")
                for c in row["courses"]:
                    blocks.append(f"- **{c['name']}**：期中 {c.get('midterm', '—')}，缺勤 {c.get('absent', 0)} 次，作业 {c.get('hw_submitted', 0)}/{c.get('hw_assigned', 0)}。")
            elif intent == "unknown":
                blocks.append("这个问题我答不准，系统里查不到这类信息。我擅长帮你看：")
                blocks.append("- 你教的课与学生：「我教的课」「我课上的学生」「班均多少」")
                blocks.append("- 某学生的考勤与作业：「张三缺了几次课」「李四哪次作业没交」")
                blocks.append("- 风险研判：「谁的风险最高」「王五为什么风险分高」")
                blocks.append("- 教学建议：「我该重点关注谁」")
            else:
                if my_students:
                    red = sum(1 for x in my_students if x["level"] == "red")
                    blocks.append(f"你本学期教 {len(tv['courses'])} 门课、{len(my_students)} 名学生，其中红色预警 {red} 人。")
                    blocks.append("可以问我：「我课上的学生」「谁的风险最高」「某学生的考勤/作业」，或「我该重点关注谁」。")
                else:
                    blocks.append("你本学期没有任课记录，暂无学生数据可看。")
        else:
            # ---- 辅导员 / 教务：支持指名道姓、序数、代词、班级 ----
            if intent == "export":
                send = any(w in message for w in ["发邮件", "发给家长", "发送", "邮件"])
                kind = self._export_kind(message)
                if send and target_sid:
                    s = self.engine.get(target_sid)
                    think(f"要把家长信发给 {s['name']} 的家长，走邮件通道（未配置 SMTP 时给可发送的 .eml）。")
                    res = call("send_parent_letter", self.t_send_letter, sid=target_sid)
                    if res.get("ok") and res.get("mode") == "smtp":
                        blocks.append(f"家长信已发送给 **{s['name']}** 的家长（{res['to']}）。")
                    elif res.get("ok"):
                        blocks.append(
                            f"当前未配置邮件服务器（演示环境），已生成 **{s['name']}** 家长信的邮件文件：\n\n"
                            f"[下载 .eml（收件人已填好，双击即进邮件客户端）]({res['url']})\n\n"
                            f"配置 AG_SMTP_* 环境变量后，同样一句话就会真实发送。")
                    else:
                        blocks.append(res.get("message", "发送失败。"))
                elif kind == "daily":
                    think("要今日日报：先聚合全校态势，正文直接给，再附 Word 链接。")
                    rep = call("daily_report", self.t_daily_report)
                    blocks.append(f"**{rep['date']} 预警日报**：{rep['summary']}")
                    blocks.append(rep["body"])
                    res = call("export_file", self.t_export, kind="daily")
                    blocks.append(f"[下载日报 Word 版]({res['url']})（定时任务每天 08:00 也会自动生成一份）")
                elif kind in ("semester", "interventions"):
                    _what = "学期汇报 PPT" if kind == "semester" else "干预台账"
                    think(f"导{_what}，全校数据现场聚合。")
                    res = call("export_file", self.t_export, kind=kind)
                    blocks.append(self._compose_export(res))
                elif target_sid:
                    s = self.engine.get(target_sid)
                    think(f"要导 {s['name']} 的文书，现场排版 Word。")
                    res = call("export_file", self.t_export, kind=kind, sid=target_sid)
                    blocks.append(self._compose_export(res, s["name"]))
                else:
                    blocks.append("要导哪个学生的？说名字（如「导出黄伟诚的家长信」），或先要一份名单再点名。")
            elif intent == "record" and target_sid:
                s = self.engine.get(target_sid)
                title, note, status = self._compose_record(message, s)
                think(f"这是一条记录指令，把「{title}」写进 {s['name']} 的干预台账。")
                res = call("record_intervention", self.t_record, sid=target_sid,
                           title=title, note=note, status=status)
                if res.get("ok"):
                    item = res["item"]
                    blocks.append(f"已记录到 **{s['name']}**（{s['class_name']}）的干预台账：")
                    blocks.append(f"- 标题：{item['title']}\n- 状态：{item['status']}\n- 时间：{item['created_at']}")
                    blocks.append("在学生详情抽屉里可以看到这条记录。继续问「他下一步该做什么」可以接上。")
                else:
                    blocks.append(res.get("message", "记录失败。"))
            elif intent == "brief" and target_sid:
                s = self.engine.get(target_sid)
                think(f"要谈话要点，直接生成 {s['name']} 的完整提纲（成因分型 + 依据 + 步骤）。")
                letter = call("counselor_brief", self.t_brief, sid=target_sid, school=school)
                citations = letter.get("citations", [])
                blocks.append(f"**{s['name']}**（{s['class_name']}）的谈话提纲：")
                blocks.append(letter["body"])
                blocks.append("提纲存为文档或直接照着谈都可以，谈完回来跟我说「记录：已完成谈话」即可归档。")
            elif intent == "overview":
                think("问的是全局，先统计全校分布，再找问题最集中的班。")
                o = call("campus_overview", self.t_overview)
                blocks.append(
                    f"全校 {o['total']} 人，红色预警 {o['dist']['red']} 人（{o['dist_pct']['red']}%），"
                    f"黄色关注 {o['dist']['yellow']} 人（{o['dist_pct']['yellow']}%），平均风险分 {o['avg_score']}。")
                worst = sorted(o["by_class"].items(), key=lambda x: -x[1]["red"])[:3]
                blocks.append("红色人数最多的班级：" + "、".join(f"{k}（{v['red']} 人）" for k, v in worst))
                blocks.append("当前最普遍的风险因素是：" + "、".join(f"{f['label']}（均摊 {f['points']} 分）" for f in o["top_factors"][:3]))
            elif intent == "trend" and target_sid:
                s = self.engine.get(target_sid)
                think(f"问的是 {s['name']} 的走势，拉他的五学期序列。")
                r = call("risk_score", self.t_risk, sid=target_sid)
                blocks.append(self._compose_trend(call("grade_trend", self.t_trend, sid=target_sid)))
                blocks.append(self._risk_sentence(s, r))
            elif intent == "trend" and not target_sid:
                rows = call("roster", self.t_roster, limit=300)
                if any(w in message for w in ["风险"]):
                    # 问的是"风险上升最快"：按风险分涨幅排，没红的也要点名
                    think("没有指名道姓，按风险分的涨幅给一份上升名单。")
                    rising = sorted(
                        [x for x in rows if x["direction"] == "up"],
                        key=lambda x: -x["delta"],
                    )[:6]
                    if rising:
                        listed = rising
                        blocks.append("风险分上升最快的 6 位学生（还没红的更要趁早谈）：")
                        blocks.append("\n".join(
                            f"- {x['name']}（{x['class_name']}）风险分 {x['score']}，较上学期 {x['delta']:+.0f} 分，"
                            f"主因 {x['top_factor']}"
                            for x in rising))
                        blocks.append("想深入哪位，说名字或「第 N 个」，也可以直接让我生成谈话要点。")
                    else:
                        blocks.append("当前没有风险分明显上升的学生。")
                else:
                    # 问的是"谁掉得最狠"：按班级名次的后退幅度排，比分数变化更抗口径差
                    think("没有指名道姓，按班级名次后退幅度给一份下滑名单。")
                    worst = sorted(
                        [x for x in rows if x["trend_rank_delta"] > 0],
                        key=lambda x: -x["trend_rank_delta"],
                    )[:6]
                    if worst:
                        listed = worst
                        blocks.append("成绩名次后退最多的 6 位学生：")
                        blocks.append("\n".join(
                            f"- {x['name']}（{x['class_name']}）班级第 {x['trend_rank']} 名，"
                            f"较大一后退 {x['trend_rank_delta']} 名，{x['trend_label']}"
                            for x in worst))
                        blocks.append("想看哪位的完整曲线，直接说名字或「第 N 个」。")
                    else:
                        blocks.append("当前没有名次明显后退的学生。")
            elif intent == "score":
                # 成绩类问题：点名了就给那位的单科成绩，点了班就给全班排名，
                # 什么都没说就给各班横向对比。原来这一类没有分支，落到名单上按风险分排，
                # 用户问「谁成绩最好」，拿回来的是「谁最危险」。
                from . import scores as scores_mod
                cls = self._match_class(message)
                want_course = next((c["name"] for c in self.engine.students[0]["courses"]
                                    if c["name"] in message), None)
                if target_sid:
                    s = self.engine.get(target_sid)
                    think(f"问的是 {s['name']} 的分数，按每门课期中卷面给。")
                    blocks.extend(call("score_detail", self._compose_scores, sid=target_sid))
                    rank, total, base = scores_mod.class_rank(self.engine, s)
                    blocks.append(f"放到班里横向看：{s['class_name']} 共 {total} 人，"
                                  f"按学分加权期中均分排第 {rank} 名（班均 {base} 分）。")
                else:
                    think("没有点名，按成绩给班级排名。")
                    blocks.extend(call("class_score_detail", self._compose_class_scores,
                                       cls=cls, course=want_course))
            elif intent == "roster":
                n = self._match_ordinal(message)
                if n and last and last.get("roster"):
                    # 在追问上一轮名单里的第 N 位：展开那位学生，不再重拉一遍名单
                    if target_sid:
                        s = self.engine.get(target_sid)
                        think(f"「第{n}个」指的是上一轮名单里的 {s['name']}（{s['class_name']}），展开他的情况。")
                        r = call("risk_score", self.t_risk, sid=target_sid)
                        blocks.append(self._risk_sentence(s, r))
                        blocks.append("拆开看是这样：\n" + "\n".join(f"- {x}" for x in self._factor_detail(s, r)))
                        blocks.append(self._compose_trend(call("grade_trend", self.t_trend, sid=target_sid)))
                        acts = call("interventions", self.t_actions, sid=target_sid)
                        blocks.append(f"最该先做的一件事：**{acts[0]['title']}** —— {acts[0]['detail']}（{acts[0]['deadline']}）。")
                        blocks.append("要谈话要点说一声；谈完「记录：已完成谈话」即可归档。")
                    else:
                        blocks.append(f"上一轮名单里只有 {len(last['roster'])} 个人，没有第 {n} 个。")
                else:
                    cls = self._match_class(message)
                    want_red = "红" in message
                    rows = call("roster", self.t_roster, class_name=cls, level="red" if want_red else None, limit=40)
                    # 把判定阈值一并写进事实段：否则润色那一步会自己发明一句
                    # 「我不知道红色预警的分数线」，把本来算对的结论说成答不了。
                    red_line = self.engine.config.get("red_line")
                    scope = f"{cls}（红色预警 = 风险分 ≥ {red_line}）" if want_red and red_line else (cls or "全校")
                    if any(w in message for w in ["上升", "变化", "趋势", "最快", "恶化"]):
                        rows = sorted([x for x in rows if x["direction"] == "up"], key=lambda x: -x["delta"])[:6]
                        head = "风险上升最快的 6 位学生（尚未计入红色名单的也要盯）："
                    else:
                        # 先记总人数再截断：只给前 6 条时，模型会怀疑「是不是还有没列出来的」，
                        # 于是加上一句「不能断定只有这 2 人」——数据本身是全的，必须告诉它。
                        total = len(rows)
                        rows = rows[:6]
                        if cls:
                            head = (f"{scope}共 {total} 人，已全部列出："
                                    if total <= 6 else f"{scope}共 {total} 人，前 6 位：")
                        else:
                            head = f"风险最高的 {len(rows)} 位学生："
                    if rows:
                        listed = rows
                        think(f"拉到了 {len(rows)} 条名单，按风险分排好序。")
                        blocks.append(head)
                        blocks.append("\n".join(
                            f"- {x['name']}（{x['class_name']}）风险分 {x['score']}，较上学期 {x['delta']:+.0f} 分，主因 {x['top_factor']}"
                            for x in rows))
                        blocks.append("想深入哪位，说名字或「第 N 个」，也可以直接让我生成谈话要点。")
                    else:
                        blocks.append("当前没有符合条件的红色预警学生。")
            elif intent == "policy":
                think("这问的是制度条款，去校规知识库里检索。")
                hits = call_rag(message, school=school)
                citations = hits
                blocks.append(self._compose_policy(hits))
            elif intent == "contact":
                # 导员/教务问老师联系方式：用任一学生的课表都能定位课程与教师档案
                any_sid = target_sid or self.engine.students[0]["id"]
                think("问的是任课老师，从课表里带出教师档案与联系方式。")
                blocks.extend(self._compose_contact(any_sid, message, who=""))
            elif target_sid:
                s = self.engine.get(target_sid)
                think(f"没有更具体的指令，给 {s['name']} 一份风险拆解 + 最该做的事。")
                r = call("risk_score", self.t_risk, sid=target_sid)
                blocks.append(self._risk_sentence(s, r))
                blocks.append("拆开看是这样：\n" + "\n".join(f"- {x}" for x in self._factor_detail(s, r)))
                acts = call("interventions", self.t_actions, sid=target_sid)
                blocks.append(f"最该先做的一件事：**{acts[0]['title']}**。")
            else:
                blocks.append("这个我查不到——系统里没有这类数据（不在学情库里）。可以问我：某个学生的风险原因（直接说名字）、班级风险名单、校规条款，或全校整体情况。")

        reply = "\n\n".join(blocks)

        # ---- 规则引擎「看着答了、其实没信息量」的两种情形，也交给模型重试 ----
        # 1) 走了兜底话术：六处「答不准 / 可以问我」，用户问什么都得到同一段
        # 2) 关键词误命中：问联系方式时句子里既没有老师名也没有课名
        #    （「学校机房几点关门」被「几点」命中了 contact，答出来是六位老师的邮箱）
        # 认出来就交模型重试一次，它至少能说清「这个查不到」或换个角度答。
        if llm.available() and (any(m in reply for m in _FALLBACK_MARKS)
                                or (intent == "contact"
                                    and not self._contact_supported(message))):
            from . import router as router_mod
            routed = router_mod.route(self, role, sid, message, school, profile, emit)
            if routed:
                if trace:
                    routed["trace"] = trace + list(routed.get("trace") or [])
                    routed["thoughts"] = thoughts + list(routed.get("thoughts") or [])
                return routed

        if llm.available():
            context = "\n".join(blocks + ([facts_ctx] if facts_ctx else []))
            cit = "\n".join(
                f"[{i}] {c['citation']}"
                f"（{c.get('school', '')}{'·' if c.get('school') else ''}相关度 {c.get('score_pct', '')}）："
                f"{c['text'][:180]}"
                for i, c in enumerate(citations, 1)
            )
            if cit:
                cit += ("\n（引用条款时在句末用序号标注，如 [1][2]；"
                        "只能引用上面列出的这几条，没有的条款不要编。）")
            # 多轮上下文：把最近两轮的问答摘要给模型，它才知道"他"是谁
            hist_txt = ""
            if mkey and self.memory:
                pairs = []
                for turn in self.memory.history(mkey)[-2:]:
                    if turn.get("message"):
                        pairs.append(f"用户：{turn['message'][:60]}\n助手：{turn['reply'][:120]}")
                if pairs:
                    hist_txt = "最近对话：\n" + "\n".join(pairs) + "\n\n"
            messages = [
                {"role": "system", "content": PERSONAS.get(role, PERSONAS["admin"])},
                {"role": "user", "content": f"{hist_txt}事实：\n{context}\n\n可引用条款：\n{cit}\n\n用户问题：{message}"},
            ]
            polished = None
            if emit:
                # 流式：逐块推给前端，同时拼成完整回答
                buf: list[str] = []
                for piece in llm.chat_stream(messages, model=llm.route_model() or None):
                    buf.append(piece)
                    emit("delta", {"text": piece})
                polished = "".join(buf).strip() or None
            else:
                polished = llm.chat(messages, model=llm.route_model() or None)
            if polished:
                reply = polished
                model_name = llm.route_model() or llm._model()
                item = {"tool": "llm_polish",
                        "args": {"model": model_name}, "ms": 0,
                        "evidence": {"source": "大模型", "table": f"模型 {model_name}",
                                     "rows": 1, "unit": "段回答",
                                     "ts": time.strftime("%H:%M:%S"), "ms": 0,
                                     "detail": "只做措辞，事实全部来自上面的工具"}}
                trace.append(item)
                if emit:
                    emit("tool", item)

        # ---- 数据依据：回答里引用了风险分与因素，就把这张表也挂进引用分组 ----
        # 校规条款能查到出处，分数以前只有结论没有来路；这里补上「六因素怎么加到 68.8」。
        if risk_seen.get("r") and intent in ("why", "advice", "trend", "roster", "overview", "policy"):
            rr = risk_seen["r"]
            factors = "、".join(
                f"{f['label']} {f.get('points', 0)}" for f in (rr.get("factors") or [])[:6]
            )
            data_cit = {
                "kind": "data",
                "citation": f"风险评分明细 · {rr.get('score')} 分（{rr.get('level_label')}）",
                "source": "students 表 · risk_score() 六因素加权",
                "text": f"六因素得分：{factors}。"
                        + (f"硬性规则命中：{'；'.join(rr.get('overrides') or [])}。" if rr.get("overrides") else ""),
            }
            if not any(c.get("kind") == "data" for c in citations):
                citations = list(citations) + [data_cit]
        # 名单类回答一个数字都没引校规，但「谁排在前面」同样需要出处
        elif roster_seen.get("rows") and intent in ("roster", "overview"):
            rows = roster_seen["rows"]
            head = "、".join(
                f"{x.get('name', '')} {x.get('score', '')}" for x in rows[:5] if isinstance(x, dict)
            )
            if not any(c.get("kind") == "data" for c in citations):
                citations = list(citations) + [{
                    "kind": "data",
                    "citation": f"风险名单 · 命中 {len(rows)} 名学生",
                    "source": "students 表 · 按风险分降序",
                    "text": f"按风险分排序取前 5 位：{head}。" + (f"其余 {len(rows) - 5} 人略。" if len(rows) > 5 else ""),
                }]
        # 全校统计与课堂数据同理：页面上那几个数字也要能点开看出处
        elif overview_seen.get("o") and intent in ("overview", "roster"):
            o = overview_seen["o"]
            dist = o.get("dist") or {}
            if not any(c.get("kind") == "data" for c in citations):
                citations = list(citations) + [{
                    "kind": "data",
                    "citation": f"全校概览 · {o.get('total', '—')} 名在册学生",
                    "source": "students 表 · 全校分布统计",
                    "text": (f"红 {dist.get('red', 0)} 人、黄 {dist.get('yellow', 0)} 人、"
                             f"绿 {dist.get('green', 0)} 人；风险上升 {o.get('rising_count', '—')} 人，"
                             f"人均风险分 {o.get('avg_score', '—')}。数据更新于 {o.get('updated_at', '—')}。"),
                }]
        elif teacher_seen.get("tv") and not any(c.get("kind") == "data" for c in citations):
            tv = teacher_seen["tv"]
            citations = list(citations) + [{
                "kind": "data",
                "citation": f"课堂数据 · 任教 {len(tv.get('courses') or [])} 门课",
                "source": "classroom · 考勤与作业明细",
                "text": (f"{tv.get('teacher', '')} 名下 {len(tv.get('students') or [])} 名修课学生，"
                         f"风险分与缺勤、未交作业次数逐人汇总。"),
            }]

        # ---- 追问材料：把「图上写的是多少」摆到最前面 ----
        # 不加这段的话，用户问「第三行是哪门课」，规则链会按意图去查系统成绩，
        # 回一串系统里的课，图上的内容一个字都没答——用户会觉得「它又忘了」。
        if reread:
            reply = (f"从你之前发的那张图上看到：{reread.strip()}\n\n"
                     "下面是系统里记的数据，两边对不上时以系统为准：\n\n" + reply)

        # ---- 写记忆：这轮"在说谁"要记住，下一轮的"他/第N个"才能接上 ----
        roster_snapshot = None
        if listed:
            roster_snapshot = [
                {"id": x["id"], "name": x["name"], "class_name": x["class_name"], "score": x.get("score")}
                for x in listed[:8]
            ]
        if mkey and self.memory:
            self.memory.append(mkey, {
                "message": (raw_message or message)[:200],
                "reply": reply[:400],
                "sid": target_sid if role not in ("student", "parent") else sid,
                "intent": intent,
                "roster": roster_snapshot,
            })

        return {
            "reply": reply,
            "intent": intent,
            "citations": citations,
            "trace": trace,
            "thoughts": thoughts,
            # 方案 C：这一轮如果落到「能替你做的一件事」，给一张待确认的卡片；
            # 只在用户点头后才执行，AI 不自作主张。
            "action": self._propose_action(role, intent, target_sid),
            "elapsed_ms": round((time.time() - t0) * 1000, 1),
            "suggestions": self._suggestions(role, intent, target_sid if role not in ("student", "parent") else sid),
        }

    def _propose_action(self, role: str, intent: str, target_sid: str | None) -> dict | None:
        """方案 C「对话即操作」：把下一步能替用户做的事摆成一张卡片。

        三条纪律：
        1. 只在答完「能落到动作」的问题时给，且一轮最多一张，不刷屏；
        2. 按角色过滤——学生端永远拿不到发给家长的动作，越权入口一个都不留；
        3. 只 propose 不执行：写台账、发信、发消息都要等用户点确认。
        """
        if not target_sid:
            return None
        try:
            s = self.engine.get(target_sid)
        except Exception:  # noqa: BLE001 - 学生不存在就别给卡片
            return None
        name = s.get("name") or ""
        risk: dict = {}
        try:
            risk = self.engine.score(target_sid)
        except Exception:  # noqa: BLE001
            risk = {}
        factors = risk.get("factors") or []
        top = ""
        if factors:
            top = (max(factors, key=lambda f: f.get("points") or 0).get("label") or "")
        level = risk.get("level") or ""

        if role == "student":
            # 学生只可能导出自己的文书；发给家长这类动作连入口都不给。
            # export 类问题回答里已经带下载链接了，不再叠一张重复的卡。
            if intent == "letter":
                return actions_mod.propose(
                    role, "export_letter", target_sid,
                    label="导出我的学业告知函",
                    payload={"sid": target_sid, "letter_type": "student"},
                    hint="生成一份可以给家长看的 Word，内容和你看到的一致",
                )
            return None

        if role == "parent":
            if intent == "letter":
                return actions_mod.propose(
                    role, "export_letter", target_sid,
                    label=f"导出 {name} 的家长告知函",
                    payload={"sid": target_sid, "letter_type": "parent"},
                )
            return None

        if role in ("counselor", "admin"):
            if intent == "brief":
                # 谈完最自然的下一步是归档，但归档是写操作：给卡片，不代劳
                return actions_mod.propose(
                    role, "record_intervention", target_sid,
                    label=f"把这次谈话记进 {name} 的台账",
                    payload={"sid": target_sid, "title": f"{name} 学业谈话",
                             "note": "按谈话提纲沟通" + (f"（主因：{top}）" if top else ""),
                             "status": "已完成"},
                    hint="点确认才写入台账；执行后还能撤销",
                )
            if intent == "letter":
                return actions_mod.propose(
                    role, "export_letter", target_sid,
                    label=f"导出 {name} 的家长告知函",
                    payload={"sid": target_sid, "letter_type": "parent"},
                )
            if intent == "export":
                # 回答里已经给了下载链接，不再摆一张重复的卡
                return None
            if intent in ("why", "advice", "trend"):
                if level == "red":
                    return actions_mod.propose(
                        role, "send_letter", target_sid,
                        label=f"给 {name} 的家长发学业预警告知函",
                        payload={"sid": target_sid, "to": f"parent.{target_sid}@example.com"},
                        hint="红色预警按校规应当书面告知家长；发送前请先核对内容",
                    )
                if role == "counselor" and top:
                    txt = (f"您好，我是{name}的辅导员。这次同步一下{name}最近的情况："
                           f"目前主要需要留意的是{top}，学校这边已经在跟进。"
                           f"想和您约个时间聊一聊，看看家里能配合做点什么。")
                    return actions_mod.propose(
                        role, "message_parent", target_sid,
                        label=f"给 {name} 的家长发一条沟通消息",
                        payload={"sid": target_sid, "text": txt},
                        hint="消息内容可以改；确认后才出现在家校沟通里",
                    )
        return None

    def _suggestions(self, role: str, intent: str = "", sid: str | None = None) -> list[str]:
        """建议词跟着上下文走：刚答完名单就引导点名，刚答完走势就引导落到行动。"""
        if role == "student":
            if intent == "export":
                return ["导出我的学业预警通知书", "我的风险分为什么这么高？", "这学期还来得及补回来吗？"]
            if intent == "trend":
                return ["那我最弱的一门怎么办？", "这学期还来得及补回来吗？", "我的风险分为什么这么高？"]
            if intent == "why":
                return ["我该先做哪件事？", "导出我的告知函", "挂多少学分会被降级？"]
            if intent == "attendance":
                return ["我哪次作业没交？", "数据结构老师的邮箱是多少？", "我的风险分为什么这么高？"]
            if intent == "homework":
                return ["我缺了几次课？", "这学期还来得及补回来吗？", "我的成绩是在涨还是在掉？"]
            if intent == "contact":
                return ["我缺了几次课？", "我哪次作业没交？", "这学期修了多少学分？"]
            if intent == "course":
                return ["我哪次作业没交？", "数据结构老师的答疑时间？", "我的成绩是在涨还是在掉？"]
            return ["我的成绩是在涨还是在掉？", "我哪次作业没交？", "数据结构老师的联系方式"]
        if role == "counselor":
            if intent == "export":
                return ["生成学期汇报 PPT", "导出干预台账", "今日日报说了什么？"]
            if intent == "roster":
                return ["第 2 个的情况展开说说", "给他生成谈话要点", "记录：已约周三下午谈话"]
            if intent == "trend":
                return ["给他生成谈话要点", "把家长信发给家长", "本班谁的风险上升最快？"]
            if intent == "brief":
                return ["把家长信发给家长", "导出谈话要点 Word", "记录：今天已完成谈话"]
            if intent == "record":
                return ["导出干预台账", "给他生成谈话要点", "本班谁的风险上升最快？"]
            if sid:
                return ["给他生成谈话要点", "把家长信发给家长", "导出他的家长信"]
            return ["本班谁的风险上升最快？", "今日日报说了什么？", "生成学期汇报 PPT"]
        if role == "admin":
            if intent == "export":
                return ["今日日报说了什么？", "生成学期汇报 PPT", "全校风险分布如何？"]
            return ["全校风险分布如何？", "今日日报说了什么？", "生成学期汇报 PPT"]
        if role == "parent":
            return ["孩子的成绩趋势怎么样？", "导出家长信", "学校什么情况下会通知家长？"]
        if role == "teacher":
            if intent == "roster":
                return ["第 2 个学生的情况", "谁的风险最高？", "班均多少？"]
            if intent == "attendance":
                return ["他哪次作业没交？", "谁的风险最高？", "我该重点关注谁？"]
            if intent == "homework":
                return ["他缺了几次课？", "谁的风险最高？", "我该重点关注谁？"]
            if intent == "why":
                return ["我该重点关注谁？", "班均多少？", "建议联系辅导员"]
            if intent == "advice":
                return ["我课上的学生", "班均多少？", "谁的风险最高？"]
            if intent == "course":
                return ["我课上的学生", "谁的风险最高？", "班均多少？"]
            return ["我课上的学生", "谁的风险最高？", "我该重点关注谁？"]
        return []

    # ---------- 主动简报：各端打开页面时智能体先开口 ----------
    def briefing(self, role: str, sid: str | None, profile: dict | None = None) -> dict:
        """每个角色进页面时的第一句话：一句话态势 + 三条要点 + 可追问的问题。"""
        points: list[dict] = []
        if role == "student" and sid:
            s = self.engine.get(sid)
            r = self.engine.score(sid)
            gt = trend_mod.grade_trend(s)
            acts = self.engine.interventions(sid)[:3]
            weakest = gt["courses"][0] if gt["courses"] else None
            points.append({
                "label": "风险态势",
                "text": f"当前风险分 {r['score']}（{r['level_label']}），"
                        f"主导因素是{r['factors'][0]['label']}。",
                "tone": r["level"],
            })
            points.append({
                "label": "成绩走势",
                "text": gt["summary"],
                "tone": "up" if gt["slope"]["direction"] == "up" else "down" if gt["slope"]["direction"] == "down" else "flat",
            })
            if weakest:
                points.append({
                    "label": "最该盯的课",
                    "text": f"{weakest['name']}（期中 {weakest['midterm']} 分，{weakest['trend_label']}）。",
                    "tone": "warn",
                })
            points.append({
                "label": "今天能做的",
                "text": acts[0]["title"] + " —— " + acts[0]["detail"][:40] + "…" if acts else "保持当前节奏。",
                "tone": "ok",
            })
            return {
                "greeting": f"{s['name']}，早。我是你的学业助手，先看一眼今天的状态——",
                "points": points,
                "asks": ["我的成绩是在涨还是在掉？", "那我最弱的一门怎么办？", "这学期还来得及补回来吗？"],
            }

        if role == "parent" and sid:
            s = self.engine.get(sid)
            r = self.engine.score(sid)
            gt = trend_mod.grade_trend(s)
            return {
                "greeting": "您好，我是家校助手。孩子这学期的整体情况是这样——",
                "points": [
                    {"label": "当前状态", "text": f"{r['level_label']}，风险分 {r['score']}，主导因素 {r['factors'][0]['label']}。", "tone": r["level"]},
                    {"label": "成绩走势", "text": gt["summary"], "tone": "flat"},
                    {"label": "本周关注", "text": f"期中加权均分 {r['raw']['mid_avg']}（班均 {r['raw']['cohort_avg']}），缺勤 {r['raw']['absent']} 次、作业少交 {r['raw']['hw_assigned'] - r['raw']['hw_submitted']} 次。", "tone": "warn"},
                ],
                "asks": ["孩子的成绩趋势怎么样？", "我们家长能做什么？", "学校什么情况下会通知家长？"],
            }

        if role == "teacher":
            teacher_name = (profile or {}).get("advisor") or (profile or {}).get("name") or ""
            try:
                tv = self.engine.teacher_view(teacher_name)
                my = tv["students"]
            except Exception:
                my, tv = [], {"courses": []}
            red = [x for x in my if x["level"] == "red"]
            top = my[0] if my else None
            pts = [
                {"label": "任课概况",
                 "text": f"本学期教 {len(tv['courses'])} 门课、{len(my)} 名学生，红色预警 {len(red)} 人。",
                 "tone": "warn" if red else "ok"},
            ]
            if top:
                pts.append({"label": "最高风险",
                            "text": f"{top['name']}（{top['class_name']}）风险分 {top['score']}，主因 {top['top_factor']}。",
                            "tone": top["level"]})
            pts.append({"label": "教学建议",
                        "text": "从红色学生盯起，缺勤与作业未交的优先反馈给辅导员。",
                        "tone": "ok"})
            return {
                "greeting": f"{teacher_name}老师，我是你的教学助手。先看一眼你课上的情况——",
                "points": pts,
                "asks": ["我课上的学生", "谁的风险最高？", "我该重点关注谁？"],
            }

        if role == "counselor":
            # 辅导员账号刘畅带计科 2404-2406；按 advisor 过滤出"自己名下"的学生
            advisor = (profile or {}).get("name") or "刘畅"
            mine = [s for s in self.engine.students if s.get("advisor") == advisor]
            scope = f"你名下的 {len(mine)} 位学生" if mine else "全校学生"
            pool = mine if mine else self.engine.students
            rows = sorted(pool, key=lambda x: -self.engine.score(x["id"])["score"])
            red = [x for x in rows if self.engine.score(x["id"])["level"] == "red"]
            rising = sorted(pool, key=lambda x: -self.engine.score(x["id"])["trend"]["delta"])[:3]
            rising = [x for x in rising if self.engine.score(x["id"])["trend"]["delta"] > 5]
            worst_class = {}
            for x in pool:
                sc = self.engine.score(x["id"])
                if sc["level"] != "green":
                    worst_class[x["class_name"]] = worst_class.get(x["class_name"], 0) + 1
            hot = sorted(worst_class.items(), key=lambda kv: -kv[1])[:1]
            points.append({
                "label": "今日名单",
                "text": f"{scope}里红色预警 {len(red)} 人，最高分 {rows[0]['name']}（{self.engine.score(rows[0]['id'])['score']} 分）。",
                "tone": "warn",
            })
            if hot:
                points.append({"label": "最集中的班", "text": f"{hot[0][0]} 非绿色学生 {hot[0][1]} 人，优先安排走访。", "tone": "warn"})
            if rising:
                names = "、".join(f"{x['name']}（{self.engine.score(x['id'])['trend']['delta']:+.0f}）" for x in rising[:3])
                points.append({"label": "上升最快", "text": f"风险分涨得最猛的三位：{names}，趁还没红先谈。", "tone": "down"})
            points.append({"label": "建议动作", "text": "从红色名单里挑一位生成谈话要点，谈完直接在对话里记录归档。", "tone": "ok"})
            return {
                "greeting": "刘老师，早。看过夜里的数据了，今天有三件事值得你先知道——",
                "points": points,
                "asks": ["本班谁的风险上升最快？", "给红色名单第一位生成谈话要点", "谁的成绩掉得最狠？"],
            }

        # admin / 兜底
        o = self.engine.overview()
        worst = sorted(o["by_class"].items(), key=lambda x: -x[1]["red"])[:3]
        return {
            "greeting": "张老师，早。全校昨夜跑完一轮评估，先看三个数字——",
            "points": [
                {"label": "全校分布", "text": f"{o['total']} 人中红色 {o['dist']['red']} 人（{o['dist_pct']['red']}%）、黄色 {o['dist']['yellow']} 人，平均风险分 {o['avg_score']}。", "tone": "warn"},
                {"label": "班级热点", "text": "红色最多的是 " + "、".join(f"{k}（{v['red']} 人）" for k, v in worst) + "。", "tone": "warn"},
                {"label": "主要因素", "text": "全校最普遍的风险因素是 " + "、".join(f"{f['label']}" for f in o["top_factors"][:3]) + "。", "tone": "flat"},
            ],
            "asks": ["全校风险分布如何？", "哪些班级问题最集中？", "把红色名单导出来说说看"],
        }
