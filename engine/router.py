"""意图路由层：让模型自己决定「要不要取数、取哪一份」。

原来的链路是「关键词 → 拼事实 → 模板句」，模型只负责润色。
模型改不了「接下来执行什么」，所以同一个 unknown 分支会吐出同一句话。

这一层把模型放到决策位上：
    问题 → 模型判断 → ├ 需要数据：自己发起工具调用 → 结果回填 → 组织回答
                     ├ 不需要数据：直接回答（政策解释、通用建议）
                     └ 判断不了 / 调用失败：return None，上层回落规则引擎

设计上刻意保守：
- 只在规则引擎认不出意图时才进来（unknown），已知意图走原路径，零额外延迟
- 任何异常、超时、额度问题都 return None，行为和改造前一模一样
- 模型不许自己产生数字，工具返回什么就用什么
"""
from __future__ import annotations

import json
import time

from . import llm, tools as tools_mod
from .memory import memory_key

MAX_STEPS = 3          # 最多几轮工具调用，防止模型在工具里绕圈
MAX_TOOL_ARGS_ECHO = 6  # trace 里展示参数时最多保留几项

_RULES = """
## 你的工作方式

你可以调用工具取数。规则是硬的，不是建议：

1. 只要问题涉及**具体学生的成绩、考勤、作业、风险**，**名单**，**全校统计**，**学校制度条款**，
   必须先调用工具。不许凭印象回答，不许"一般来说"。
2. **数字只能来自工具返回。** 不许自己计算、不许估算、不许把工具没给的数字补上。
   工具给 71.0 你就说 71.0，不许说"约 70 分"。
3. 工具返回 ok=false 时，**如实说查不到**，把 note 里的候选名单或建议转述给用户，
   但**绝不把候选当成用户问的那个人**。例如「没找到张伟，最接近的是张玮（计科2403），是他吗？」
   **按姓名查不到时不要换别的工具再试同一个名字**——所有按姓名的工具查的是同一份学生库，
   换工具只会得到同样的结果，白等十几秒。直接问用户是哪一位。
4. 工具结果里没有的字段，就是系统里没有这项数据，直说没有，不要编一个。
5. 制度类问题回答时必须指明出自哪一条（工具会给出 citation）。
6. 如果这个问题系统确实答不了（比如问食堂几点开门），直接说明这不在系统范围内，
   并说清你能查什么。不要硬凑答案。
7. **需要多个工具时，在同一个回合里一次全部提出**（比如同时要成绩、考勤、作业，
   就一次给出三个 tool_calls）。分三轮问会多花两轮等待，用户要干等十几秒。

## 回答风格

- 中文。先给结论，再给依据。控制在 3 段以内，不要长篇。
- 有多个数字时用「- 」列点，数字带单位（分、次、人、%）。
- 不要用 Markdown 标题（#），不要写"作为AI"这类开场。
- 不确定的地方反问一句，比硬答更有用。
"""


def _identity(agent, role: str, sid: str | None, profile: dict | None) -> str:
    """本轮是谁在问。学生/家长直接给姓名，模型就不用反复查"我"。"""
    p = profile or {}
    if role in ("student", "parent") and sid:
        try:
            s = agent.engine.get(sid)
            who = "家长" if role == "parent" else "学生本人"
            return (f"\n## 当前会话身份\n"
                    f"对方的身份是{who}，学生是 **{s['name']}**（{s['class_name']}，学号 {s['id']}）。"
                    f"问「我」的时候指的就是这位，直接用工具查他/她即可。\n")
        except KeyError:
            return ""
    if role == "teacher":
        name = p.get("name") or p.get("teacher") or ""
        return (f"\n## 当前会话身份\n任课教师 **{name}**。只能谈论他/她自己任教的课程和学生，"
                f"不涉及其他教师或其他班级。\n")
    if role == "counselor":
        return "\n## 当前会话身份\n辅导员，可以查看全校任何学生的数据，但没有修改规则的权限。\n"
    if role == "admin":
        return "\n## 当前会话身份\n教务管理员，可以查看全校数据与规则配置。\n"
    return ""


def _history(agent, mkey: str | None) -> list[dict]:
    """最近两轮问答作为上下文，让「他」「这个人」能接上。"""
    if not (mkey and agent.memory):
        return []
    out: list[dict] = []
    for turn in agent.memory.history(mkey)[-2:]:
        if turn.get("message"):
            out.append({"role": "user", "content": turn["message"][:120]})
        if turn.get("reply"):
            out.append({"role": "assistant", "content": turn["reply"][:300]})
    return out


