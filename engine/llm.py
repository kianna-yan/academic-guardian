"""大模型接入层（可选）。

没有配置 key 时 available() 返回 False，上层自动降级为规则引擎；
配置任意 OpenAI 兼容服务（智谱 GLM / DeepSeek / 通义 / Kimi / vLLM 等）即可开启。

对外四件事：
- available()   —— 是否可用（key + 开关）
- chat()        —— 一次性生成
- chat_stream() —— 流式生成
- chat_tools()  —— 带 tools 的一次调用，返回原始 message（含 tool_calls）

配置在调用时实时读取 os.environ，不再锁在模块常量里——这样 .env 后加载、
或者运行期改配置都能生效。模块级的 llm.MODEL / llm.BASE_URL 通过
__getattr__ 保持兼容（agent.py 的 trace 里在用）。
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request

DEFAULT_BASE = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"

# ---- 运行期健康状态 ----------------------------------------------------
# 给前端顶部黄条用：一次调用真失败就置 False，下一次成功再自动置回 True。
# 之所以要记这个，是因为失败会被上层静默吞掉、回落规则引擎作答——
# 页面看着正常，只是措辞变生硬，不主动提示的话没人知道大模型已经掉线了。
HEALTH: dict = {"ok": True, "reason": "", "at": 0.0, "fails": 0}
_HEALTH_LOCK = threading.Lock()


def _fail_reason(err) -> str:
    """把异常翻成一句人能看懂的原因，前端黄条直接显示。"""
    if isinstance(err, urllib.error.HTTPError):
        try:
            raw = err.read().decode("utf-8", "ignore")[:160]
        except OSError:
            raw = ""
        if err.code in (401, 403):
            return f"密钥无效或权限不足（HTTP {err.code}）"
        if err.code == 429:
            return "额度已用尽或频率超限（HTTP 429）"
        if err.code >= 500:
            return f"模型服务端异常（HTTP {err.code}）"
        return f"调用被拒（HTTP {err.code}）" + (f" {raw}" if raw else "")
    return "网络不可达或响应异常"


def _mark_fail(err) -> None:
    reason = _fail_reason(err)
    with _HEALTH_LOCK:
        HEALTH["ok"] = False
        HEALTH["reason"] = reason
        HEALTH["at"] = time.time()
        HEALTH["fails"] += 1


def _mark_ok() -> None:
    with _HEALTH_LOCK:
        if not HEALTH["ok"]:
            HEALTH["ok"] = True
            HEALTH["reason"] = ""
            HEALTH["at"] = time.time()


def health() -> dict:
    """前端黄条要的状态。enabled=False 表示压根没配 key，永远走规则引擎。"""
    with _HEALTH_LOCK:
        snap = dict(HEALTH)
    snap["enabled"] = available()
    snap["model"] = _model()
    snap["route_model"] = route_model() or _model()
    snap["checked_at"] = time.strftime("%H:%M:%S", time.localtime(snap["at"])) if snap["at"] else ""
    if not snap["enabled"]:
        snap["ok"] = False
        snap["reason"] = "未配置大模型（LLM_API_KEY 为空）"
    return snap


def _base_url() -> str:
    return os.getenv("LLM_BASE_URL", DEFAULT_BASE).rstrip("/")


def _api_key() -> str:
    return os.getenv("LLM_API_KEY", "").strip()


def _model() -> str:
    return os.getenv("LLM_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _thinking() -> str:
    """思考档位：low / high / max，空字符串表示不传该参数。

    GLM-5.3-Flash 这类推理模型「始终思考」，不支持 type=disabled
    （会返回 1210 错误），只能调档，不能关。

    ⚠️ 实测出来的坑：这个参数**只在请求带 tools 时才被接受**。
    同一个 thinking={"type":"low"}，带 tools 返回 200，不带 tools 返回
    400 / 1210「该模型始终思考，不支持关闭思考」。所以 _payload 只在
    有 tools 时才把它塞进去——否则收尾那一轮（工具已摘掉）必然 400。
    """
    return os.getenv("LLM_THINKING", "").strip().lower()


def available() -> bool:
    if os.getenv("LLM_ENABLED", "1").lower() in {"0", "false", "no"}:
        return False
    return bool(_api_key())


def _headers() -> dict:
    return {"Content-Type": "application/json", "Authorization": f"Bearer {_api_key()}"}


def _post(body: dict, timeout: int):
    req = urllib.request.Request(
        f"{_base_url()}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers=_headers(),
        method="POST",
    )
    return urllib.request.urlopen(req, timeout=timeout)


def _payload(messages: list[dict], temperature: float, max_tokens: int,
             with_thinking: bool = False, model: str | None = None, **extra) -> dict:
    body = {
        "model": model or _model(),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    lvl = _thinking()
    # 只在带 tools 的请求里发 thinking，否则 GLM-5.3-Flash 会回 1210
    if lvl and with_thinking:
        body["thinking"] = {"type": lvl}
    body.update({k: v for k, v in extra.items() if v is not None})
    return body


def route_model() -> str:
    """专门用来「判断该调哪个工具」的模型。

    实测：GLM-5.3-Flash 出第一个 token 要 4～11 秒（它每次都要先思考），
    GLM-4.5-Air 只要 0.7 秒。工具决策是个简单的分类任务，用快模型足够，
    省下来的 5 秒是整条链路里性价比最高的一笔。
    """
    return os.getenv("LLM_ROUTE_MODEL", "").strip()


def chat(messages: list[dict], temperature: float = 0.3, max_tokens: int = 700,
         timeout: int = 60, model: str | None = None) -> str | None:
    if not available():
        return None
    try:
        with _post(_payload(messages, temperature, max_tokens, model=model), timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        _mark_ok()
        return (data["choices"][0]["message"].get("content") or "").strip()
    except urllib.error.HTTPError as e:
        _mark_fail(e)
        return None
    except (urllib.error.URLError, KeyError, json.JSONDecodeError, TimeoutError, OSError) as e:
        _mark_fail(e)
        return None


def chat_stream(messages: list[dict], temperature: float = 0.3, max_tokens: int = 700,
                timeout: int = 90, model: str | None = None):
    """流式生成：逐块 yield 文本增量。推理模型的 reasoning_content 不输出。"""
    if not available():
        return
    try:
        with _post(_payload(messages, temperature, max_tokens, stream=True, model=model), timeout) as resp:
            _mark_ok()
            for raw in resp:
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    obj = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                delta = (obj.get("choices") or [{}])[0].get("delta") or {}
                piece = delta.get("content")
                if piece:
                    yield piece
    except (urllib.error.URLError, TimeoutError, KeyError, OSError):
        return


def chat_tools(messages: list[dict], tools: list[dict], temperature: float = 0.2,
               max_tokens: int = 1200, timeout: int = 120) -> dict | None:
    """带工具的一次调用。

    返回 {"content": str, "tool_calls": list, "finish_reason": str,
          "reasoning": str, "usage": dict}；失败返回 None，由上层回落规则引擎。
    """
    if not available():
        return None
    body = _payload(
        messages, temperature, max_tokens,
        with_thinking=bool(tools),
        tools=tools or None,
        tool_choice="auto" if tools else None,
    )
    try:
        with _post(body, timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "ignore")[:300]
        except OSError:
            detail = ""
        print(f"[llm] HTTP {e.code} {detail}", flush=True)
        _mark_fail(e)
        return None
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError) as e:
        print(f"[llm] 调用失败：{e}", flush=True)
        _mark_fail(e)
        return None

    _mark_ok()
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    return {
        "content": (msg.get("content") or "").strip(),
        "tool_calls": msg.get("tool_calls") or [],
        "finish_reason": choice.get("finish_reason") or "",
        "reasoning": (msg.get("reasoning_content") or "").strip(),
        "usage": data.get("usage") or {},
    }


def stream_tools(messages: list[dict], tools: list[dict], temperature: float = 0.2,
                 max_tokens: int = 1200, timeout: int = 120, on_delta=None,
                 model: str | None = None) -> dict | None:
    """带工具的流式调用：文本增量实时回调，工具调用在流结束后一次性返回。

    为什么要有它：非流式的 tool 调用要等模型把整段回答生成完才返回，
    实测一次 4～5 秒；用户盯着转圈，体感很差。改成流式后首字约 1～2 秒就出来了。

    返回结构与 chat_tools() 完全一致，调用方不用区分两种情况。
    """
    if not available():
        return None
    if not tools:
        # 没有工具时就摘掉 thinking 参数：GLM-5.3-Flash 带 thinking 却不带 tools 会回 1210
        body = _payload(messages, temperature, max_tokens, stream=True, model=model)
    else:
        body = _payload(messages, temperature, max_tokens, stream=True, model=model,
                        with_thinking=True, tools=tools, tool_choice="auto")

    content: list[str] = []
    # 工具调用是分片下发的：同一 index 的 name 只来一次，arguments 是一段段 JSON 碎片拼起来
    slots: dict[int, dict] = {}
    finish = ""
    reasoning: list[str] = []

    try:
        with _post(body, timeout) as resp:
            _mark_ok()
            for raw in resp:
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    obj = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                choice = (obj.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                if choice.get("finish_reason"):
                    finish = choice["finish_reason"]
                if delta.get("reasoning_content"):
                    reasoning.append(delta["reasoning_content"])
                piece = delta.get("content")
                if piece:
                    content.append(piece)
                    if on_delta:
                        on_delta(piece)
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    slot = slots.setdefault(idx, {"id": "", "function": {"name": "", "arguments": ""}})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["function"]["name"] += fn["name"]
                    if fn.get("arguments"):
                        slot["function"]["arguments"] += fn["arguments"]
    except (urllib.error.URLError, TimeoutError, KeyError, OSError) as e:
        print(f"[llm] 流式调用失败：{e}", flush=True)
        # 已经吐出部分文本就当作成功，否则交给上层回落
        if not content:
            _mark_fail(e)
            return None

    calls = [slots[k] for k in sorted(slots) if slots[k]["function"]["name"]]
    for c in calls:
        c["id"] = c["id"] or f"call_{c['function']['name']}"
    return {
        "content": "".join(content).strip(),
        "tool_calls": calls,
        "finish_reason": finish or ("tool_calls" if calls else "stop"),
        "reasoning": "".join(reasoning).strip(),
        "usage": {},
    }


def status() -> dict:
    return {
        "enabled": available(),
        "model": _model(),
        "base_url": _base_url(),
        "thinking": _thinking() or "(默认)",
        "route_model": route_model(),
    }


def __getattr__(name: str):
    """兼容旧写法：llm.MODEL / llm.BASE_URL / llm.API_KEY / llm.ENABLED。"""
    if name == "MODEL":
        return _model()
    if name == "BASE_URL":
        return _base_url()
    if name == "API_KEY":
        return _api_key()
    if name == "ENABLED":
        return os.getenv("LLM_ENABLED", "1").lower() not in {"0", "false", "no"}
    raise AttributeError(f"module 'llm' has no attribute {name!r}")
