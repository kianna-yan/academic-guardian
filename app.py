"""学业护航 · FastAPI 服务入口。

前端为 Vue 3 + Vite 工程（web/），构建产物在 web/site，由本服务托管。
启动： python -m uvicorn app:app --port 8600
"""
from __future__ import annotations

import copy
import json
import os
import queue
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel

from engine import accounts, curriculum, data, exporter, llm, rag, report as report_mod, trend
from engine.agent import Agent
from engine.letters import class_report, counselor_brief, parent_letter, student_letter
from engine.memory import ConversationMemory
from engine.risk import DEFAULT_CONFIG, RiskEngine

BASE = Path(__file__).resolve().parent
DIST = BASE / "web" / "site"
LEGACY = BASE / "static"
STARTED_AT = time.time()
app = FastAPI(title="学业护航 Academic Guardian")

DATASET = data.db()
CONFIG = copy.deepcopy(DEFAULT_CONFIG)
ENGINE = RiskEngine(DATASET, CONFIG)
KB = rag.kb()
INTERVENTIONS: dict[str, list[dict]] = {}
COUNTER = {"n": 0}
ACCOUNTS = accounts.Accounts(DATASET["students"], BASE / "data" / "accounts.json")
# 教务维护过的课程/教师档案优先于内置默认值
CURRICULUM = curriculum.Curriculum()
CURRICULUM.apply(DATASET)
# 会话记忆：多轮对话的"他 / 第 N 个"靠它消解；按账号隔离
MEMORY = ConversationMemory()


def _record_intervention(sid: str, title: str, note: str, status: str = "已完成") -> dict:
    """对话里说「记录：谈过了」，智能体直接写进干预台账。"""
    COUNTER["n"] += 1
    item = {
        "id": COUNTER["n"],
        "title": title,
        "status": status,
        "note": note,
        "created_at": datetime.now().strftime("%m-%d %H:%M"),
    }
    INTERVENTIONS.setdefault(sid, []).insert(0, item)
    return item


def _make_agent() -> Agent:
    from urllib.parse import quote

    def _send_parent_letter(sid: str) -> dict:
        """对话里的「把家长信发给家长」：SMTP 配置了就真发，否则给 .eml 下载。"""
        letter = _letter_of(sid, "parent")
        to = f"parent.{sid}@example.com"
        res = exporter.send_letter_email(letter, to)
        if not res["ok"]:
            return {"ok": False, "message": f"发送失败：{res.get('error', '未知错误')}"}
        if res["mode"] == "smtp":
            return {"ok": True, "mode": "smtp", "to": to}
        return {"ok": True, "mode": "eml", "to": to,
                "url": f"/api/export/send/{sid}?to={quote(to)}"}

    return Agent(ENGINE, KB, INTERVENTIONS, memory=MEMORY,
                 recorder=_record_intervention,
                 mailer=_send_parent_letter,
                 reporter=lambda: report_mod.daily_report(
                     ENGINE, INTERVENTIONS, week=DATASET.get("week")))


# ---------------------------------------------------------------------------
# 每日预警日报：定时聚合（默认每天 08:00；AG_REPORT_INTERVAL_MIN 设分钟间隔可演示），
# 结果挂在 REPORT_STATE 上，供对话问答、Word 导出与推送复用。
# ---------------------------------------------------------------------------
REPORT_STATE: dict = {"last_run": None, "last_report": None, "runs": 0}


