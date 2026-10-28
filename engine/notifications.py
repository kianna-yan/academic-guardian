"""四端消息中心：事件通知、待办事项、学生异议。

设计要点
- 按「角色:账号」隔离（与 ConversationMemory 同一个键规则），每端只看得到自己的
  通知与待办——学生看到的是"你的旷课/缺交/预警"，导员看到的是"学生异议/约谈提醒"。
- 启动播种（seed）：从数据集里把每个学生的旷课、作业缺交、风险预警落成
  通知 + 待办；给辅导员生成红色/黄色学生约谈待办。
- 学生异议闭环：学生对某条考勤/作业记录提异议 → 实时生成导员端通知 + 待办；
  导员处理（同意/驳回）→ 学生端收到回执通知，原待办同步闭环。
- 纯内存实现（演示场景重启重置可接受），接口按可替换设计。
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime

from engine.accounts import ADMIN_ACCOUNT, COUNSELOR_ACCOUNT


def _now() -> str:
    return datetime.now().strftime("%m-%d %H:%M")


def _key(role: str, account: str) -> str:
    return f"{role}:{account}"


class _Store:
    """role:account → 有序列表 的线程安全兜底容器。"""

    def __init__(self) -> None:
        self._data: dict[str, list[dict]] = {}
        self._lock = threading.Lock()

    def list(self, role: str, account: str) -> list[dict]:
        with self._lock:
            return list(self._data.get(_key(role, account), []))

    def add(self, role: str, account: str, item: dict, top: bool = True) -> dict:
        with self._lock:
            rows = self._data.setdefault(_key(role, account), [])
            if top:
                rows.insert(0, item)
            else:
                rows.append(item)
            return item

    def patch(self, role: str, account: str, item_id: str, **fields) -> dict | None:
        with self._lock:
            for row in self._data.get(_key(role, account), []):
                if row["id"] == item_id:
                    row.update(fields)
                    return row
            return None


class NotificationCenter:
    """未读通知。学生端：旷课/缺交/预警/异议回执；导员端：学生异议/约谈提醒。"""

    def __init__(self) -> None:
        self._store = _Store()
        self._seq = 0

    def _new(self, kind: str, title: str, text: str, meta: dict | None = None) -> dict:
        self._seq += 1
        return {
            "id": f"n{self._seq:04d}",
            "kind": kind,          # absent | homework | risk | appeal_new | appeal_reply
            "title": title,
            "text": text,
            "ts": _now(),
            "read": False,
            "meta": meta or {},
        }

    def push(self, role: str, account: str, kind: str, title: str, text: str,
             meta: dict | None = None) -> dict:
        return self._store.add(role, account, self._new(kind, title, text, meta))

    def unread(self, role: str, account: str) -> list[dict]:
        return [n for n in self._store.list(role, account) if not n["read"]]

    def mark_read(self, role: str, account: str, ids: list[str]) -> int:
        n = 0
        for i in ids:
            if self._store.patch(role, account, i, read=True):
                n += 1
        return n


class TodoCenter:
    """待办事项。学生：补交作业/说明缺勤/查看预警；导员：处理异议/约谈学生。"""

    def __init__(self) -> None:
        self._store = _Store()
        self._seq = 0

    def _new(self, kind: str, title: str, detail: str, meta: dict | None = None) -> dict:
        self._seq += 1
        return {
            "id": f"t{self._seq:04d}",
            "kind": kind,          # homework | attendance | risk | appeal | talk
            "title": title,
            "detail": detail,
            "ts": _now(),
            "done": False,
            "meta": meta or {},
        }

    def push(self, role: str, account: str, kind: str, title: str, detail: str,
             meta: dict | None = None) -> dict:
        return self._store.add(role, account, self._new(kind, title, detail, meta))

    def items(self, role: str, account: str) -> list[dict]:
        return self._store.list(role, account)

    def finish(self, role: str, account: str, item_id: str) -> dict | None:
        return self._store.patch(role, account, item_id, done=True)

    def close_by_meta(self, role: str, account: str, match: dict) -> int:
        """按 meta 字段批量闭环（如异议处理完，导员端对应待办自动完成）。"""
        n = 0
        for row in self._store.list(role, account):
            if row["done"]:
                continue
            if all(row.get("meta", {}).get(k) == v for k, v in match.items()):
                self._store.patch(role, account, row["id"], done=True)
                n += 1
        return n


class AppealCenter:
    """学生异议：对某条考勤/作业记录不认可，提出说明，等导员裁定。"""

    def __init__(self) -> None:
        self._rows: list[dict] = []
        self._lock = threading.Lock()
        self._seq = 0

    def submit(self, profile: dict, kind: str, record_id: str, course: str,
               reason: str, extra: dict | None = None) -> dict:
        self._seq += 1
        row = {
            "id": f"a{self._seq:04d}",
            "sid": profile.get("sid") or profile.get("account"),
            "name": profile.get("name", ""),
            "class_name": profile.get("class_name", ""),
            "advisor": profile.get("advisor", ""),
            "kind": kind,              # attendance | homework
            "record_id": record_id,
            "course": course,
            "reason": reason,
            "ts": _now(),
            "status": "pending",       # pending | accepted | rejected
            "reply": "",
            "extra": extra or {},
        }
        with self._lock:
            self._rows.insert(0, row)
        return row

    def by_student(self, sid: str) -> list[dict]:
        return [r for r in self._rows if r["sid"] == sid]

    def by_advisor(self, advisor: str) -> list[dict]:
        rows = [r for r in self._rows if r["advisor"] == advisor]
        return rows if rows else list(self._rows)   # 导员名下无匹配时放宽为全部（演示场景）

    def all(self) -> list[dict]:
        return list(self._rows)

    def get(self, aid: str) -> dict | None:
        return next((r for r in self._rows if r["id"] == aid), None)

    def resolve(self, aid: str, action: str, reply: str) -> dict | None:
        row = self.get(aid)
        if row:
            row["status"] = "accepted" if action == "accept" else "rejected"
            row["reply"] = reply
        return row


NOTIFS = NotificationCenter()
TODOS = TodoCenter()
APPEALS = AppealCenter()


# ---------------------------------------------------------------------------
# 启动播种：把数据集里"已经发生"的事变成各端的未读消息与待办
# ---------------------------------------------------------------------------

def seed(engine) -> None:
    """启动时调用。为每个学生生成旷课/缺交/预警通知+待办；给导员生成约谈待办。"""
    students = engine.students
    for s in students:
        sid = s["id"]
        key = ("student", sid)
        level = engine.score(sid)["level"]

        # ---- 旷课 ----
        absences: list[dict] = []
        for c in s["courses"]:
            for a in c.get("attendance", []):
                if a["status"] == "absent":
                    absences.append({**a, "course": c["name"]})
        if absences:
            absences.sort(key=lambda x: x["date"], reverse=True)
            latest = absences[0]
            NOTIFS.push(*key, "absent", f"考勤提醒：本学期已旷课 {len(absences)} 次",
                        f"最近一次：{latest['course']}（{latest['date']} {latest['period']}，{latest['note']}）。"
                        f"多次旷课会影响平时成绩并触发预警，如有特殊情况可在记录旁提出异议。",
                        {"course": latest["course"], "date": latest["date"]})
            TODOS.push(*key, "attendance", "说明缺勤情况",
                       f"{latest['course']} {latest['date']} 的旷课记录如有误或确有原因，"
                       f"可在学业明细里提出异议，或主动联系辅导员说明。",
                       {"course": latest["course"], "date": latest["date"]})

        # ---- 作业缺交 ----
        missing: list[dict] = []
        for c in s["courses"]:
            for h in c.get("homework", []):
                if h["status"] == "missing":
                    missing.append({**h, "course": c["name"]})
        if missing:
            first = missing[0]
            names = "、".join(f"《{m['course']}》{m['title']}" for m in missing[:3])
            NOTIFS.push(*key, "homework", f"作业提醒：有 {len(missing)} 次作业未交",
                        f"{names}{'等' if len(missing) > 3 else ''}已过截止时间。未交作业直接影响平时分，"
                        f"尽快补交并和任课老师说明情况。", {"course": first["course"]})
            TODOS.push(*key, "homework", f"补交 {len(missing)} 次作业",
                       f"未交：{names}{'等' if len(missing) > 3 else ''}。补交后风险分会跟着回落。",
                       {"course": first["course"]})

        # ---- 预警 ----
        if level in ("red", "yellow"):
            label = "红色预警" if level == "red" else "黄色关注"
            NOTIFS.push(*key, "risk", f"学业{label}通知",
                        "系统根据出勤、作业、期中成绩等综合评估后发出提醒。"
                        "不用慌——先看风险拆解找到最弱的一环，从最容易补的一件事做起。",
                        {"level": level})
            TODOS.push(*key, "risk", "查看我的风险拆解",
                       "在对话里问「我的风险分为什么这么高」，按建议先补最弱的一项。")

        # ---- 家长端同步一份预警 ----
        if level in ("red", "yellow"):
            NOTIFS.push("parent", sid, "risk",
                        f"孩子学业{'红色预警' if level == 'red' else '黄色关注'}提醒",
                        "学校已根据综合数据发出提醒，建议和孩子聊聊近期的出勤与作业情况，"
                        "有疑问可在家长端直接询问。")

    # ---- 导员端：名下红/黄学生约谈待办 ----
    pool: dict[str, list] = {}
    for s in students:
        pool.setdefault(s.get("advisor", ""), []).append(s)
    for advisor, rows in pool.items():
        rows.sort(key=lambda x: -engine.score(x["id"])["score"])
        for s in rows:
            lv = engine.score(s["id"])["level"]
            if lv in ("red", "yellow"):
                TODOS.push("counselor", COUNSELOR_ACCOUNT, "talk",
                           f"约谈 {s['name']}（{s['class_name']}）",
                           f"{lv} 级学生，风险分 {engine.score(s['id'])['score']}，"
                           f"可在对话里说「给 {s['name']} 生成谈话要点」先做功课。",
                           {"sid": s["id"], "level": lv})
