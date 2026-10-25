"""大模型接入层（可选）。

没有配置 key 时返回 None，上层自动降级为模板化回答；
配置任意 OpenAI 兼容服务（DeepSeek、通义、Kimi、vLLM 等）即可开启生成式表达。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
API_KEY = os.getenv("LLM_API_KEY", "")
MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
ENABLED = os.getenv("LLM_ENABLED", "1") not in {"0", "false", "False"}


def available() -> bool:
    return bool(ENABLED and API_KEY)


def chat(messages: list[dict], temperature: float = 0.3, max_tokens: int = 700, timeout: int = 30) -> str | None:
    if not available():
        return None
    payload = json.dumps({
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, KeyError, json.JSONDecodeError, TimeoutError):
        return None


def chat_stream(messages: list[dict], temperature: float = 0.3, max_tokens: int = 700,
                timeout: int = 60):
    """流式生成：逐块 yield 文本增量。未配置 key 时什么都不产出。"""
    if not available():
        return
    payload = json.dumps({
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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
    except (urllib.error.URLError, TimeoutError, KeyError):
        return


def status() -> dict:
    return {"enabled": available(), "model": MODEL, "base_url": BASE_URL}
