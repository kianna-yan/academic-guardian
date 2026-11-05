"""Skill 被点选的那一轮：回答由技能自己组织，不再交给意图猜测。

问题背景
「+ → Skill」的提问是**系统预填**的，不是用户自己组织的话。以前它和普通提问走同一条
链路，先过 `agent._intent` 的关键词打分：学生端的「补救计划」能命中 advice，导员端同一
句话却什么都没命中，于是落进兜底话术——截图上那条「规则引擎没认出来 / 模型调用失败」
就是这么来的。同一个技能在五个端生成同一套学生口吻的文案，是设计上的错位，不是措辞问题。

这里的做法
1. 技能自带回答：文件类技能按「本端能看到的数据范围」写摘要，和生成的文件同源；
2. 文书辅助：给「自动带出了什么、还差哪几项、走哪条签批链」，并写明只起草不提交；
3. 家校沟通：进入角色扮演，家长说的每个数字都来自学情库；
4. 记忆：演练状态随会话记忆走，下一轮不看技能参数也能接上。
"""
from __future__ import annotations

import time
from datetime import datetime

from engine import documents, family, skills
from engine.memory import memory_key

ROLE_LABEL = {
    "student": "学生端",
    "parent": "家长端",
    "counselor": "辅导员端",
    "admin": "教务端",
    "teacher": "教师端",
}

FILE_SKILLS = {"ppt", "pdf", "word"}
REVIEW_WORDS = ("复盘", "结束演练", "结束模拟", "不练了", "总结一下这场", "这场沟通怎么样")


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _trace(tool: str, args: dict, detail: str, rows: int = 1) -> dict:
    return {
        "tool": tool,
        "args": args,
        "ms": 0.4,
        "evidence": {
            "source": "学情库",
            "table": detail,
            "rows": rows,
            "unit": "条",
            "ts": time.strftime("%H:%M:%S"),
            "ms": 0.4,
            "detail": detail,
        },
    }


def _result(reply: str, intent: str, trace: list[dict], suggestions: list[str],
            t0: float, citations: list[dict] | None = None,
            thoughts: list[str] | None = None) -> dict:
    """与 agent.answer 的返回结构保持一致，接口层不用为技能单开分支。"""
    return {
        "reply": reply,
        "intent": intent,
        "citations": citations or [],
        "trace": trace,
        "thoughts": thoughts or [],
        "action": None,
        "elapsed_ms": round((time.time() - t0) * 1000, 1),
        "suggestions": suggestions,
    }


def _think(emit, bag: list[str], text: str) -> None:
    """思考链：既进返回体（非流式接口要用），也推给前端（流式实时显示）。"""
    bag.append(text)
    if emit:
        emit("thought", {"text": text})


def _emit_tool(emit, item: dict) -> None:
    if emit:
        emit("tool", item)


def _remember(agent, profile: dict, message: str, reply: str, sid: str | None,
              intent: str, family_state: dict | None = None) -> None:
    """写会话记忆。演练状态就挂在「上一轮」上，不用另开存储。"""
    if not (getattr(agent, "memory", None) and profile):
        return
    turn = {"message": (message or "")[:200], "reply": reply[:400], "sid": sid,
            "intent": intent, "roster": None}
    if family_state:
        turn["family"] = family_state
    agent.memory.append(memory_key(profile), turn)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def answer(agent, role: str, sid: str | None, message: str, school: str | None,
           profile: dict | None, emit=None, skill: str | None = None,
           sub: str | None = None) -> dict | None:
    """skill 有值就按技能答；否则看上一轮是不是在演练里，是就接着演。"""
    t0 = time.time()
    profile = profile or {}

    if skill == "family" or (not skill and _running(agent, profile, role)):
        return _family(agent, role, sid, message, profile, emit, t0, sub, start=bool(skill))
    if skill == "doc":
        return _doc(agent, role, sid, message, profile, emit, t0, sub)
    if skill in FILE_SKILLS:
        return _file(agent, role, sid, profile, emit, t0, skill)
    return None


def _running(agent, profile: dict, role: str) -> bool:
    if role not in ("counselor", "admin") or not getattr(agent, "memory", None):
        return False
    hist = agent.memory.history(memory_key(profile))
    return bool(hist and hist[-1].get("family"))


