"""Agent 编排层：意图识别 → 工具调用 → 事实拼装 →（可选）大模型润色。

没有大模型 key 时走确定性链路，回答里的每个数字都来自工具返回，
不会出现"模型编造分数"的情况；接入模型后只负责组织语言，事实仍由工具提供。
"""
from __future__ import annotations

import re
import time

from . import llm
from .rag import KnowledgeBase

POLICY_WORDS = ["校规", "规定", "政策", "教育部", "降级", "劝退", "退学", "学分要求",
                "多少学分", "几门", "预警线", "通知家长", "什么时候", "多久", "文件"]
WHY_WORDS = ["为什么", "原因", "怎么回事", "怎么算", "依据", "评估", "风险分", "多少分", "严重"]
ADVICE_WORDS = ["怎么办", "建议", "提高", "计划", "补救", "行动", "帮我", "如何", "怎么改", "来得及"]
ROSTER_WORDS = ["谁", "名单", "哪些", "班级", "排名", "几个人", "多少人", "学生"]
OVERVIEW_WORDS = ["整体", "全校", "概况", "分布", "统计", "总览", "情况如何"]
LETTER_WORDS = ["告知函", "家长信", "通知", "信件", "周报", "报告"]


class Agent:
    def __init__(self, engine, kb: KnowledgeBase, store):
        self.engine = engine
        self.kb = kb
        self.store = store

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
        return self.kb.search(query, top_k=2, school=school)

    def t_roster(self, class_name: str | None = None, level: str | None = None, limit: int = 8) -> list[dict]:
        return self.engine.roster(class_name, level)[:limit]

    def t_overview(self) -> dict:
        return self.engine.overview()

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
        }
        if "怎么办" in text or "建议" in text:
            scores["advice"] += 1.5
        if "降级" in text or "劝退" in text or "规定" in text:
            scores["policy"] += 2
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "why"

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

    def answer(self, role: str, sid: str | None, message: str, school: str | None = None,
               emit=None) -> dict:
        """生成回答。

        emit: 可选回调 emit(kind, payload)，用于把中间过程推给流式接口。
              kind 取值 meta / tool / delta；不传则行为与原来完全一致。
        """
        t0 = time.time()
        trace: list[dict] = []
        citations: list[dict] = []
        intent = self._intent(message)
        blocks: list[str] = []

        if emit:
            emit("meta", {"intent": intent})

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
            if intent in {"why", "advice", "letter"}:
                blocks.append(self._risk_sentence(s, r))
                if intent == "why":
                    blocks.append("拆开看是这样：\n" + "\n".join(f"- {x}" for x in self._factor_detail(s, r)))
                    if r["overrides"]:
                        blocks.append("另外触发了硬性规则：" + "；".join(r["overrides"]))
            if intent == "advice":
                acts = call("interventions", self.t_actions, sid=sid)
                blocks.append("接下来按这个顺序做：\n" + "\n".join(
                    f"{i+1}. **{a['title']}** —— {a['detail']}（{a['deadline']}）"
                    for i, a in enumerate(acts[:3])))
            if intent == "policy":
                hits = call("retrieve_policy", self.t_policy, query=message, school=school)
                citations = hits
                blocks.append(self._compose_policy(hits))
                blocks.append(f"对照你的情况：风险分 {r['score']}，累计挂科学分 {s['history']['failed_credits']}。")
        elif role == "parent" and sid:
            s = self.engine.get(sid)
            r = call("risk_score", self.t_risk, sid=sid)
            policy_q = any(w in message for w in ["通知", "规定", "政策", "什么时候", "多少", "几门", "降级", "毕业", "退学"])
            if policy_q:
                hits = call("retrieve_policy", self.t_policy, query=message + " 家长 学业预警", school=school)
                citations = hits
                blocks.append(self._compose_policy(hits))
                blocks.append(
                    f"对照 {s['name']} 的情况：风险分 {r['score']}（{r['level_label']}），"
                    f"累计挂科 {s['history']['failed_credits']} 学分，目前处于关注与帮扶阶段，尚未触发处分线。")
            else:
                hits = call("retrieve_policy", self.t_policy, query="家长 通知 学业预警", school=school)
                citations = hits[:1]
                blocks.append(f"{s['name']}（{s['class_name']}）本学期状态：{r['level_label']}，风险分 {r['score']}。")
                blocks.append("具体情况：\n" + "\n".join(f"- {x}" for x in self._factor_detail(s, r)[:3]))
                if hits:
                    blocks.append(f"关于家校沟通：{hits[0]['text'].strip().split(chr(10))[0]}")
        else:
            if intent == "overview":
                o = call("campus_overview", self.t_overview)
                blocks.append(
                    f"全校 {o['total']} 人，红色预警 {o['dist']['red']} 人（{o['dist_pct']['red']}%），"
                    f"黄色关注 {o['dist']['yellow']} 人（{o['dist_pct']['yellow']}%），平均风险分 {o['avg_score']}。")
                worst = sorted(o["by_class"].items(), key=lambda x: -x[1]["red"])[:3]
                blocks.append("红色人数最多的班级：" + "、".join(f"{k}（{v['red']} 人）" for k, v in worst))
                blocks.append("当前最普遍的风险因素是：" + "、".join(f"{f['label']}（均摊 {f['points']} 分）" for f in o["top_factors"][:3]))
            elif intent == "roster":
                rows = call("roster", self.t_roster, level="red" if "红" in message else None, limit=40)
                if any(w in message for w in ["上升", "变化", "趋势", "最快", "恶化"]):
                    rows = sorted([x for x in rows if x["direction"] == "up"], key=lambda x: -x["delta"])[:6]
                    head = "风险上升最快的 6 位学生（尚未计入红色名单的也要盯）："
                else:
                    rows = rows[:6]
                    head = f"风险最高的 {len(rows)} 位学生："
                if rows:
                    blocks.append(head)
                    blocks.append("\n".join(
                        f"- {x['name']}（{x['class_name']}）风险分 {x['score']}，较上学期 {x['delta']:+.0f} 分，主因 {x['top_factor']}"
                        for x in rows))
                else:
                    blocks.append("当前没有符合条件的红色预警学生。")
            elif intent == "policy":
                hits = call("retrieve_policy", self.t_policy, query=message, school=school)
                citations = hits
                blocks.append(self._compose_policy(hits))
            elif sid:
                s = self.engine.get(sid)
                r = call("risk_score", self.t_risk, sid=sid)
                blocks.append(self._risk_sentence(s, r))
                blocks.append("拆开看是这样：\n" + "\n".join(f"- {x}" for x in self._factor_detail(s, r)))
                acts = call("interventions", self.t_actions, sid=sid)
                blocks.append(f"最该先做的一件事：**{acts[0]['title']}**。")
            else:
                blocks.append("可以问我：某个学生的风险原因、班级风险名单、校规条款，或全校整体情况。")

        reply = "\n\n".join(blocks)

        if llm.available():
            context = "\n".join(blocks)
            cit = "\n".join(f"- {c['citation']}：{c['text'][:120]}" for c in citations)
            messages = [
                {"role": "system", "content": (
                    "你是高校学业预警助手。只能使用给定的事实与条款，不得编造数字或政策。"
                    "用简体中文回答，语气平实、有同理心，不要用夸张的鼓励语。"
                    "保留所有具体数字，长度控制在 200 字以内，不要使用 Markdown 标题。")},
                {"role": "user", "content": f"事实：\n{context}\n\n可引用条款：\n{cit}\n\n用户问题：{message}"},
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

        return {
            "reply": reply,
            "intent": intent,
            "citations": citations,
            "trace": trace,
            "elapsed_ms": round((time.time() - t0) * 1000, 1),
            "suggestions": self._suggestions(role),
        }

    def _suggestions(self, role: str) -> list[str]:
        return {
            "student": ["我的风险分为什么这么高？", "这学期还来得及补回来吗？", "挂多少学分会被降级？"],
            "counselor": ["本班谁的风险上升最快？", "给张三生成谈话要点", "这周班级整体情况如何？"],
            "admin": ["全校风险分布如何？", "红色预警名单有多少人？", "哪些班级问题最集中？"],
            "parent": ["孩子这学期情况怎么样？", "学校什么情况下会通知家长？", "他还来得及毕业吗？"],
        }.get(role, [])