def _build_report() -> dict:
    rep = report_mod.daily_report(ENGINE, INTERVENTIONS, week=DATASET.get("week"))
    REPORT_STATE["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    REPORT_STATE["last_report"] = rep
    REPORT_STATE["runs"] += 1
    return rep


def _report_due(now: datetime) -> bool:
    """到点判断：按天（默认 08:00）或按分钟间隔（演示模式）。"""
    interval_min = os.environ.get("AG_REPORT_INTERVAL_MIN")
    if interval_min:
        return (now - datetime.fromtimestamp(STARTED_AT)).total_seconds() / 60 >= float(interval_min)
    hour = int(os.environ.get("AG_REPORT_HOUR", "8"))
    return now.hour == hour and now.minute < 5


@app.on_event("startup")
async def _report_scheduler():
    """每 30 秒看一眼是否到点；到点就聚合一份日报挂到 REPORT_STATE。"""
    import asyncio

    async def loop():
        last_day = ""
        while True:
            now = datetime.now()
            if _report_due(now) and now.strftime("%Y-%m-%d") != last_day:
                try:
                    rep = _build_report()
                    last_day = now.strftime("%Y-%m-%d")
                    print(f"[日报] {rep['date']} 已生成：{rep['summary'][:48]}…")
                except Exception as exc:  # noqa: BLE001
                    print(f"[日报] 生成失败：{exc}")
            await asyncio.sleep(30)

    asyncio.create_task(loop())


# ---------------------------------------------------------------------------
# 鉴权：四个端各自独立登录，接口按角色隔离
# 公开接口只有健康检查、元信息和登录本身；其余一律要 Bearer token。
# ---------------------------------------------------------------------------
PUBLIC_API = {"/api/health", "/api/meta", "/api/auth/login"}


def _bearer(request: Request) -> str:
    """从请求里取本服务的登录 token。

    线上托管网关会往 `Authorization` 里塞平台自己的 JWT 并覆盖我们带的头，
    所以优先读自定义头 `X-Ag-Token`，其次读 query 的 `ag_token`（网关透传），
    最后才看 Authorization —— 且只认本服务签发的格式（恰好一个"."，JWT 是两个）。
    """
    raw = (request.headers.get("x-ag-token") or "").strip()
    if raw:
        return raw
    raw = (request.query_params.get("ag_token") or "").strip()
    if raw:
        return raw
    raw = (request.headers.get("authorization") or "").strip()
    if raw.lower().startswith("bearer "):
        cand = raw[7:].strip()
        if cand.count(".") == 1:
            return cand
    return ""


def _deny(profile: dict, method: str, path: str) -> str:
    """越权校验：学生只能看自己，家长只能看孩子，教务才有配置与导入权。"""
    role = profile.get("role")
    own = profile.get("sid")
    parts = [p for p in path.strip("/").split("/") if p]
    # parts: ["api", ...]

    def target_sid() -> str | None:
        if len(parts) >= 3 and parts[1] in ("students", "letters"):
            return parts[2]
        if len(parts) >= 3 and parts[1] == "interventions":
            return parts[2]
        # 导出路径：/api/export/letter/{sid}、/api/export/notice/{sid}、/api/export/send/{sid}
        if len(parts) >= 4 and parts[1] == "export" and parts[2] in ("letter", "notice", "send"):
            return parts[3]
        return None

    if role in ("student", "parent"):
        if path == "/api/students":
            return "该账号无查看全校名单的权限"
        if path.startswith("/api/reports"):
            return "该账号无生成班级报告的权限"
        if path == "/api/overview":
            return "该账号无查看全校看板的权限"
        if path == "/api/config" or path.startswith("/api/config/"):
            return "该账号无修改规则的权限"
        if path.startswith("/api/auth/import-students") or path.startswith("/api/auth/accounts"):
            return "该账号无账号管理权限"
        if path.startswith("/api/curriculum"):
            return "该账号无查看课程与教师档案的权限"
        sid = target_sid()
        if sid and sid != own:
            return "只能查看本人/孩子的学业数据"
        if sid and method == "POST" and parts[1] == "interventions" and role == "parent":
            return "家长端仅可查看，不可提交处理记录"
    elif role == "counselor":
        if path == "/api/config" and method == "POST":
            return "只有教务端可以修改预警规则"
        if path.startswith("/api/auth/import-students") or path.startswith("/api/auth/accounts"):
            return "只有教务端可以管理账号"
        if path.startswith("/api/curriculum") and method == "POST":
            return "只有教务端可以维护课程与教师档案"
    return ""


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/") or path in PUBLIC_API:
        return await call_next(request)

    profile = ACCOUNTS.profile_of(_bearer(request))
    if not profile:
        return JSONResponse({"detail": "登录已过期，请重新登录"}, status_code=401)

    denied = _deny(profile, request.method, path)
    if denied:
        return JSONResponse({"detail": denied}, status_code=403)

    request.state.profile = profile
    return await call_next(request)


class ChatIn(BaseModel):
    role: str = "student"
    sid: str | None = None
    message: str


class ConfigIn(BaseModel):
    red_line: float
    yellow_line: float
    absence_warn_ratio: float | None = None
    midterm_fail_trigger: int | None = None


class InterventionIn(BaseModel):
    title: str
    status: str = "进行中"
    note: str = ""


class LoginIn(BaseModel):
    role: str
    account: str
    password: str


class PasswordIn(BaseModel):
    old_password: str
    new_password: str


class ImportIn(BaseModel):
    text: str = ""


def _scope(profile: dict, body: ChatIn) -> tuple[str, str | None]:
    """对话的身份由登录态决定，前端传什么都不能越权。"""
    role = profile.get("role") or "student"
    if role in ("student", "parent"):
        return role, profile.get("sid")
    return role, body.sid


def rebuild():
    global ENGINE
    ENGINE = RiskEngine(DATASET, CONFIG)
    return ENGINE


def _demo_students() -> dict:
    rows = ENGINE.roster()
    student = next((r for r in rows if r["level"] == "yellow" and r["delta"] > 8), rows[60])
    parent = next((r for r in rows if r["level"] == "red"), rows[0])
    return {"student": student["id"], "parent": parent["id"], "counselor": student["id"]}


def _entry_html() -> Path:
    """优先返回 Vite 构建产物；没有构建时回退到旧版 static/，方便随时回滚。"""
    if (DIST / "index.html").exists():
        return DIST / "index.html"
    return LEGACY / "index.html"


# 入口 HTML 绝对不能缓存：一旦浏览器/网关留着上一版 index.html，
# 它引用的 assets/index-<旧hash>.js 会随新部署被删掉，用户看到的就是
# {"detail":"Not Found"} 或白屏。带 hash 的静态资源反而可以长期缓存。
_NO_STORE = {"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}


def _entry_response() -> FileResponse:
    return FileResponse(_entry_html(), headers=_NO_STORE)


@app.get("/")
def index():
    return _entry_response()


@app.post("/api/auth/login")
def auth_login(body: LoginIn):
    try:
        result = ACCOUNTS.login(body.role, body.account, body.password)
    except accounts.AccountError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, **result}


@app.get("/api/auth/me")
def auth_me(request: Request):
    profile = getattr(request.state, "profile", None) or {}
    return {
        "profile": profile,
        "stats": ACCOUNTS.stats(),
        "defaults": accounts.DEFAULT_PASSWORD,
        "staff_accounts": {
            "counselor": accounts.COUNSELOR_ACCOUNT,
            "admin": accounts.ADMIN_ACCOUNT,
        },
    }


@app.post("/api/auth/change-password")
def auth_change_password(body: PasswordIn, request: Request):
    profile = getattr(request.state, "profile", None) or {}
    try:
        updated = ACCOUNTS.change_password(profile, body.old_password, body.new_password)
    except accounts.AccountError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "profile": updated}