# ---------------------------------------------------------------------------
# 文件类：PPT / PDF / Word
# ---------------------------------------------------------------------------
def _file(agent, role: str, sid: str | None, profile: dict, emit, t0: float, key: str) -> dict:
    meta = skills.BY_KEY[key]
    name = meta["name"].replace(" 生成", "")
    thoughts: list[str] = []
    trace: list[dict] = []
    citations: list[dict] = []

    if role in ("student", "parent") and sid:
        b = skills.brief(agent.engine, sid)
        rk = b["risk"]
        _think(emit, thoughts, f"点了「{meta['name']}」：按 {b['name']} 的当前学情现场排版，"
                               f"回答和文件用同一份数据。")
        # 称呼跟着端走：学生端用「你」，家长端说「孩子」，别把名字硬塞进正文
        owner = "你" if role == "student" else "孩子"
        lines = [f"**《{skills.filename(key, b)}》已生成**", "",
                 f"这份{name}讲的是{owner}这学期的整体情况，核心是三件事：", ""]
        delta = rk.get("delta")
        lines.append(f"- 风险 {rk['score']} 分（{rk['level_label']}）"
                     + (f"，较上学期 {delta:+.0f} 分" if isinstance(delta, (int, float)) else ""))
        if rk["factors"]:
            lines.append("- 主要来自：" + "、".join(
                f"{f['label']}（{f['points']} 分）" for f in rk["factors"][:3]))
        steps = b["advice"]["steps"] or []
        if steps:
            lines.append(f"- 下一步先做：{steps[0]}")
        lines += ["", "文件在下方，点「下载」保存到本机；要换口径（只讲课程、只讲考勤）直接说。"]
        citations.append({
            "kind": "data",
            "citation": f"学情快照 · 风险 {rk['score']} 分（{rk['level_label']}）",
            "source": "students 表 · risk_score() 六因素加权",
            "text": "、".join(f"{f['label']} {f['points']} 分" for f in rk["factors"][:3])
                    or "本学期暂无课程成绩",
        })
        trace.append(_trace("skill_render",
                            {"skill": key, "sid": sid, "note": f"按 {b['name']} 的学情渲染{name}"},
                            f"{b['name']} · 学情聚合", len(b["courses"])))
        suggestions = _file_chips(role)
    else:
        o = agent.engine.overview()
        dist = o.get("dist") or {}
        pct = o.get("dist_pct") or {}
        _think(emit, thoughts, f"点了「{meta['name']}」：导员/教务没有单个学生的语境，"
                               f"导出的是全校口径，回答也按全校说，不套学生话术。")
        lines = [f"**《{_class_filename(key)}》已生成**", "",
                 f"这是全校口径（当前登录：{ROLE_LABEL.get(role, role)}），"
                 f"在册 {o.get('total')} 人：", ""]
        lines.append(f"- 红色预警 {dist.get('red', 0)} 人（{pct.get('red', 0)}%）、"
                     f"黄色关注 {dist.get('yellow', 0)} 人（{pct.get('yellow', 0)}%）")
        worst = sorted((o.get("by_class") or {}).items(), key=lambda kv: -kv[1]["red"])[:2]
        if worst:
            lines.append("- 红预警最集中：" + "、".join(f"{k}（{v['red']} 人）" for k, v in worst))
        if o.get("top_factors"):
            lines.append("- 最普遍的风险因素：" + "、".join(
                f"{f['label']}（均摊 {f['points']} 分）" for f in o["top_factors"][:3]))
        lines += ["", "文件在下方，可直接投屏或打印；点名要某个学生的那份，说名字我另出一份。"]
        citations.append({
            "kind": "data",
            "citation": f"全校概览 · {o.get('total')} 名在册学生",
            "source": "students 表 · 全校分布统计",
            "text": f"红 {dist.get('red', 0)} 人、黄 {dist.get('yellow', 0)} 人、绿 {dist.get('green', 0)} 人；"
                    f"人均风险分 {o.get('avg_score')}。",
        })
        trace.append(_trace("skill_render",
                            {"skill": key, "scope": "全校", "note": f"按全校口径渲染{name}"},
                            "students 表 · 全校分布", o.get("total") or 0))
        suggestions = _file_chips(role)

    reply = "\n".join(lines)
    _emit_tool(emit, trace[0])
    _remember(agent, profile, "", reply, sid, "skill")
    return _result(reply, "skill", trace, suggestions, t0, citations, thoughts)


