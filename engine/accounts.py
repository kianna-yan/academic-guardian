"""账号体系：四个端各自独立的登录身份。

设计要点
- 密码只用 PBKDF2-SHA256 存哈希，库里不落明文；初始密码统一走 DEFAULT_PASSWORD。
- 账号库写 JSON 文件（data/accounts.json），改密、批量导入都能跨进程重启保留。
- 登录态用 HMAC 签名 token（无状态），服务重启不掉登录。
- 学生/家长以学号为主体，家长账号和学生共用学号但密码不同、权限不同。

默认账号（首次运行自动创建）
- 学生端：学号（学情库里的 8 位学号） / 0000
- 辅导员端：2024014589 / 1111
- 教务端：1234567899 / 2222
- 家长端：学生学号 / 3333
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from typing import Any

PBKDF2_ROUNDS = 120_000
TOKEN_TTL = 12 * 3600

ROLE_STUDENT = "student"
ROLE_COUNSELOR = "counselor"
ROLE_ADMIN = "admin"
ROLE_PARENT = "parent"
ROLE_TEACHER = "teacher"

ROLES = (ROLE_STUDENT, ROLE_COUNSELOR, ROLE_ADMIN, ROLE_PARENT, ROLE_TEACHER)
ROLE_LABEL = {
    ROLE_STUDENT: "学生",
    ROLE_COUNSELOR: "辅导员",
    ROLE_ADMIN: "教务",
    ROLE_PARENT: "家长",
    ROLE_TEACHER: "任课教师",
}

DEFAULT_PASSWORD = {
    ROLE_STUDENT: "0000",
    ROLE_COUNSELOR: "1111",
    ROLE_ADMIN: "2222",
    ROLE_PARENT: "3333",
    ROLE_TEACHER: "4444",
}

COUNSELOR_ACCOUNT = "2024014589"
ADMIN_ACCOUNT = "1234567899"

MIN_PASSWORD_LEN = 4
MAX_PASSWORD_LEN = 32


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ROUNDS
    ).hex()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


class AccountError(Exception):
    """业务层可直接展示给用户的错误。"""


class Accounts:
    """账号库 + 登录态。所有公开方法都返回纯 dict，方便直接丢给 FastAPI。"""

    def __init__(self, students: list[dict], path: Path, teachers: dict | None = None):
        self.path = Path(path)
        self.students = {str(s["id"]): s for s in students}
        self.teachers = teachers or {}  # {教师姓名: {...含 employee_id}}
        self.data: dict[str, Any] = {}
        self.persistent = True
        self._load()
        self._bootstrap()

    # ------------------------------------------------------------------ 存储
    def _load(self) -> None:
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.data = {}
        self.data.setdefault("secret", secrets.token_hex(32))
        self.data.setdefault("students", {})
        self.data.setdefault("parents", {})
        self.data.setdefault("staff", {})
        self.data.setdefault("teachers", {})

    def _save(self) -> None:
        """落盘失败不阻断业务。

        线上托管环境是只读挂载，写不进去时退化成内存态账号库：本次进程内
        改密/导入照常生效，重启后回到初始密码，不会因为一次 IO 异常把登录打成 500。
        """
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(self.path)
            self.persistent = True
        except OSError:
            self.persistent = False

    def _bootstrap(self) -> None:
        changed = False
        for role, account in ((ROLE_COUNSELOR, COUNSELOR_ACCOUNT), (ROLE_ADMIN, ADMIN_ACCOUNT)):
            entry = self.data["staff"].get(role)
            if not entry:
                salt = secrets.token_hex(8)
                self.data["staff"][role] = {
                    "role": role,
                    "account": account,
                    "salt": salt,
                    "hash": _hash(DEFAULT_PASSWORD[role], salt),
                    "changed": False,
                    "created_at": _now(),
                }
                changed = True
        # 任课教师账号：每位教师一个工号，关联到 data.TEACHERS 的姓名
        for tname, tinfo in self.teachers.items():
            eid = tinfo.get("employee_id") or tname
            if eid not in self.data["teachers"]:
                salt = secrets.token_hex(8)
                self.data["teachers"][eid] = {
                    "role": ROLE_TEACHER,
                    "account": eid,
                    "teacher_name": tname,
                    "salt": salt,
                    "hash": _hash(DEFAULT_PASSWORD[ROLE_TEACHER], salt),
                    "changed": False,
                    "created_at": _now(),
                }
                changed = True
        if changed:
            self._save()

    # ------------------------------------------------------------- 内部工具
    def _new_entry(self, role: str) -> dict:
        salt = secrets.token_hex(8)
        return {
            "role": role,
            "salt": salt,
            "hash": _hash(DEFAULT_PASSWORD[role], salt),
            "changed": False,
            "created_at": _now(),
        }

    def _student_profile(self, sid: str, entry: dict) -> dict:
        s = self.students[sid]
        return {
            "role": ROLE_STUDENT,
            "account": sid,
            "sid": sid,
            "name": s.get("name", ""),
            "class_name": s.get("class_name", ""),
            "advisor": s.get("advisor", ""),
            "must_change": not entry.get("changed", False),
        }

    def _parent_profile(self, sid: str, entry: dict) -> dict:
        s = self.students[sid]
        return {
            "role": ROLE_PARENT,
            "account": sid,
            "sid": sid,
            "name": f"{s.get('name', '')} 家长",
            "class_name": s.get("class_name", ""),
            "advisor": s.get("advisor", ""),
            "must_change": not entry.get("changed", False),
        }

    def _staff_profile(self, role: str, entry: dict) -> dict:
        name = "刘畅" if role == ROLE_COUNSELOR else "教务处 · 张敏"
        return {
            "role": role,
            "account": entry["account"],
            "sid": None,
            "name": name,
            "class_name": "计科 2024 级" if role == ROLE_COUNSELOR else "全校",
            "advisor": "",
            "must_change": not entry.get("changed", False),
        }

    def _teacher_profile(self, entry: dict) -> dict:
        """教师身份：name=教师名（后端按名查所教课与学生），class_name=所在院系。"""
        tname = entry.get("teacher_name", "")
        tinfo = self.teachers.get(tname, {})
        return {
            "role": ROLE_TEACHER,
            "account": entry["account"],
            "sid": None,
            "name": tname,
            "class_name": tinfo.get("dept", "任课教师"),
            "advisor": tname,  # 复用 advisor 字段带教师名，后端按此查所教课
            "must_change": not entry.get("changed", False),
        }

    def _entry_for(self, role: str, account: str) -> dict | None:
        """取账号条目；学生/家长首次登录时懒创建（等价于教务已为其开通）。"""
        account = (account or "").strip()
        if role == ROLE_STUDENT:
            if account not in self.students:
                return None
            entry = self.data["students"].get(account)
            if not entry:
                entry = self._new_entry(ROLE_STUDENT)
                self.data["students"][account] = entry
                self._save()
            return entry
        if role == ROLE_PARENT:
            if account not in self.students:
                return None
            entry = self.data["parents"].get(account)
            if not entry:
                entry = self._new_entry(ROLE_PARENT)
                self.data["parents"][account] = entry
                self._save()
            return entry
        if role in (ROLE_COUNSELOR, ROLE_ADMIN):
            entry = self.data["staff"].get(role)
            if entry and entry["account"] == account:
                return entry
            return None
        if role == ROLE_TEACHER:
            return self.data["teachers"].get(account)
        return None

    # ---------------------------------------------------------------- 登录态
    def _secret(self) -> bytes:
        return self.data["secret"].encode("utf-8")

    def issue_token(self, profile: dict) -> str:
        payload = {
            "r": profile["role"],
            "a": profile["account"],
            "n": profile["name"],
            "e": int(time.time()) + TOKEN_TTL,
        }
        body = _b64(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        sig = _b64(hmac.new(self._secret(), body.encode("ascii"), hashlib.sha256).digest())
        return f"{body}.{sig}"

    def read_token(self, token: str) -> dict | None:
        try:
            body, sig = token.split(".", 1)
        except ValueError:
            return None
        expect = _b64(hmac.new(self._secret(), body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expect):
            return None
        try:
            payload = json.loads(_unb64(body))
        except Exception:
            return None
        if int(payload.get("e", 0)) < int(time.time()):
            return None
        return payload

    def profile_of(self, token: str) -> dict | None:
        payload = self.read_token(token)
        if not payload:
            return None
        role, account = payload.get("r"), payload.get("a")
        entry = self._entry_for(role, account)
        if not entry:
            return None
        return self._profile(role, account, entry)

    def _profile(self, role: str, account: str, entry: dict) -> dict:
        if role == ROLE_STUDENT:
            return self._student_profile(account, entry)
        if role == ROLE_PARENT:
            return self._parent_profile(account, entry)
        if role == ROLE_TEACHER:
            return self._teacher_profile(entry)
        return self._staff_profile(role, entry)

    # ------------------------------------------------------------------ 接口
    def login(self, role: str, account: str, password: str) -> dict:
        role = (role or "").strip()
        if role not in ROLES:
            raise AccountError("登录入口不存在")
        account = (account or "").strip()
        password = (password or "").strip()
        if not account or not password:
            raise AccountError("请输入账号和密码")

        entry = self._entry_for(role, account)
        if not entry:
            if role == ROLE_STUDENT:
                raise AccountError("学号不存在，请核对后重试")
            if role == ROLE_PARENT:
                raise AccountError("学号不存在，请核对孩子的学号")
            raise AccountError("账号或密码错误")

        if not hmac.compare_digest(_hash(password, entry["salt"]), entry["hash"]):
            raise AccountError("账号或密码错误")

        profile = self._profile(role, account, entry)
        return {
            "token": self.issue_token(profile),
            "profile": profile,
            "initial_password": DEFAULT_PASSWORD[role],
        }

    def change_password(self, profile: dict, old: str, new: str) -> dict:
        role, account = profile["role"], profile["account"]
        entry = self._entry_for(role, account)
        if not entry:
            raise AccountError("账号状态异常，请重新登录")
        if not hmac.compare_digest(_hash(old or "", entry["salt"]), entry["hash"]):
            raise AccountError("原密码不正确")
        new = new or ""
        if len(new) < MIN_PASSWORD_LEN:
            raise AccountError(f"新密码至少 {MIN_PASSWORD_LEN} 位")
        if len(new) > MAX_PASSWORD_LEN:
            raise AccountError(f"新密码最长 {MAX_PASSWORD_LEN} 位")
        if new == old:
            raise AccountError("新密码不能与原密码相同")
        salt = secrets.token_hex(8)
        entry["salt"] = salt
        entry["hash"] = _hash(new, salt)
        entry["changed"] = True
        entry["updated_at"] = _now()
        self._save()
        return self._profile(role, account, entry)

    # -------------------------------------------------------------- 批量导入
    def import_students(self, text: str) -> dict:
        """每行 `学号,姓名,班级[,初始密码]`；已存在的学号重置为初始密码。"""
        created, reset, failed = [], [], []
        lines = [ln.strip() for ln in (text or "").replace("\r", "").split("\n")]
        seen: set[str] = set()
        for no, line in enumerate(lines, 1):
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.replace("\t", ",").split(",")]
            sid = parts[0] if parts else ""
            if not sid:
                continue
            if sid in seen:
                failed.append({"line": no, "sid": sid, "reason": "同一批内重复"})
                continue
            seen.add(sid)
            if len(sid) != 8 or not sid.isdigit():
                failed.append({"line": no, "sid": sid, "reason": "学号需为 8 位数字"})
                continue
            if sid not in self.students:
                failed.append({"line": no, "sid": sid, "reason": "学情库中无此学号"})
                continue
            pwd = parts[3] if len(parts) > 3 and parts[3] else DEFAULT_PASSWORD[ROLE_STUDENT]
            if len(pwd) < MIN_PASSWORD_LEN:
                failed.append({"line": no, "sid": sid, "reason": "初始密码至少 4 位"})
                continue
            existed = sid in self.data["students"]
            entry = self._new_entry(ROLE_STUDENT)
            entry["salt"] = secrets.token_hex(8)
            entry["hash"] = _hash(pwd, entry["salt"])
            entry["changed"] = False
            self.data["students"][sid] = entry
            (reset if existed else created).append(sid)

        if created or reset:
            self._save()
        return {
            "ok": True,
            "created": len(created),
            "reset": len(reset),
            "failed": failed[:30],
            "failed_count": len(failed),
            "accounts": self.account_list(limit=8),
        }

    def account_list(self, limit: int = 200) -> list[dict]:
        rows = []
        for sid, entry in self.data["students"].items():
            s = self.students.get(sid, {})
            rows.append(
                {
                    "sid": sid,
                    "name": s.get("name", ""),
                    "class_name": s.get("class_name", ""),
                    "is_default": not entry.get("changed", False),
                    "created_at": entry.get("created_at", ""),
                }
            )
        rows.sort(key=lambda r: r["sid"])
        return rows[:limit]

    def stats(self) -> dict:
        total = len(self.students)
        opened = len(self.data["students"])
        changed = sum(1 for e in self.data["students"].values() if e.get("changed"))
        parents = len(self.data["parents"])
        teachers = len(self.data["teachers"])
        return {
            "student_total": total,
            "student_accounts": opened,
            "student_changed": changed,
            "parent_accounts": parents,
            "teacher_accounts": teachers,
        }


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")
