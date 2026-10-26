"""会话记忆：让智能体具备多轮对话能力。

设计要点
- 按「账号」隔离（学生 / 家长 / 辅导员 / 教务各自独立），每个账号保留最近几轮。
- 记的不只是消息文本，还有这轮"讨论过的学生""列过的名单"——这样下一轮
  用户说「他呢」「第 3 个是谁」「为什么」时才能正确指代。
- 纯内存实现：演示场景下重启丢记忆可接受，换来零依赖；接口按可替换设计。
"""
from __future__ import annotations

import threading

MAX_TURNS = 8


class ConversationMemory:
    def __init__(self, max_turns: int = MAX_TURNS):
        self._max = max_turns
        self._store: dict[str, list[dict]] = {}
        self._lock = threading.Lock()

    def history(self, key: str) -> list[dict]:
        with self._lock:
            return list(self._store.get(key, []))

    def append(self, key: str, turn: dict) -> None:
        with self._lock:
            rows = self._store.setdefault(key, [])
            rows.append(turn)
            if len(rows) > self._max:
                del rows[: len(rows) - self._max]

    def clear(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)


def memory_key(profile: dict) -> str:
    """账号 → 记忆隔离键。同一个学号的学生端和家长端也是两份独立记忆。"""
    role = profile.get("role") or "student"
    account = profile.get("account") or profile.get("sid") or "anon"
    return f"{role}:{account}"
