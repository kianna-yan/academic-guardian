"""课程与教师档案的教务端维护层。

教务在这里维护「哪门课由谁上、怎么找到这位老师」。默认值来自 engine/data.py 的
COURSES / TEACHERS，教务导入后会写进 data/curriculum.json 并即时覆盖到当前进程的
数据集上——学生端刷新即可看到新的联系方式和答疑时间，不需要重启服务。

导入格式（每行一门课，逗号 / 制表符 / 竖线分隔均可，允许带表头）：
课程代码, 课程名称, 学分, 类型, 任课教师, 上课时间, 教师邮箱, 教师电话, 办公室, 答疑时间
后面四列可以留空，表示只更新课程本身、不动这位老师的联系方式。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STORE = DATA_DIR / "curriculum.json"

FIELDS = ["code", "name", "credit", "kind", "teacher", "period",
          "email", "phone", "office", "office_hour"]

SEP = re.compile(r"\s*[,\t|，]\s*")
HEADER_HINT = ("课程代码", "课程编号", "code")


def _split(line: str) -> list[str]:
    return [x.strip().strip('"').strip("'") for x in SEP.split(line.strip())]


class Curriculum:
    def __init__(self) -> None:
        self.persistent = True
        self.updated_at = ""
        self.courses: list[dict] = []
        self.teachers: dict[str, dict] = {}
        self._load()

    # ---------------- 持久化 ----------------
    def _load(self) -> None:
        if not STORE.exists():
            return
        try:
            raw = json.loads(STORE.read_text(encoding="utf-8"))
        except Exception:
            return
        self.courses = raw.get("courses") or []
        self.teachers = raw.get("teachers") or {}
        self.updated_at = raw.get("updated_at") or ""

    def _save(self) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            STORE.write_text(json.dumps({
                "courses": self.courses,
                "teachers": self.teachers,
                "updated_at": self.updated_at,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            self.persistent = True
        except Exception:
            # 沙箱只读时降级为内存态：本次会话有效，重启回默认
            self.persistent = False

    # ---------------- 应用到数据集 ----------------
    def apply(self, dataset: dict) -> None:
        """把教务维护的内容贴到当前数据集上（就地修改）。"""
        if not self.courses:
            return
        by_code = {c["code"]: c for c in self.courses}
        catalog = {c["code"]: c for c in dataset["courses"]}
        dataset.setdefault("teachers", {})

        for code, course in by_code.items():
            raw_profile = self.teachers.get(course.get("teacher") or "") or {}
            # 导入往往只填联系方式，不能把内置的职称/院系冲掉，所以是"叠加"而不是"替换"
            base_profile = dataset.get("teachers", {}).get(course.get("teacher") or "", {})
            profile = {**base_profile,
                       **{k: v for k, v in raw_profile.items() if v not in ("", None)}}
            target = catalog.get(code)
            if target is not None:
                for key in ("name", "credit", "kind", "teacher", "period"):
                    if course.get(key) not in (None, ""):
                        target[key] = course[key]
            else:
                target = dict(course)
                dataset["courses"].append(target)
                catalog[code] = target
            if profile:
                dataset["teachers"][course["teacher"]] = dict(profile)

            # 同步到每个学生的课程快照
            for s in dataset["students"]:
                hit = next((c for c in s["courses"] if c["code"] == code), None)
                if hit is not None:
                    for key in ("name", "credit", "kind", "teacher", "period"):
                        if course.get(key) not in (None, ""):
                            hit[key] = course[key]
                    if profile:
                        hit["teacher_profile"] = dict(profile)
                else:
                    # 教务新开、本学期还没选上的课：单独挂在 extra_courses，不参与风险计算
                    extra = s.setdefault("extra_courses", [])
                    if not any(c["code"] == code for c in extra):
                        extra.append({
                            "code": code,
                            "name": course.get("name", ""),
                            "credit": course.get("credit", 0),
                            "kind": course.get("kind", ""),
                            "teacher": course.get("teacher", ""),
                            "period": course.get("period", ""),
                            "teacher_profile": dict(profile) if profile else {},
                            "status": "待开课",
                        })

    # ---------------- 导入 ----------------
    def import_text(self, text: str, known_codes: set[str] | None = None) -> dict:
        total = 0
        ok = 0
        updated = 0
        added = 0
        failed: list[dict] = []
        # 内置课程也算"已存在"，这样首次导入显示的是"更新"而不是"新增"
        known = {c["code"] for c in self.courses} | {c.upper() for c in (known_codes or set())}

        for lineno, raw in enumerate(text.splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if any(h in line for h in HEADER_HINT) and lineno <= 2:
                continue
            total += 1
            cells = _split(line)
            if len(cells) < 2:
                failed.append({"line": lineno, "text": line[:40], "reason": "至少要有课程代码和课程名称"})
                continue

            row = {FIELDS[i]: (cells[i] if i < len(cells) else "") for i in range(len(FIELDS))}
            code, name = row["code"].upper(), row["name"]
            if not re.fullmatch(r"[A-Z]{2,4}\d{2,4}", code):
                failed.append({"line": lineno, "text": line[:40], "reason": f"课程代码「{code}」格式不对，应形如 CS201"})
                continue
            if not name:
                failed.append({"line": lineno, "text": line[:40], "reason": "课程名称不能为空"})
                continue
            try:
                credit = float(row["credit"]) if row["credit"] else 3
                if credit <= 0 or credit > 12:
                    raise ValueError
            except ValueError:
                failed.append({"line": lineno, "text": line[:40], "reason": f"学分「{row['credit']}」应为 0-12 的数字"})
                continue
            if not row["teacher"]:
                failed.append({"line": lineno, "text": line[:40], "reason": "任课教师不能为空"})
                continue
            if row["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", row["email"]):
                failed.append({"line": lineno, "text": line[:40], "reason": f"邮箱「{row['email']}」格式不对"})
                continue

            course = {
                "code": code,
                "name": name,
                "credit": int(credit) if float(credit).is_integer() else credit,
                "kind": row["kind"] or "必修",
                "teacher": row["teacher"],
                "period": row["period"] or "",
            }
            idx = next((i for i, c in enumerate(self.courses) if c["code"] == code), None)
            if idx is not None:
                self.courses[idx] = {**self.courses[idx],
                                     **{k: v for k, v in course.items() if v not in ("", None)}}
            else:
                self.courses.append(course)
            if code in known:
                updated += 1
            else:
                added += 1
                known.add(code)

            profile = self.teachers.setdefault(row["teacher"], {"name": row["teacher"]})
            for key in ("email", "phone", "office", "office_hour"):
                if row[key]:
                    profile[key] = row[key]
            ok += 1

        if ok:
            self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
            self._save()

        return {
            "ok": ok > 0,
            "total": total,
            "ok_count": ok,
            "updated": updated,
            "added": added,
            "failed": failed,
            "persistent": self.persistent,
            "updated_at": self.updated_at,
        }

    # ---------------- 输出 ----------------
    def payload(self, dataset: dict) -> dict:
        rows = []
        for c in dataset["courses"]:
            profile = dataset.get("teachers", {}).get(c.get("teacher", "")) or {}
            rows.append({**c, "teacher_profile": profile})
        return {
            "courses": rows,
            "teachers": list(dataset.get("teachers", {}).values()),
            "updated_at": self.updated_at or dataset["updated_at"],
            "persistent": self.persistent,
        }


CURRICULUM = Curriculum()