@app.get("/api/auth/accounts")
def auth_accounts(limit: int = Query(200, ge=1, le=500)):
    return {"rows": ACCOUNTS.account_list(limit=limit), "stats": ACCOUNTS.stats()}


@app.post("/api/auth/import-students")
def auth_import_students(body: ImportIn):
    try:
        return ACCOUNTS.import_students(body.text)
    except accounts.AccountError as e:
        raise HTTPException(400, str(e))


@app.get("/api/meta")
def meta():
    demo = _demo_students()
    return {
        "roles": [
            {"key": "student", "name": "学生端", "desc": "自查风险 · 补救路径"},
            {"key": "counselor", "name": "辅导员端", "desc": "风险名单 · 谈话跟进"},
            {"key": "admin", "name": "教务端", "desc": "规则配置 · 全校看板"},
            {"key": "parent", "name": "家长端", "desc": "情况沟通 · 家校联动"},
        ],
        "classes": DATASET["classes"],
        "schools": KB.schools(),
        "config": CONFIG,
        "llm": llm.status(),
        "term": DATASET["term"],
        "week": DATASET["week"],
        "demo": demo,
        "student_count": len(DATASET["students"]),
        "updated_at": DATASET["updated_at"],
    }


@app.get("/api/overview")
def overview():
    return ENGINE.overview()


