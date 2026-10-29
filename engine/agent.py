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

from . import llm, trend as trend_mod
from .letters import counselor_brief
from .memory import ConversationMemory, memory_key
from .rag import KnowledgeBase

POLICY_WORDS = ["校规", "规定", "政策", "教育部", "降级", "劝退", "退学", "学分要求",
                "多少学分", "几门", "预警线", "通知家长", "什么时候", "多久", "文件"]
WHY_WORDS = ["为什么", "原因", "怎么回事", "怎么算", "依据", "评估", "风险分", "多少分", "严重"]
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
# 谈话要点：辅导员在对话里直接要一份提纲，不用去页面点
BRIEF_WORDS = ["谈话要点", "谈话提纲", "谈话大纲", "生成谈话", "谈一下", "怎么跟他谈",
               "怎么谈", "谈话建议", "给我一份谈话"]
# 记录动作：把谈话结果写回系统，对话即操作
RECORD_WORDS = ["记录一下", "记录", "登记", "已谈", "谈过了", "谈完了", "刚谈完",
                "已经谈话", "做了辅导", "已联系"]
# 指代与追问：这些词本身不带主题，得靠上一轮的记忆补全
PRONOUN_WORDS = ["他", "她", "这个学生", "这孩子", "那孩子", "这位同学"]
# 任课老师与联系方式：数据在每门课的 teacher_profile 里，不在校规库里
CONTACT_WORDS = ["老师", "任课", "教师", "电话", "邮箱", "联系方式", "办公室",
                 "答疑", "几点", "上课时间", "办公时间", "怎么联系", "office hour"]
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
# 四端人设：同一个引擎，四个端口各自有不同的身份、口吻与内容边界。
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


