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
MESSAGES = None  # 在文件末尾实例化，避免前向引用


class MessageCenter:
    """家长端 ↔ 辅导员端 双向消息。

    设计：
    - 以学生 sid 为配对键（thread_id = "pc:{sid}"），家长账号 = 孩子学号，
      导员账号 = 工号；一个学生的家长和导员之间只有一条会话线。
    - 每条消息记录 from/to/正文/时间/已读；发送时同时给对方推一条通知（复用 NOTIFS），
      保证对方即使不打开消息面板也能从铃铛红点 + 永久弹窗看到。
    - 纯内存实现（演示场景）。
    """

    def __init__(self) -> None:
        self._threads: dict[str, list[dict]] = {}   # thread_id → 消息列表（时间正序）
        self._lock = threading.Lock()
        self._seq = 0

    @staticmethod
    def thread_id(sid: str) -> str:
        return f"pc:{sid}"

    def _new(self, from_role: str, from_name: str, to_role: str, to_name: str,
             text: str, sid: str) -> dict:
        self._seq += 1
        return {
            "id": f"m{self._seq:04d}",
            "thread_id": self.thread_id(sid),
            "sid": sid,
            "from_role": from_role,
            "from_name": from_name,
            "to_role": to_role,
            "to_name": to_name,
            "text": text,
            "ts": _now(),
            "read": False,
        }

    def send(self, from_role: str, from_account: str, from_name: str,
             to_role: str, to_account: str, to_name: str, text: str,
             sid: str) -> dict:
        """发一条消息；同时给对方推一条通知（铃铛红点 + 永久弹窗）。

        只推这一条通知，前端不再合成第二条：旧版前端 notices.ts 会再合成一条
        “发来家校消息”的弹窗，导致用户看到两个标题不同的弹窗。
        现在统一由后端推、kind 固定 family_message，标题就叫“发来家校消息”。
        """
        text = (text or "").strip()
        if not text:
            raise ValueError("消息内容不能为空")
        msg = self._new(from_role, from_name, to_role, to_name, text, sid)
        with self._lock:
            self._threads.setdefault(msg["thread_id"], []).append(msg)
        # 给对方推通知（唯一一份）
        NOTIFS.push(to_role, to_account, "family_message",
                    f"{from_name} 发来家校消息",
                    text[:80] + ("…" if len(text) > 80 else ""),
                    {"thread_id": msg["thread_id"], "sid": sid, "msg_id": msg["id"]})
        return msg

    def recall(self, msg_id: str) -> dict | None:
        """撤回一条消息（对话里点的动作执行后悔了）。

        只允许撤回自己刚发的那条：从会话里摘掉，并给对方补一条「已撤回」通知，
        免得家长端留下一句没有下文的独白。
        """
        with self._lock:
            for _tid, rows in self._threads.items():
                for i, m in enumerate(rows):
                    if m.get("id") == msg_id:
                        gone = rows.pop(i)
                        NOTIFS.push(gone["to_role"], gone["sid"], "family_message",
                                    f"{gone['from_name']} 撤回了一条消息",
                                    "对方撤回了刚才那条家校消息。",
                                    {"thread_id": gone["thread_id"], "sid": gone["sid"]})
                        return gone
        return None

    def threads_for(self, role: str, account: str, students: list[dict] | None = None) -> list[dict]:
        """返回该用户参与的会话列表（家长：1 条；导员：名下每个学生一条）。

        students 用来补全导员侧的学生姓名/班级（家长侧 sid 就是自己孩子，不必补）。
        每条会话带 peer_phone（对方联系方式）：家长端看到的是辅导员电话，
        导员端看到的是对应学生家长的电话——方便两端互相找。

        导员端的列表要展示「风险高的学生优先」——哪怕还没发过消息的学生，
        也应该列出来让导员能主动联系。所以遍历 students 全集，按 level 排序：
        红 → 黄 → 绿，同级按分数降序。没消息的会话 messages=[]。
        """
        out: list[dict] = []
        stu_map = {str(s["id"]): s for s in (students or [])}
        # 演示场景固定一位辅导员，电话也固定为占位号（数据集里没有真实辅导员电话）
        counselor_phone = "138-0013-8000"
        if role == "parent":
            # 家长只看自己孩子那条线
            sid = account
            tid = self.thread_id(sid)
            msgs = self._threads.get(tid, [])
            if msgs:
                unread = sum(1 for m in msgs if m["to_role"] == "parent" and not m["read"])
                out.append({"thread_id": tid, "sid": sid,
                            "peer_name": "辅导员", "peer_role": "counselor",
                            "peer_phone": counselor_phone,
                            "last_text": msgs[-1]["text"], "last_ts": msgs[-1]["ts"],
                            "unread": unread, "messages": list(msgs)})
            else:
                out.append({"thread_id": tid, "sid": sid,
                            "peer_name": "辅导员", "peer_role": "counselor",
                            "peer_phone": counselor_phone,
                            "last_text": "", "last_ts": "",
                            "unread": 0, "messages": []})
        elif role == "counselor":
            # 导员看所有名下学生（不只发过消息的）：遍历 students 全集，
            # 没消息的学生也列出来，messages=[]，方便主动联系。
            # 没拿到 students 兜底用已发消息的会话。
            if stu_map:
                order = {"red": 0, "yellow": 1, "green": 2}
                items = sorted(
                    stu_map.values(),
                    key=lambda s: (order.get(s.get("level"), 9), -(s.get("score") or 0)),
                )
                for stu in items:
                    sid = str(stu["id"])
                    tid = self.thread_id(sid)
                    msgs = self._threads.get(tid, [])
                    peer_name = f"{stu['name']} 家长"
                    tail = stu.get("phone_tail")
                    if not tail and sid:
                        try:
                            tail = f"{int(sid[-4:]) % 10000:04d}"
                        except Exception:
                            tail = "0000"
                    peer_phone = f"138-0013-{tail}"
                    unread = sum(1 for m in msgs if m["to_role"] == "counselor" and not m["read"])
                    out.append({
                        "thread_id": tid, "sid": sid,
                        "peer_name": peer_name, "peer_role": "parent",
                        "peer_phone": peer_phone,
                        "last_text": msgs[-1]["text"] if msgs else "",
                        "last_ts": msgs[-1]["ts"] if msgs else "",
                        "unread": unread, "messages": list(msgs),
                        # 学生侧信息：供前端列表展示风险标签/分数/班级
                        "student_name": stu["name"],
                        "student_class": stu.get("class_name", ""),
                        "level": stu.get("level", "green"),
                        "score": stu.get("score", 0),
                        "top_factor": stu.get("top_factor", ""),
                    })
            else:
                # 兜底：没传 students 就按旧逻辑只看有消息的
                for tid, msgs in self._threads.items():
                    sid = tid.split(":", 1)[1]
                    peer_name = f"家长（{sid}）"
                    tail = "0000"
                    try:
                        tail = f"{int(sid[-4:]) % 10000:04d}"
                    except Exception:
                        pass
                    peer_phone = f"138-0013-{tail}"
                    unread = sum(1 for m in msgs if m["to_role"] == "counselor" and not m["read"])
                    out.append({"thread_id": tid, "sid": sid,
                                "peer_name": peer_name, "peer_role": "parent",
                                "peer_phone": peer_phone,
                                "last_text": msgs[-1]["text"] if msgs else "",
                                "last_ts": msgs[-1]["ts"] if msgs else "",
                                "unread": unread, "messages": list(msgs)})
                out.sort(key=lambda x: x["last_ts"] or "", reverse=True)
        return out

    def mark_read(self, thread_id: str, role: str) -> int:
        """把该会话里对方发给我的消息全部标已读。"""
        n = 0
        with self._lock:
            for m in self._threads.get(thread_id, []):
                if m["to_role"] == role and not m["read"]:
                    m["read"] = True
                    n += 1
        return n

    def unread_count(self, role: str, account: str) -> int:
        """该用户收到的未读消息数（用于铃铛徽标合并）。"""
        total = 0
        for tid in self._threads:
            for m in self._threads[tid]:
                if m["to_role"] == role and not m["read"]:
                    # 家长只看自己那条线（account=sid）；导员看全部
                    if role == "parent" and tid.split(":", 1)[1] != account:
                        continue
                    total += 1
        return total