@app.get("/api/students")
def students(
    class_name: str | None = Query(None),
    level: str | None = Query(None),
    limit: int = Query(300, ge=1, le=300),
):
    rows = ENGINE.roster(class_name, level)
    return {"total": len(rows), "rows": rows[:limit]}


@app.get("/api/students/{sid}")
def student_detail(sid: str):
    try:
        s = ENGINE.get(sid)
    except KeyError:
        raise HTTPException(404, "学生不存在")
    r = ENGINE.score(sid)
    plan = ENGINE.advice(sid, r)
    # 成绩走势：班级均分从课程统计里补，避免 trend 模块重复算全校数据
    gt = trend.grade_trend(s)
    for c in gt["courses"]:
        stat = ENGINE.course_stats.get(c["code"])
        if stat:
            c["cohort_avg"] = stat["mean"]
    return {
        "student": {
            "id": s["id"], "name": s["name"], "gender": s["gender"], "class_name": s["class_name"],
            "major": s["major"], "grade": s["grade"], "advisor": s["advisor"], "term": s["term"],
            "credits": s["credits"], "history": s["history"], "engagement": s["engagement"],
        },
        "risk": r,
        "courses": s["courses"],
        "extra_courses": s.get("extra_courses", []),
        "actions": plan["actions"],
        "advice": plan,
        "grade_trend": gt,
        "interventions": INTERVENTIONS.get(sid, []),
    }


@app.get("/api/curriculum")
def curriculum_list():
    return CURRICULUM.payload(DATASET)


@app.post("/api/curriculum/import")
def curriculum_import(body: ImportIn):
    result = CURRICULUM.import_text(body.text or "", {c["code"] for c in DATASET["courses"]})
    if result["ok"]:
        CURRICULUM.apply(DATASET)
        rebuild()
    return result


@app.get("/api/letters/{sid}")
def letters(sid: str, type: str = Query("student")):
    if sid not in {s["id"] for s in DATASET["students"]}:
        raise HTTPException(404, "学生不存在")
    school = CONFIG.get("school")
    if type == "parent":
        return parent_letter(ENGINE, KB, sid, school)
    if type == "counselor":
        return counselor_brief(ENGINE, KB, sid, school)
    return student_letter(ENGINE, KB, sid, school)


@app.get("/api/reports/{class_name}")
def report(class_name: str):
    return class_report(ENGINE, class_name)


@app.get("/api/policy")
def policy(q: str, school: str | None = None):
    hits = KB.search(q, top_k=4, school=school)
    return {"query": q, "hits": hits}


@app.post("/api/chat")
def chat(body: ChatIn, request: Request):
    role, sid = _scope(request.state.profile, body)
    agent = _make_agent()
    return agent.answer(role, sid, body.message, CONFIG.get("school"),
                        profile=request.state.profile)


@app.get("/api/agent/briefing")
def agent_briefing(request: Request):
    """主动简报：各端进页面时智能体先开口，页面是它的仪表盘。"""
    profile = request.state.profile
    role = profile.get("role") or "student"
    sid = profile.get("sid")
    agent = _make_agent()
    return agent.briefing(role, sid, profile)


@app.post("/api/agent/reset")
def agent_reset(request: Request):
    """清空本账号的会话记忆（换个思路重新聊）。"""
    from engine.memory import memory_key
    MEMORY.clear(memory_key(request.state.profile))
    return {"ok": True}


