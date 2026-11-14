"""数字溯源率评测：回答里出现的每一个数值，能不能在**本次**工具返回里找到。

为什么要单独一个脚本：
    「回答中数字可溯源率 100%」如果只是一句断言，评委会问「怎么证明」。
    这个脚本把「溯源」变成可执行的定义——

        回答中的每一个数值，都能在本次对话的工具返回（含证据链元数据）里
        找到同值或四舍五入后同值的来源。

    做法：把 engine.tools.run 包一层，抓下每次工具调用的**原始返回**，
    再把模型回答里的数字逐个回查。查不到的打出来，人工看是模型自己算的
    （该改 prompt）、还是格式误差（该放宽匹配）。

用法（在项目根目录，需要 .env 里的 key）：
    python tests/number_trace.py                # 全部用例
    python tests/number_trace.py --only 取数     # 只跑取数题
    python tests/number_trace.py --limit 3      # 先跑 3 条看看
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import engine  # noqa: E402  载入 .env
from engine import data, llm, rag, tools as tools_mod  # noqa: E402
from engine.agent import Agent  # noqa: E402
from engine.memory import ConversationMemory  # noqa: E402
from engine.risk import RiskEngine  # noqa: E402

from chat_eval import CASES  # noqa: E402  复用同一套用例，口径不分裂

# 回答里的数字：整数或小数。前面不能紧贴字母/数字（避免把 2401 从「计科2401」里
# 单独切出来当成一个待查数字——它作为整体仍然会去工具返回里比对）。
NUM_RE = re.compile(r"(?<![A-Za-z0-9.])\d+(?:\.\d+)?")


def _num_texts(obj, out: set[str]) -> None:
    """把任意工具返回递归摊平成「可能出现在回答里的数字字符串」。"""
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.add(str(obj))
        out.add(f"{obj:g}")
        out.add(f"{obj:.1f}")
        if float(obj).is_integer():
            out.add(str(int(obj)))
        out.add(f"{obj * 100:.1f}")   # 0.688 → 68.8（模型常把比例写成百分数）
        out.add(f"{obj * 100:g}")
        return
    if isinstance(obj, str):
        out.add(obj)
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _num_texts(v, out)
        return
    if isinstance(obj, (list, tuple)):
        for v in obj:
            _num_texts(v, out)


def _hit(token: str, pool: set[str], blob: str) -> bool:
    """一个数字算不算可溯源：同值 / 四舍五入同值 / 在返回原文里出现过。"""
    if token in pool:
        return True
    try:
        v = float(token)
    except ValueError:
        return False
    if token in blob:
        return True
    for s in pool:
        try:
            w = float(s)
        except ValueError:
            continue
        if abs(w - v) <= 0.051 or abs(w * 100 - v) <= 0.5 or abs(w / 100 - v) <= 0.005:
            return True
    return False


def _profile(role: str, acc: str) -> tuple[dict, str | None]:
    """和 chat_eval 一样的登录态构造，保证两边问的是同一个身份。"""
    if role == "teacher":
        tmap = {v["employee_id"]: v for v in data.db()["teachers"].values()}
        return {"role": "teacher", "account": acc,
                "name": tmap.get(acc, {}).get("name", ""), "sid": None}, None
    if role in ("student", "parent"):
        return {"role": role, "account": acc, "name": "", "sid": acc}, acc
    names = {"counselor": "陈静", "admin": "教务管理员"}
    return {"role": role, "account": acc, "name": names.get(role, ""), "sid": None}, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["取数", "通用", "边界", "成绩", "课表"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--grep", default="", help="只跑问题里含该字样的用例（改完问题定向复查用）")
    args = ap.parse_args()

    cases = [c for c in CASES if not args.only or c["kind"] == args.only]
    if args.grep:
        cases = [c for c in cases if args.grep in c["q"]]
    if args.limit:
        cases = cases[: args.limit]

    captured: list[dict] = []
    derived: list = []          # 引擎方法的返回值（规则链路不经过 tools.run，走这里）
    ctx: list = []              # 真正下发给模型的消息（模型看到的数字才算「有出处」）
    real_run = tools_mod.run

    def wrap_llm(fn):
        def wrapper(messages, *a, **kw):
            ctx.append(messages)
            return fn(messages, *a, **kw)

        return wrapper

    real_llm = {k: getattr(llm, k) for k in ("chat", "chat_stream", "chat_tools", "stream_tools")}
    for k, fn in real_llm.items():
        setattr(llm, k, wrap_llm(fn))

    def spy_run(agent, role, sid, name, cargs, teacher_name="", profile=None):
        res = real_run(agent, role, sid, name, cargs, teacher_name, profile)
        captured.append({"tool": name, "args": cargs, "result": res})
        return res

    tools_mod.run = spy_run  # 只在本次进程内生效，不动产品代码

    def spy(obj, sink):
        """把对象的方法调用结果记下来。

        规则链路（「谁最危险」这类）不经过 tools.run，直接调 RiskEngine 的方法，
        但那些返回值同样是可溯源的出处——所以这里连引擎一起记。
        """
        class _Spy:
            def __getattr__(self, key):
                val = getattr(obj, key)
                if not callable(val):
                    return val

                def wrapper(*a, **kw):
                    out = val(*a, **kw)
                    sink.append(out)
                    return out

                return wrapper

        return _Spy()

    # 只记引擎与工具算出来的值，不把整张库表塞进数字池——
    # 否则「别的学生的分数」也能给错答案背书，这个指标就失去意义了。
    risk = RiskEngine(data.db())
    agent = Agent(spy(risk, derived), rag.KnowledgeBase(), None,
                  memory=ConversationMemory())

    total_nums = traced_nums = 0
    case_rows = []

    try:
        for i, c in enumerate(cases, 1):
            captured.clear()
            derived.clear()
            ctx.clear()
            prof, sid = _profile(c["role"], c["acc"])
            t0 = time.time()
            try:
                r = agent.answer(c["role"], sid, c["q"], None, profile=prof)
            except Exception as exc:  # noqa: BLE001
                print(f"{i:2d}. [ERR ] {c['q']}  ← {exc}")
                continue
            el = time.time() - t0
            reply = (r.get("reply") or "").strip()

            # 数字池 = 工具原始返回 + 引擎/数据表返回值 + 轨迹里的证据链元数据
            pool: set[str] = set()
            for item in captured:
                _num_texts(item["result"], pool)
            for v in derived:
                _num_texts(v, pool)
            for t in r.get("trace") or []:
                _num_texts(t, pool)
            for msgs in ctx:
                _num_texts(msgs, pool)
            blob = json.dumps(captured, ensure_ascii=False, default=str) + \
                json.dumps(derived, ensure_ascii=False, default=str) + \
                json.dumps(r.get("trace") or [], ensure_ascii=False, default=str) + \
                json.dumps(ctx, ensure_ascii=False, default=str)

            tokens = NUM_RE.findall(reply)
            miss = [t for t in tokens if not _hit(t, pool, blob)]
            total_nums += len(tokens)
            traced_nums += len(tokens) - len(miss)
            rate = (len(tokens) - len(miss)) / len(tokens) * 100 if tokens else 100.0
            mark = "OK  " if not miss else "MISS"
            print(f"{i:2d}. [{mark}] {c['q']}   {len(tokens)} 个数字 / 未溯源 {len(miss)}"
                  f"   {el:.1f}s   工具 {[x['tool'] for x in captured]}")
            if miss:
                print(f"      未溯源：{miss}")
                print(f"      回答：{reply[:200].replace(chr(10), ' / ')}")
            case_rows.append((c["q"], len(tokens), len(miss), rate))
    finally:
        tools_mod.run = real_run
        for k, fn in real_llm.items():
            setattr(llm, k, fn)

    print("\n" + "=" * 66)
    if total_nums:
        print(f"数字总数 {total_nums}   可溯源 {traced_nums}   "
              f"溯源率 {traced_nums / total_nums * 100:.2f}%")
    else:
        print("这些用例的回答里没有数字")
    clean = sum(1 for _, _, m, _ in case_rows if m == 0)
    print(f"全部数字可溯源的回答 {clean}/{len(case_rows)} 条")
    return 0 if traced_nums == total_nums else 1


if __name__ == "__main__":
    raise SystemExit(main())