def _class_filename(key: str) -> str:
    day = datetime.now().strftime("%Y%m%d")
    return {"ppt": f"学业预警学期汇报_{day}.pptx",
            "pdf": f"每日预警日报_{day}.pdf",
            "word": f"每日预警日报_{day}.docx"}[key]


def _file_chips(role: str) -> list[str]:
    if role == "student":
        return ["我该先做哪件事", "我的成绩是在涨还是在掉", "导出我的告知函"]
    if role == "parent":
        return ["孩子的成绩趋势怎么样", "学校什么情况下会通知家长", "导出家长信"]
    if role == "counselor":
        return ["本班谁的风险最高", "给他生成谈话要点", "今日日报说了什么"]
    return ["全校风险分布如何", "今日日报说了什么", "导出学期汇报 PPT"]


# ---------------------------------------------------------------------------
# 文书辅助
# ---------------------------------------------------------------------------
def _doc(agent, role: str, sid: str | None, message: str, profile: dict, emit,
         t0: float, sub: str | None) -> dict:
    if role in ("student", "parent"):
        reply = ("文书辅助是给教务和辅导员用的：这些表格要学院和教务处签批，"
                 "学生自己填的那部分，学院会发纸质表格。")
        return _result(reply, "doc", [], [], t0)

    key = sub if sub in documents.BY_KEY else documents.KINDS[0]["key"]
    meta = documents.BY_KEY[key]
    thoughts: list[str] = []

    # 导员/教务没有固定学生：消息里点了名就用那位，没点名就留空，不硬塞一个
    target = sid
    try:
        named, _ = agent.resolve_target(message or "", role, sid, None)
        target = named or sid
    except Exception:  # noqa: BLE001 - 点不出人不是错误，照常起草
        target = sid
    if key not in documents.STUDENT_KINDS:
        target = None

    ctx = documents.context(agent.engine, target, profile, message)
    b = documents.brief(key, ctx)
    _think(emit, thoughts, f"文书辅助：按《{meta['name']}》模板起草。"
                           f"能自动填的从学情库取，只有人知道的一律留【待填】，不猜日期和事由。")

    lines = [f"**《{b['file']}》已起草（草稿）**", ""]
    if b["auto"]:
        lines += ["已经从学情库带出：", ""]
        lines += [f"- {k}：{v}" for k, v in b["auto"]]
        lines.append("")
    else:
        lines += ["这一份不涉及具体学生（通知、纪要通常如此），落款人按当前账号填。", ""]

    lines += [f"还需要人工补 {len(b['blank'])} 处（文档里标成【待填：…】）：", ""]
    lines += [f"{i}. {x}" for i, x in enumerate(b["blank"], 1)]
    lines += ["", f"签批链：{' → '.join(b['flow'])}", ""]
    if meta.get("tip"):
        lines += [f"> {meta['tip']}", ""]
    lines += ["**只起草，不代提交**：系统里没有教务提交接口，这份文件也没有进入任何业务系统。"
              "正式办理请人工审核、签字盖章后走学校流程。", "",
              "文件在下方，点「下载」拿到 .docx；要换一类文书，重新点 Skill 里的「文书辅助」。"]
    if key in documents.STUDENT_KINDS and not target:
        lines += ["", "（要自动带出姓名学号，说「给沈一鸣起草一份休学申请」这样带上名字。）"]

    reply = "\n".join(lines)
    trace = [_trace("doc_draft", {"kind": key, "sid": target,
                                  "note": f"按模板起草《{meta['name']}》"},
                    f"documents · {meta['name']} 模板", 1)]
    _emit_tool(emit, trace[0])
    _remember(agent, profile, message, reply, target, "doc")
    return _result(reply, "doc", trace, [], t0, thoughts=thoughts)