def _prefetch(agent, role: str, sid: str | None, message: str,
              teacher_name: str) -> tuple[str, list[dict], list[str]]:
    """问题里点了名，就先把这名学生的数据取好放进提示词。

    为什么值得做：一次工具决策要等模型 5 秒左右，而"某某这学期怎么样"是最高频的问法。
    姓名匹配是确定性的（库里就那么几个名字），先查好直接给它，
    模型看到数据够了就会一轮答完，省掉一整轮往返。

    返回 (提示词片段, trace 条目, 已用工具名)。
    """
    if role not in ("counselor", "admin", "teacher"):
        return "", [], []
    names: dict = getattr(agent, "_names", None) or {}
    hit = ""
    for n in names:
        # 最长匹配：避免「李明」吃掉「李明轩」
        if n and n in message and len(n) > len(hit):
            hit = n
    if not hit:
        return "", [], []

    blocks: list[str] = []
    trace: list[dict] = []
    used: list[str] = []
    for tool_name in ("get_student", "get_attendance", "get_homework"):
        result = tools_mod.run(agent, role, sid, tool_name, {"name": hit}, teacher_name)
        if result.get("ok"):
            blocks.append(f"### {tool_name}\n{tools_mod.render(result)}")
            trace.append({"tool": tool_name, "args": {"name": hit}, "ms": 0.0,
                          "ok": True, "prefetch": True})
            used.append(tool_name)
        elif tool_name == "get_student":
            # 连学生都查不到，后面的考勤作业一定也是空的，直接收手
            break

    if not blocks:
        return "", [], []

    body = "\n\n".join(blocks)
    if len(body) > 3200:                      # 防止把上下文撑爆，尾部截断并注明
        body = body[:3200] + "\n…（数据过长，已截断）"
    head = (f"\n## 已预先查到的数据\n提问里提到的学生是 **{hit}**，下面这些数据"
            f"**已经在提问前查好了**，不需要再调用工具。\n"
            f"如果这些够回答问题，直接作答即可。\n\n{body}\n")
    return head, trace, used


