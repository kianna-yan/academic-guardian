"""学业护航 · FastAPI 服务入口。

前端为 Vue 3 + Vite 工程（web/），构建产物在 web/dist，由本服务托管。
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

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from engine import data, llm, rag
from engine.agent import Agent
from engine.letters import class_report, counselor_brief, parent_letter, student_letter
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


@app.get("/")
def index():
    return FileResponse(_entry_html())


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
    return {
        "student": {
            "id": s["id"], "name": s["name"], "gender": s["gender"], "class_name": s["class_name"],
            "major": s["major"], "grade": s["grade"], "advisor": s["advisor"], "term": s["term"],
            "credits": s["credits"], "history": s["history"], "engagement": s["engagement"],
        },
        "risk": r,
        "courses": s["courses"],
        "actions": ENGINE.interventions(sid),
        "interventions": INTERVENTIONS.get(sid, []),
    }


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
def chat(body: ChatIn):
    agent = Agent(ENGINE, KB, INTERVENTIONS)
    return agent.answer(body.role, body.sid, body.message, CONFIG.get("school"))


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
def chat_stream(body: ChatIn):
    """SSE 流式对话。

    工具调用、回答增量、引用、建议分事件推送；Agent 在独立线程里跑，
    通过队列把中间事件转给生成器，所以"查了什么、查到什么"是实时可见的。
    """

    def gen():
        started = time.time()
        events: queue.Queue = queue.Queue()
        sentinel = object()
        # 客户端断开后置位，worker 就不再往队列里塞东西，避免线程和队列长期悬挂
        stop = threading.Event()

        def worker():
            try:
                agent = Agent(ENGINE, KB, INTERVENTIONS)

                def emit(kind, payload):
                    if not stop.is_set():
                        events.put((kind, payload))

                result = agent.answer(
                    body.role, body.sid, body.message, CONFIG.get("school"),
                    emit=emit,
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


app.mount("/static", StaticFiles(directory=LEGACY), name="static")

# Vite 构建产物：带 hash 的静态资源单独挂载，index.html 之外的深层路由交给下面的回退
if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    """Vue Router 用 history 模式，非 API 路径一律交回 index.html。"""
    if full_path.startswith("api/"):
        raise HTTPException(404, "Not Found")
    if (DIST / "index.html").exists():
        target = DIST / full_path
        if full_path and target.is_file():
            return FileResponse(target)
    return FileResponse(_entry_html())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8600")))