# ---------------------------------------------------------------------------
# 家校沟通：角色扮演
# ---------------------------------------------------------------------------
def _family(agent, role: str, sid: str | None, message: str, profile: dict, emit,
            t0: float, kind: str | None, start: bool) -> dict:
    if role not in ("counselor", "admin"):
        reply = ("家校沟通演练是给辅导员和教务用的：模拟家长、练话术。"
                 "学生端和家长端不开放——真家长不该被系统「演」一遍。")
        return _result(reply, "family", [], [], t0)

    thoughts: list[str] = []
    hist = agent.memory.history(memory_key(profile)) if getattr(agent, "memory", None) else []
    state = (hist[-1].get("family") if hist else None) or {}

    if start:
        k = kind if kind in family.BY_KEY else family.PARENTS[0]["key"]
        target = _pick_student(agent, sid, message)
        ctx = family.student_ctx(agent.engine, target)
        p = family.BY_KEY[k]
        _think(emit, thoughts, f"进入家校沟通演练：扮演{p['name']}，"
                               f"事实取自 {ctx['name']} 的学情（风险 {ctx['score']} 分）。")
        text = family.opening(k, ctx)
        trace = [_trace("family_sim",
                        {"parent": k, "sid": target,
                         "note": f"扮演{p['name']}：按共情/事实/方案/边界四类动作给反馈"},
                        f"{ctx['name']} · 学情快照", 1)]
        _emit_tool(emit, trace[0])
        _remember(agent, profile, message, text, target, "family",
                  {"kind": k, "sid": target, "turn": 1, "moves": []})
        return _result(text, "family", trace, family.opening_chips(k, ctx), t0, thoughts=thoughts)

    if not state:
        reply = "先点 Skill 里的「家校沟通」，选一类家长，我们从头开始演练。"
        return _result(reply, "family", [], [], t0)

    k = state.get("kind") or family.PARENTS[0]["key"]
    target = state.get("sid") or _pick_student(agent, sid, message)
    ctx = family.student_ctx(agent.engine, target)
    turn = int(state.get("turn") or 1) + 1
    moves = list(state.get("moves") or [])

    if any(w in (message or "") for w in REVIEW_WORDS):
        text = family.review(k, ctx, moves, turn - 1)
        _think(emit, thoughts, f"演练收尾：按覆盖到的动作给复盘，事实底子用 {ctx['name']} 的真实数据。")
        trace = [_trace("family_review",
                        {"parent": k, "sid": target, "turns": turn - 1,
                         "note": "复盘：覆盖了哪几个关键动作、漏了什么"},
                        "family · 动作覆盖统计", turn - 1)]
        _emit_tool(emit, trace[0])
        _remember(agent, profile, message, text, target, "family", None)
        return _result(text, "family", trace, _file_chips("counselor"), t0, thoughts=thoughts)

    r = family.reply(k, message or "", ctx, turn, moves, state.get("last"))
    _think(emit, thoughts, f"这句话里识别到「{_move_label(r['move'])}」。按{p_label(k)}的反应往下演。")
    trace = [_trace("family_sim",
                    {"parent": k, "turn": turn, "move": r["move"],
                     "note": f"第 {turn} 轮：家长按「{_move_label(r['move'])}」反应"},
                    "family · 对话动作识别", 1)]
    _emit_tool(emit, trace[0])
    _remember(agent, profile, message, r["text"], target, "family",
              {"kind": k, "sid": target, "turn": turn, "moves": r["moves"], "last": r["move"]})
    return _result(r["text"], "family", trace, r["suggestions"], t0, thoughts=thoughts)


def _move_label(move: str) -> str:
    return family.MOVE_LABEL.get(move, "对话")


def p_label(kind: str) -> str:
    return family.BY_KEY[kind]["name"]


def _pick_student(agent, sid: str | None, message: str) -> str:
    """演练要有具体学情才像真的：点了名用那位，没点名就拿红色预警里风险最高的。"""
    if sid:
        return sid
    try:
        named, _ = agent.resolve_target(message or "", "counselor", None, None)
        if named:
            return named
    except Exception:  # noqa: BLE001
        pass
    rows = agent.engine.roster()
    red = [x for x in rows if x.get("level") == "red"]
    return (red or rows)[0]["id"]