def route(agent, role: str, sid: str | None, message: str, school: str | None = None,
          profile: dict | None = None, emit=None) -> dict | None:
    """尝试用模型回答。成功返回和 Agent.answer() 同结构的 dict；放弃则返回 None。"""
    if not llm.available():
        return None

    t0 = time.time()
    trace: list[dict] = []
    thoughts: list[str] = []
    citations: list[dict] = []
    used_tools: list[str] = []

    def think(text: str) -> None:
        thoughts.append(text)
        if emit:
            emit("thought", {"text": text})

    think("这个问题规则引擎没认出来，交给模型判断该查什么。")

    persona = ""
    try:
        from .agent import PERSONAS
        persona = PERSONAS.get(role, PERSONAS.get("admin", ""))
    except Exception:  # noqa: BLE001
        pass

    system = f"{persona}\n{_RULES}\n{_identity(agent, role, sid, profile)}".strip()
    mkey = memory_key(profile) if (profile and agent.memory) else None
    teacher_name = (profile or {}).get("name") or (profile or {}).get("teacher") or ""

    # 点名提问是最高频场景：先把这名学生的数据查好塞进去，省掉一轮模型往返（约 5 秒）
    pre_text, pre_trace, pre_used = _prefetch(agent, role, sid, message, teacher_name)
    if pre_text:
        system += pre_text
        trace.extend(pre_trace)
        used_tools.extend(pre_used)
        for item in pre_trace:
            if emit:
                emit("tool", item)
        think(f"问题里提到了 {pre_trace[0]['args']['name']}，已直接取好数据（免一轮判断）。")

    msgs: list[dict] = [{"role": "system", "content": system}]
    msgs.extend(_history(agent, mkey))
    msgs.append({"role": "user", "content": message})

    specs = tools_mod.specs_for(role)
    reply = ""
    force_final = False

    # ---- 流式：先把开头几个字压住不放 ----
    # 模型两种产出：① 直接作答（该边说边显示）② 先调工具（此时不该往屏幕上写字）。
    # 这两种在流结束前分不出来，所以压住前 KEEP 个字符：够长就说明它在写长答案，
    # 开始实时放；如果最后拿到的是 tool_calls，缓冲的那些直接丢掉，用户什么都没看到。
    KEEP = 80
    pending: list[str] = []
    flushing = False
    started = False          # 模型偶尔先用几个空行开路，直接显示会在气泡顶部留白

    def on_delta(piece: str) -> None:
        nonlocal flushing, started
        if flushing:
            if emit:
                emit("delta", {"text": piece})
            return
        pending.append(piece)
        text = "".join(pending)
        if not started:
            text = text.lstrip()
            if not text:
                pending.clear()
                return
        if len(text) >= KEEP:
            flushing = True
            started = True
            if emit:
                emit("delta", {"text": text})
            pending.clear()

    for step in range(MAX_STEPS + 1):
        last = step == MAX_STEPS or force_final
        pending.clear()
        flushing = False
        started = False
        # 最后一轮把工具摘掉，逼它用已有信息作答，避免无限调用
        # 决策轮用快模型（LLM_ROUTE_MODEL），收尾轮用主模型——决策只要准，作答才要好听
        r = llm.stream_tools(
            msgs, [] if last else specs, on_delta=on_delta,
            model=None if last else (llm.route_model() or None),
        )
        if r is None:
            think("模型调用失败，回落到规则引擎。")
            return None

        calls = r["tool_calls"]
        if calls and not last:
            # 这一轮其实是在调工具，之前抢跑出去的正文要作废（正常情况没有）
            if flushing:
                think("（模型先说了半句再决定查数据，已切到取数）")
            # 把这一轮的工具调用原样回填，否则下一轮模型看不见自己刚才要过什么
            msgs.append({
                "role": "assistant",
                "content": "" if flushing else (r["content"] or None),
                "tool_calls": [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["function"]["name"],
                                  "arguments": c["function"].get("arguments") or "{}"}}
                    for c in calls
                ],
            })
            for c in calls:
                name = c["function"]["name"]
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                    if not isinstance(args, dict):
                        args = {}
                except json.JSONDecodeError:
                    args = {}
                start = time.time()
                result = tools_mod.run(agent, role, sid, name, args, teacher_name)
                item = {
                    "tool": name,
                    "args": dict(list(args.items())[:MAX_TOOL_ARGS_ECHO]),
                    "ms": round((time.time() - start) * 1000, 1),
                    "ok": bool(result.get("ok")),
                }
                trace.append(item)
                used_tools.append(name)
                if emit:
                    emit("tool", item)
                if name == "search_policy" and result.get("ok"):
                    for hit in (result.get("data") or {}).get("条款") or []:
                        citations.append({
                            "citation": hit.get("出处"),
                            "text": hit.get("原文", ""),
                            "school": hit.get("学校"),
                        })
                msgs.append({
                    "role": "tool",
                    "tool_call_id": c["id"],
                    "content": tools_mod.render(result),
                })
                # 姓名查不到就别让它换工具重试了：所有按姓名的工具查的是同一份
                # 学生库，再试只会多花十几秒、结论一模一样。
                note = str(result.get("note") or "")
                if result.get("ok") is False and ("没有找到叫" in note or "学生库（" in note):
                    force_final = True
            continue

        reply = r["content"]
        # 这里**不要**把 r["reasoning"] 直接显示到「思考过程」里。
        # 那是模型的原始思维链，里面会出现「根据工具描述…」「我注意到…」这类
        # 内部独白，用户看了像在看调试日志。真正该给用户看的是「查了什么、查到了什么」，
        # 那部分已经由 trace 和上面的 think() 表达过了。
        break

    reply = (reply or "").strip()
    if not reply:
        think("模型没有给出有效回答，回落到规则引擎。")
        return None

    # 短回答（不足 KEEP 字）还没放出去：这里一次性补发，保证前端拿到的增量拼起来等于全文
    if pending and emit:
        tail = "".join(pending)
        emit("delta", {"text": tail if started else tail.lstrip()})
        pending.clear()

    if mkey and agent.memory:
        agent.memory.append(mkey, {
            "message": message[:200],
            "reply": reply[:400],
            "sid": sid,
            "intent": "llm_route",
            "roster": None,
        })

    think(f"走的是模型路由，调用工具 {len(used_tools)} 次"
          + (f"（{'、'.join(used_tools)}）" if used_tools else "（未取数，直接答）") + "。")

    return {
        "reply": reply,
        "intent": "llm_route" if not used_tools else "llm_tool",
        "citations": citations,
        "trace": trace,
        "thoughts": thoughts,
        "elapsed_ms": round((time.time() - t0) * 1000, 1),
        "suggestions": agent._suggestions(role, "", sid),
    }