class Agent:
    def __init__(self, engine, kb: KnowledgeBase, store,
                 memory: ConversationMemory | None = None,
                 recorder=None, mailer=None, reporter=None):
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
        # 姓名索引：240 个学生两三个字的中文姓名，直接建 dict，最长匹配优先
        self._names: dict[str, dict] = {s["name"]: s for s in engine.students}
        self._classes: list[str] = sorted({s["class_name"] for s in engine.students})

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

    def t_actions(self, sid: str) -> list[dict]:
        return self.engine.interventions(sid)

    def t_policy(self, query: str, school: str | None = None) -> list[dict]:
        # policy 检索跨全库：评委/学生问的是通用规则，不该被学校名挡住具体条款
        # （如「挂多少学分会被降级」应召回华南理工「降级试读条件·25 学分」，
        #  而非只剩教育部通用政策）。school 参数保留兼容调用，内部不限定。
        hits = self.kb.search(query, top_k=4, school=None, min_score=0.3)
        return hits[:3]

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
        }
        if "怎么办" in text or "建议" in text:
            scores["advice"] += 1.5
        if "降级" in text or "劝退" in text or "规定" in text:
            scores["policy"] += 2
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
        # 老师联系方式必然伴随课程或「老师」本身，别让「数据结构」里的「结构」类词干扰
        if any(w in text for w in ["电话", "邮箱", "联系方式", "办公室", "答疑"]):
            scores["contact"] += 2
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
                tail = f"，低于班级均分 {gap} 分" if gap > 0 else "，高于班级均分"
                out.append(f"期中：加权均分 {raw['mid_avg']}，班级均分 {raw['cohort_avg']}{tail}")
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
        for h in hits:
            first = h["text"].strip().split("\n")[0]
            lines.append(f"- **{h['title']}**：{first}")
        lines.append("\n以上条款来自知识库原文，可在下方引用里核对。")
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

    def answer(self, role: str, sid: str | None, message: str, school: str | None = None,
               emit=None, profile: dict | None = None) -> dict:
        """生成回答。

        emit: 可选回调 emit(kind, payload)，用于把中间过程推给流式接口。
              kind 取值 meta / thought / tool / delta；不传则行为与原来完全一致。
        profile: 登录身份，用来定位会话记忆；不给则不开多轮能力。
        """
        t0 = time.time()
        trace: list[dict] = []
        citations: list[dict] = []
        intent = self._intent(message)
        blocks: list[str] = []
        thoughts: list[str] = []
        # 本轮对话里实际列过的名单（供下一轮"第 N 个"指代）
        listed: list[dict] | None = None

        def think(text: str) -> None:
            thoughts.append(text)
            if emit:
                emit("thought", {"text": text})

        if emit:
            emit("meta", {"intent": intent})

        # ---- 多轮：取上一轮记忆，消解这轮在说谁 ----
        last: dict | None = None
        mkey = memory_key(profile) if (profile and self.memory) else None
        if mkey:
            hist = self.memory.history(mkey)
            if hist:
                last = hist[-1]

        target_sid = sid
        if role in ("counselor", "admin"):
            target_sid, thought = self.resolve_target(message, role, sid, last)
            if thought:
                think(thought)

        def call(name, fn, **kwargs):
            start = time.time()
            result = fn(**kwargs)
            item = {
                "tool": name,
                "args": {k: v for k, v in kwargs.items() if v is not None},
                "ms": round((time.time() - start) * 1000, 1),
            }
            trace.append(item)
            if emit:
                emit("tool", item)
            return result

        if role == "student" and sid:
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
                hits = call("retrieve_policy", self.t_policy, query=message, school=school)
                citations = hits
                blocks.append(self._compose_policy(hits))
                blocks.append(f"对照你的情况：风险分 {r['score']}，累计挂科学分 {s['history']['failed_credits']}。")
            if intent == "contact":
                think("问的是任课老师，从课表里带出老师的档案与联系方式。")
                blocks.extend(self._compose_contact(sid, message, who=""))
            if intent == "attendance":
                think("问的是考勤明细，落到每一次异常记录。")
                blocks.extend(self._compose_attendance(sid))
            if intent == "homework":
                think("问的是作业明细，把未交和迟交的挑出来。")
                blocks.extend(self._compose_homework(sid))
            if intent == "course":
                think("问的是课表或学分，直接给在修课程清单。")
                blocks.extend(self._compose_courses(sid))
            if not blocks:
                # 没听懂的问题：先试知识库；检索不到就直说不会，绝不拿风险分充数
                think("没匹配到已知问法，先去校规知识库试一次。")
                hits = call("retrieve_policy", self.t_policy, query=message, school=school)
                if hits:
                    citations = hits
                    blocks.append(self._compose_policy(hits))
                    blocks.append(f"对照你的情况：风险分 {r['score']}，累计挂科学分 {s['history']['failed_credits']}。")
                else:
                    blocks.append("这个问题我暂时答不准，不想瞎猜误事。我擅长这些：")
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
                    blocks.extend(self._compose_contact(sid, message, who="孩子"))
                elif intent == "attendance":
                    blocks.extend(self._compose_attendance(sid, who="孩子"))
                elif intent == "homework":
                    blocks.extend(self._compose_homework(sid, who="孩子"))
                else:
                    blocks.extend(self._compose_courses(sid, who="孩子"))
            if intent == "trend":
                # 成绩走势已经答完了，不再叠一段政策，家长一次只吸收一件事
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
                hits = call("retrieve_policy", self.t_policy, query=message + " 家长 学业预警", school=school)
                citations = hits
                blocks.append(self._compose_policy(hits))
                blocks.append(
                    f"对照 {s['name']} 的情况：风险分 {r['score']}（{r['level_label']}），"
                    f"累计挂科 {s['history']['failed_credits']} 学分，目前处于关注与帮扶阶段，尚未触发处分线。")
            elif intent == "unknown":
                blocks.append("这个问题我答不准，不想瞎猜。我擅长帮您看这些：")
                blocks.append("- 孩子的出勤与作业：「孩子哪次作业没交」「孩子缺了几次课」")
                blocks.append("- 任课老师联系：「数据结构老师怎么联系」")
                blocks.append("- 孩子的成绩走势与风险：「孩子成绩怎么样」「孩子的风险分」")
                blocks.append("- 学校关于家校通知的规定：「学校什么情况下会通知家长」")
            else:
                hits = call("retrieve_policy", self.t_policy, query="家长 通知 学业预警", school=school)
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

            if intent == "course" or any(w in message for w in ["教的课", "教什么课", "几门课", "我教什么"]):
                think("问的是自己教的课，给课程清单。")
                cs = tv["courses"]
                blocks.append(f"你本学期教 {len(cs)} 门课：")
                blocks.append("\n".join(f"- **{c['name']}**（{c.get('credit','')} 学分·{c.get('kind','')}·{c.get('period','')}）" for c in cs))
                blocks.append(f"修这些课的学生共 {len(my_students)} 人，要看名单就说「我课上的学生」。")
            elif any(w in message for w in ["班均", "平均", "成绩"]) and not t_sid:
                think("问的是班级成绩，给各课期中班均。")
                for c in tv["courses"]:
                    scs = [st["courses"][0]["midterm"] for st in my_students
                           if st["courses"] and st["courses"][0]["code"] == c["code"]
                           and st["courses"][0].get("midterm") is not None]
                    if scs:
                        blocks.append(f"- **{c['name']}** 期中班均 {round(sum(scs) / len(scs), 1)}，最高 {max(scs)}，最低 {min(scs)}。")
                blocks.append("想看某位学生的明细，说名字或「第 N 个」。")
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
                hits = call("retrieve_policy", self.t_policy, query=message, school=school)
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
                blocks.append("这个问题我答不准。我擅长帮你看：")
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
                    rows = call("roster", self.t_roster, class_name=cls, level="red" if "红" in message else None, limit=40)
                    if any(w in message for w in ["上升", "变化", "趋势", "最快", "恶化"]):
                        rows = sorted([x for x in rows if x["direction"] == "up"], key=lambda x: -x["delta"])[:6]
                        head = "风险上升最快的 6 位学生（尚未计入红色名单的也要盯）："
                    else:
                        rows = rows[:6]
                        head = f"{cls or '全校'}风险最高的 {len(rows)} 位学生：" if cls else f"风险最高的 {len(rows)} 位学生："
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
                hits = call("retrieve_policy", self.t_policy, query=message, school=school)
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
                blocks.append("可以问我：某个学生的风险原因（直接说名字）、班级风险名单、校规条款，或全校整体情况。")

        reply = "\n\n".join(blocks)

        if llm.available():
            context = "\n".join(blocks)
            cit = "\n".join(f"- {c['citation']}：{c['text'][:120]}" for c in citations)
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
                for piece in llm.chat_stream(messages):
                    buf.append(piece)
                    emit("delta", {"text": piece})
                polished = "".join(buf).strip() or None
            else:
                polished = llm.chat(messages)
            if polished:
                reply = polished
                item = {"tool": "llm_polish", "args": {"model": llm.MODEL}, "ms": 0}
                trace.append(item)
                if emit:
                    emit("tool", item)

        # ---- 写记忆：这轮"在说谁"要记住，下一轮的"他/第N个"才能接上 ----
        roster_snapshot = None
        if listed:
            roster_snapshot = [
                {"id": x["id"], "name": x["name"], "class_name": x["class_name"], "score": x.get("score")}
                for x in listed[:8]
            ]
        if mkey and self.memory:
            self.memory.append(mkey, {
                "message": message[:200],
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
            "elapsed_ms": round((time.time() - t0) * 1000, 1),
            "suggestions": self._suggestions(role, intent, target_sid if role not in ("student", "parent") else sid),
        }

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
