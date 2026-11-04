"""对话即操作（方案 C）：AI 只把动作摆出来，人点确认才执行。

约定（与方案原文一致）
--------------------
- 回答体里只有 **一个** action：``{id, type, label, payload, confirm}``；
- ``type`` 走白名单，并按角色过滤——学生端永远拿不到 ``send_letter``；
- 两段式：``propose()`` 只生成一张卡片，真正落地要等用户点按钮，
  再走 ``/api/actions/execute``（AI 建议 → 人确认 → 系统留痕）；
- 同一个 id 幂等：重复提交（刷新页面、点两下）返回首次结果，不重复写入；
- 执行过的动作都能撤销，``undo`` 做的是反操作（删记录 / 撤回消息），
  不是把历史抹掉。

为什么不在 ``answer()`` 里直接执行：发信、写信、发消息都对外产生副作用，
猜错一次就收不回来。把「决定权」留给人的那一下点击，才是可交付的形态。
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STORE = DATA_DIR / "actions.json"

# 白名单：type -> (允许的角色, 人话标签)
WHITELIST: dict[str, tuple[frozenset[str], str]] = {
    "export_letter": (frozenset({"student", "parent", "counselor", "admin"}), "导出文书"),
    "send_letter": (frozenset({"counselor", "admin"}), "发送家长信"),
    "record_intervention": (frozenset({"counselor", "admin"}), "记入干预台账"),
    "message_parent": (frozenset({"counselor"}), "给家长发消息"),
}

# 每个类型在卡片上给一句「点下去会发生什么」，避免用户盲点
EFFECT: dict[str, str] = {
    "export_letter": "按校规模板排版一份 Word，点下载即存到本机",
    "send_letter": "把这份告知函发给家长；未配置邮件服务器时生成 .eml 邮件文件",
    "record_intervention": "写进这名学生的干预台账，学生详情里立刻可见",
    "message_parent": "在「家校沟通」里给家长发一条消息，家长端同步收到",
}


def allowed(role: str, atype: str) -> bool:
    """角色白名单：越权的 type 直接不可见，不做「点了再报错」。"""
    row = WHITELIST.get(atype)
    return bool(row) and role in row[0]


def types_for(role: str) -> list[str]:
    return [t for t, (roles, _) in WHITELIST.items() if role in roles]


def propose(role: str, atype: str, sid: str | None, label: str,
            payload: dict | None = None, hint: str = "") -> dict | None:
    """生成一张待确认的动作卡片；角色不匹配返回 None（前端就什么都不显示）。"""
    if not allowed(role, atype):
        return None
    aid = f"{atype}-{sid or 'na'}-{uuid.uuid4().hex[:8]}"
    return {
        "id": aid,
        "type": atype,
        "label": label,
        "payload": payload or {},
        "confirm": True,
        "hint": hint or EFFECT.get(atype, ""),
        "ts": datetime.now().strftime("%H:%M:%S"),
    }


class ActionStore:
    """动作台账：幂等判重 + 撤销时反查原参数。

    进程内加锁，落盘到 ``data/actions.json``；落盘失败不影响主流程
    （线上托管目录可能只读，内存里的去重照样生效）。
    """

    def __init__(self, path: Path | None = STORE):
        self.path = path
        self._lock = threading.RLock()
        self._rows: dict[str, dict] = {}
        self._load()

    # ---------- 持久化 ----------
    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._rows = {str(k): v for k, v in data.items() if isinstance(v, dict)}
        except Exception:  # noqa: BLE001 - 台账坏了不能拖垮服务
            self._rows = {}

    def _save(self) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._rows, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:  # noqa: BLE001
            pass

    # ---------- 状态流转 ----------
    def get(self, aid: str) -> dict | None:
        with self._lock:
            row = self._rows.get(aid)
            return dict(row) if row else None

    def begin(self, aid: str, atype: str, payload: dict, actor: str = "") -> dict | None:
        """登记一次执行。

        返回 None = 首次执行，可以继续往下做；
        返回 dict = 已经执行过（幂等命中），直接把它当结果返回即可。
        """
        with self._lock:
            row = self._rows.get(aid)
            if row and row.get("state") in ("done", "undone"):
                res = dict(row.get("result") or {})
                res.update({"replayed": True, "state": row.get("state")})
                return res
            if row and row.get("state") == "running":
                # 上一次还在跑（连点了两下）：不重复执行，让前端稍后刷新
                res = dict(row.get("result") or {})
                res.update({"replayed": True, "state": "running"})
                return res
            self._rows[aid] = {
                "id": aid,
                "type": atype,
                "payload": payload,
                "state": "running",
                "actor": actor,
                "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._save()
            return None

    def finish(self, aid: str, result: dict) -> dict:
        with self._lock:
            row = self._rows.setdefault(aid, {"id": aid})
            row["state"] = "done"
            row["result"] = result
            row["done_at"] = datetime.now().strftime("%H:%M:%S")
            self._save()
        return result

    def fail(self, aid: str, error: str) -> None:
        with self._lock:
            row = self._rows.setdefault(aid, {"id": aid})
            row["state"] = "failed"
            row["error"] = error
            self._save()

    def mark_undone(self, aid: str, note: str = "") -> dict | None:
        with self._lock:
            row = self._rows.get(aid)
            if not row:
                return None
            row["state"] = "undone"
            row["undo_at"] = datetime.now().strftime("%H:%M:%S")
            if note:
                row["undo_note"] = note
            self._save()
            return dict(row)


ACTION_STORE = ActionStore()