MESSAGES = MessageCenter()


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

    # ---- 教师端：名下学生的作业未交 / 考勤异常 / 红色预警 ----
    from collections import defaultdict
    t_stats: dict = defaultdict(lambda: {"hw_missing": [], "absent": [], "red": []})
    for s in students:
        s_lv = engine.score(s["id"])["level"]
        for c in s["courses"]:
            tp = c.get("teacher_profile") or {}
            eid = tp.get("employee_id")
            if not eid:
                continue
            if any(h.get("status") == "missing" for h in c.get("homework", [])):
                t_stats[eid]["hw_missing"].append(s["name"])
            if c.get("absent", 0) > 0:
                t_stats[eid]["absent"].append(s["name"])
            if s_lv == "red":
                t_stats[eid]["red"].append(s["name"])
    for eid, st in t_stats.items():
        if st["hw_missing"]:
            names = "、".join(st["hw_missing"][:5])
            NOTIFS.push("teacher", eid, "homework", f"作业未交提醒：{len(st['hw_missing'])} 名学生",
                        f"未交学生：{names}{'等' if len(st['hw_missing']) > 5 else ''}。"
                        f"建议下节课前提醒补交，可在对话里问「谁的风险最高」定位重点。",
                        {"count": str(len(st["hw_missing"]))})
            TODOS.push("teacher", eid, "homework", f"跟进 {len(st['hw_missing'])} 名学生补交作业",
                       "在对话里问「我课上的学生」可看完整名单与明细。")
        if st["red"]:
            rnames = "、".join(st["red"][:5])
            NOTIFS.push("teacher", eid, "risk", f"红色预警学生：{len(st['red'])} 名",
                        f"红色名单：{rnames}{'等' if len(st['red']) > 5 else ''}。"
                        f"建议联系辅导员联动帮扶。", {"count": str(len(st["red"]))})
            TODOS.push("teacher", eid, "risk", f"关注 {len(st['red'])} 名红色预警学生",
                       "在对话里问「我该重点关注谁」可拿重点名单。")