# ---------------------------------------------------------------------------
# 文书导出：Word（家长信/告知函/谈话要点/通知书/台账/日报）+ 学期汇报 PPT + 家长信邮件
# 浏览器 <a> 直接下载走 ag_token query 透传（_bearer 已支持）。
# ---------------------------------------------------------------------------
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _file_stream(buf, filename: str, mime: str) -> StreamingResponse:
    from urllib.parse import quote
    return StreamingResponse(
        buf, media_type=mime,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


def _letter_of(sid: str, letter_type: str) -> dict:
    school = CONFIG.get("school")
    if letter_type == "parent":
        return parent_letter(ENGINE, KB, sid, school)
    if letter_type == "counselor":
        return counselor_brief(ENGINE, KB, sid, school)
    return student_letter(ENGINE, KB, sid, school)


@app.get("/api/export/letter/{sid}")
def export_letter(sid: str, type: str = Query("parent")):
    """家长信 / 告知函 / 谈话要点 → Word（letters.py 原文排版）。"""
    letter = _letter_of(sid, type)
    stamp = datetime.now().strftime("%Y%m%d")
    return _file_stream(exporter.letter_docx(letter),
                        f"{letter['title']}_{stamp}.docx", _DOCX_MIME)


@app.get("/api/export/notice/{sid}")
def export_notice(sid: str):
    """学业预警通知书（存档联 + 回执）→ Word。"""
    stamp = datetime.now().strftime("%Y%m%d")
    s = ENGINE.get(sid)
    return _file_stream(exporter.notice_docx(ENGINE, sid),
                        f"学业预警通知书_{s['name']}_{stamp}.docx", _DOCX_MIME)


@app.get("/api/export/interventions")
def export_interventions(request: Request, sid: str | None = Query(None)):
    """干预台账 → Word。辅导员可带 sid 导单人；教务导全校。"""
    profile = request.state.profile
    if profile.get("role") not in ("counselor", "admin"):
        raise HTTPException(403, "仅辅导员与教务端可导出台账")
    scope = "全部学生"
    data_map = INTERVENTIONS
    if sid:
        data_map = {sid: INTERVENTIONS.get(sid, [])}
        scope = ENGINE.get(sid)["name"]
    return _file_stream(exporter.interventions_docx(data_map, ENGINE, scope=scope),
                        f"学业干预台账_{datetime.now().strftime('%Y%m%d')}.docx", _DOCX_MIME)


@app.get("/api/export/daily-report")
def export_daily_report(request: Request, fresh: int = Query(0)):
    """每日预警日报 → Word。fresh=1 现场重聚合（演示定时任务同款逻辑）。"""
    if request.state.profile.get("role") not in ("counselor", "admin"):
        raise HTTPException(403, "仅辅导员与教务端可导出日报")
    rep = _build_report() if fresh or not REPORT_STATE["last_report"] else REPORT_STATE["last_report"]
    return _file_stream(exporter.daily_report_docx(rep),
                        f"每日预警日报_{rep['date']}.docx", _DOCX_MIME)


@app.get("/api/export/semester")
def export_semester(request: Request):
    """学期汇报 → PPT（6 页：概览/班级排名/重点学生/干预成效/建议）。"""
    if request.state.profile.get("role") not in ("counselor", "admin"):
        raise HTTPException(403, "仅辅导员与教务端可导出学期汇报")
    rep = REPORT_STATE["last_report"] or _build_report()
    return _file_stream(exporter.semester_pptx(rep, ENGINE),
                        f"学业预警学期汇报_{datetime.now().strftime('%Y%m%d')}.pptx", _PPTX_MIME)


@app.get("/api/agent/daily-report")
def agent_daily_report(request: Request):
    """日报 JSON：对话里问「今日日报」与前端卡片都走这里。没有缓存就现场聚合。"""
    if request.state.profile.get("role") not in ("counselor", "admin"):
        raise HTTPException(403, "仅辅导员与教务端可查看日报")
    rep = REPORT_STATE["last_report"] or _build_report()
    return {
        "date": rep["date"], "week": rep["week"], "generated_at": rep["generated_at"],
        "scheduled_at": REPORT_STATE["last_run"], "runs": REPORT_STATE["runs"],
        "summary": rep["summary"], "body": rep["body"],
        "red_top": [{"name": x["name"], "class_name": x["class_name"], "score": x["score"]}
                    for x in rep["red_top"]],
        "rising": [{"name": x["name"], "class_name": x["class_name"],
                    "delta": x["delta"], "score": x["score"]} for x in rep["rising"]],
        "docx_url": "/api/export/daily-report",
        "smtp_configured": exporter.smtp_configured(),
    }


@app.get("/api/export/send/{sid}")
def export_send(sid: str, request: Request, to: str | None = Query(None)):
    """家长信邮件：SMTP（AG_SMTP_*）配置后由对话直接触发真实发送；
    未配置时本端点产出 .eml（收件人已填好，双击即进邮件客户端）——演示环境同样走完闭环。"""
    profile = request.state.profile
    if profile.get("role") not in ("counselor", "admin", "parent"):
        raise HTTPException(403, "学生端不能发送家长信")
    letter = _letter_of(sid, "parent")
    s = ENGINE.get(sid)
    to_addr = (to or "").strip() or f"parent.{sid}@example.com"
    res = exporter.send_letter_email(letter, to_addr)
    if not res["ok"]:
        raise HTTPException(502, f"邮件发送失败：{res.get('error', '未知错误')}")
    if res["mode"] == "smtp":
        return JSONResponse({"mode": "smtp", "ok": True, "to": to_addr,
                             "message": f"家长信已通过邮件发送给 {s['name']} 的家长（{to_addr}）。"})
    stamp = datetime.now().strftime("%Y%m%d")
    return _file_stream(res["eml"], f"家长信_{s['name']}_{stamp}.eml", "message/rfc822")


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _chunks(text: str, size: int = 8):
    for i in range(0, len(text), size):
        yield text[i:i + size]


@app.get("/api/health")
def health():
    """轻量健康检查：沙箱刚唤醒、应用还没监听时，外部探活可以先用它确认。"""
    return {
        "ok": True,
        "pid": os.getpid(),
        "uptime_s": round(time.time() - STARTED_AT, 1),
        "dist": (DIST / "index.html").exists(),
        "legacy": (LEGACY / "index.html").exists(),
    }


@app.post("/api/chat/stream")
def chat_stream(body: ChatIn, request: Request):
    """SSE 流式对话。

    工具调用、回答增量、引用、建议分事件推送；Agent 在独立线程里跑，
    通过队列把中间事件转给生成器，所以"查了什么、查到什么"是实时可见的。
    """
    # 在进入生成器前就把身份定下来：生成器里拿不到 request.state 的可靠性不如这里
    role, sid = _scope(request.state.profile, body)
    profile = dict(request.state.profile)

    def gen():
        started = time.time()
        events: queue.Queue = queue.Queue()
        sentinel = object()
        # 客户端断开后置位，worker 就不再往队列里塞东西，避免线程和队列长期悬挂
        stop = threading.Event()

        def worker():
            try:
                agent = _make_agent()

                def emit(kind, payload):
                    if not stop.is_set():
                        events.put((kind, payload))

                result = agent.answer(
                    role, sid, body.message, CONFIG.get("school"),
                    emit=emit, profile=profile,
                )
                events.put(("final", result))
            except Exception as exc:  # noqa: BLE001
                events.put(("error", {"message": str(exc)}))
            finally:
                events.put(sentinel)

        threading.Thread(target=worker, daemon=True).start()

        final = None
        streamed_by_llm = False
        try:
            while True:
                try:
                    item = events.get(timeout=15)
                except queue.Empty:
                    # 空闲时发一个注释帧，避免隧道/代理把长连接判成挂死
                    yield ": ping\n\n"
                    continue
                if item is sentinel:
                    break
                kind, payload = item
                if kind == "meta":
                    yield _sse("meta", payload)
                elif kind == "thought":
                    yield _sse("thought", payload)
                elif kind == "tool":
                    yield _sse("tool", payload)
                elif kind == "delta":
                    streamed_by_llm = True
                    yield _sse("delta", payload)
                elif kind == "error":
                    yield _sse("error", payload)
                elif kind == "final":
                    final = payload
        finally:
            stop.set()

        if final is None:
            yield _sse("done", {"elapsed_ms": 0})
            return

        # 没有配置大模型时，把确定性回答切块推出，前端同样是流式观感
        if not streamed_by_llm:
            for piece in _chunks(final["reply"]):
                yield _sse("delta", {"text": piece})
                time.sleep(0.012)

        if final.get("citations"):
            yield _sse("citations", final["citations"])
        if final.get("suggestions"):
            yield _sse("suggestions", final["suggestions"])
        yield _sse("done", {
            "elapsed_ms": round((time.time() - started) * 1000, 1),
            "agent_ms": final.get("elapsed_ms", 0),
            "intent": final.get("intent"),
        })

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/config")
def update_config(body: ConfigIn):
    if body.yellow_line >= body.red_line:
        raise HTTPException(400, "黄色线必须低于红色线")
    CONFIG["red_line"] = body.red_line
    CONFIG["yellow_line"] = body.yellow_line
    if body.absence_warn_ratio is not None:
        CONFIG["policy"]["absence_warn_ratio"] = body.absence_warn_ratio
    if body.midterm_fail_trigger is not None:
        CONFIG["policy"]["midterm_fail_trigger"] = body.midterm_fail_trigger
    rebuild()
    o = ENGINE.overview()
    return {"ok": True, "config": CONFIG, "overview": o}


@app.get("/api/config")
def get_config():
    return CONFIG


@app.get("/api/interventions/{sid}")
def list_interventions(sid: str):
    return {"items": INTERVENTIONS.get(sid, [])}


@app.post("/api/interventions/{sid}")
def add_intervention(sid: str, body: InterventionIn):
    if sid not in {s["id"] for s in DATASET["students"]}:
        raise HTTPException(404, "学生不存在")
    COUNTER["n"] += 1
    item = {
        "id": COUNTER["n"],
        "title": body.title,
        "status": body.status,
        "note": body.note,
        "created_at": datetime.now().strftime("%m-%d %H:%M"),
    }
    INTERVENTIONS.setdefault(sid, []).insert(0, item)
    return {"ok": True, "item": item}


class _HashedAssets(StaticFiles):
    """带 hash 的前端资源目录。

    正常情况下直接命中文件。只有当浏览器还拿着上一版 index.html、
    来要一个已经被新部署替换掉的 assets/index-<旧hash>.js 时才会 404 ——
    这时不要回 {"detail":"Not Found"}（页面会白屏或直接把这段 JSON 显示出来），
    而是回一段几行的脚本让页面自己刷新拿最新入口。带次数上限，避免死循环。
    """

    _HEAL = (
        "(function(){try{var k='ag.reload';"
        "var n=+(sessionStorage.getItem(k)||0);"
        "if(n>=2){console.warn('[学业护航] 资源版本仍不一致，请手动刷新页面');return;}"
        "sessionStorage.setItem(k,String(n+1));"
        "console.warn('[学业护航] 前端资源已更新，正在自动刷新');"
        "location.replace(location.pathname+location.search);"
        "}catch(e){location.reload();}})();"
    )

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return Response(
                self._HEAL,
                media_type="application/javascript",
                headers={"Cache-Control": "no-store"},
            )


app.mount("/static", StaticFiles(directory=LEGACY), name="static")

# Vite 构建产物：带 hash 的静态资源单独挂载，index.html 之外的深层路由交给下面的回退
if (DIST / "assets").exists():
    app.mount("/assets", _HashedAssets(directory=DIST / "assets"), name="assets")


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    """Vue Router 用 history 模式，非 API 路径一律交回 index.html。"""
    if full_path.startswith("api/"):
        raise HTTPException(404, "Not Found")
    if (DIST / "index.html").exists():
        target = DIST / full_path
        if full_path and target.is_file():
            return FileResponse(target)
    return _entry_response()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8600")))
