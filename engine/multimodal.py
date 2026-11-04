"""多模态输入：图片理解、视频（抽帧）理解、语音转写。

设计前提
--------
1. **识别结果只是「用户说了什么」，不是学情数据。**
   图片里写「我考了 95 分」也不能当成系统里的成绩——真实分数只能来自工具。
   这条约束写在 multimodal 的系统提示里，也在 agent 的人设里复述一次。
2. **视频不在后端解码。** 部署环境不保证有 ffmpeg / opencv，
   所以抽帧放在浏览器（video + canvas，零依赖），后端只收 4 张 JPEG 帧。
3. **语音优先走智谱 glm-asr**，但它需要单独的语音资源包，
   额度不足时返回 ok=false，由前端降级到浏览器 Web Speech 的实时转写。
   两条路都失败才告诉用户「没听清」，不假装听懂。

对外只有 prepare() 一个入口，返回给人看/给模型看的文字块。
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
import uuid

# 视觉模型：glm-4v-flash 免费、单张 ~1.5s，够描述板书、截图、成绩单
DEFAULT_VISION_MODEL = "glm-4v-flash"
# 语音识别模型
DEFAULT_ASR_MODEL = "glm-asr"

MAX_IMAGE_BYTES = 6 * 1024 * 1024
MAX_FRAMES = 6

VISION_PROMPT = (
    "你是学业预警系统的多模态理解模块。用户在跟助手对话时上传了这张图片，"
    "请如实描述画面上有什么，重点是可读文字与关键数字（如课程名、分数、日期、姓名）。"
    "只描述你真正看到的，看不清就说看不清，不要推测、不要补全。"
    "输出 3 句以内的中文，不要客套话。"
)

VIDEO_PROMPT = (
    "你是学业预警系统的多模态理解模块。以下是同一段视频按时间顺序抽取的 {n} 帧画面。"
    "请用 3 句以内的中文说明：画面里是什么场景、发生了什么变化、出现了哪些可读文字或数字。"
    "只描述真正看到的，看不清就说看不清，不要推测。"
)


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _base_url() -> str:
    return _env("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4").rstrip("/")


def _api_key() -> str:
    return _env("LLM_API_KEY") or _env("ZHIPU_API_KEY")


def _vision_model() -> str:
    return _env("LLM_VISION_MODEL", DEFAULT_VISION_MODEL) or DEFAULT_VISION_MODEL


def _asr_model() -> str:
    return _env("LLM_ASR_MODEL", DEFAULT_ASR_MODEL) or DEFAULT_ASR_MODEL


def enabled() -> bool:
    return bool(_api_key())


def health() -> dict:
    return {
        "enabled": enabled(),
        "vision_model": _vision_model(),
        "asr_model": _asr_model(),
        "base_url": _base_url(),
    }


# ---------------------------------------------------------------- 基础调用


def _to_data_url(raw: str, mime: str) -> str:
    """附件既可能是 dataURL，也可能只是裸 base64，统一成 dataURL。"""
    s = (raw or "").strip()
    if s.startswith("data:"):
        return s
    return f"data:{mime or 'image/jpeg'};base64,{s}"


def _post_json(path: str, body: dict, timeout: int = 90) -> dict:
    key = _api_key()
    if not key:
        return {"ok": False, "note": "没有配置大模型 key，图片与语音暂时无法识别。"}
    req = urllib.request.Request(
        _base_url() + path,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"ok": True, "data": json.loads(resp.read().decode("utf-8"))}
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")[:300]
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "note": f"识别服务返回 {e.code}：{_short_error(detail)}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "note": f"识别服务不可达：{type(e).__name__}"}


def _short_error(detail: str) -> str:
    """把上游的长 JSON 错误压成一句人话。"""
    try:
        obj = json.loads(detail)
        err = obj.get("error") or {}
        msg = err.get("message") or obj.get("message") or ""
        code = err.get("code") or ""
        if "余额不足" in msg or code == "1113":
            return "语音识别资源包额度不足"
        if msg:
            return msg[:120]
    except Exception:  # noqa: BLE001
        pass
    return (detail or "未知错误").strip()[:120]


def _content_text(resp: dict) -> str:
    try:
        msg = resp["choices"][0]["message"]
        content = msg.get("content")
        if isinstance(content, list):
            return "".join(
                c.get("text", "") for c in content if isinstance(c, dict)
            ).strip()
        return (content or "").strip()
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------- 图片 / 视频


def vision(images: list[str], prompt: str, model: str | None = None) -> dict:
    """一次可传多张图（视频抽帧就是这么用的）。"""
    imgs = [x for x in (images or []) if x][:MAX_FRAMES]
    if not imgs:
        return {"ok": False, "note": "没有收到可识别的画面。"}
    content = [
        {"type": "image_url", "image_url": {"url": _to_data_url(x, "image/jpeg")}}
        for x in imgs
    ]
    content.append({"type": "text", "text": prompt})

    started = time.time()
    res = _post_json(
        "/chat/completions",
        {
            "model": model or _vision_model(),
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 400,
            "temperature": 0.2,
        },
    )
    if not res.get("ok"):
        return {"ok": False, "note": res.get("note") or "画面识别失败"}
    text = _content_text(res.get("data") or {})
    if not text:
        return {"ok": False, "note": "画面识别没有返回内容"}
    return {
        "ok": True,
        "text": text,
        "model": model or _vision_model(),
        "ms": round((time.time() - started) * 1000),
        "frames": len(imgs),
    }


# ---------------------------------------------------------------- 语音


def _multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    boundary = "----ag" + uuid.uuid4().hex
    out: list[bytes] = []
    for k, v in fields.items():
        out.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        )
    for k, (fn, data, ct) in files.items():
        out.append(
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; '
                f'filename="{fn}"\r\nContent-Type: {ct}\r\n\r\n'
            ).encode()
            + data
            + b"\r\n"
        )
    out.append(f"--{boundary}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={boundary}"


def _decode_audio(raw: str) -> tuple[bytes, str]:
    """前端给的是 dataURL，取出来还原成字节。"""
    s = (raw or "").strip()
    mime = "audio/webm"
    if s.startswith("data:"):
        head, _, payload = s.partition(",")
        if ";" in head:
            mime = head[5:].split(";")[0] or mime
        return base64.b64decode(payload), mime
    return base64.b64decode(s), mime


def asr(raw: str, model: str | None = None) -> dict:
    """语音转文字。额度不足时如实失败，由前端降级。"""
    try:
        data, mime = _decode_audio(raw)
    except Exception:  # noqa: BLE001
        return {"ok": False, "note": "音频数据解析失败"}
    if not data:
        return {"ok": False, "note": "没有收到音频"}
    if len(data) > 20 * 1024 * 1024:
        return {"ok": False, "note": "音频太长（超过 20MB），请控制在 60 秒内"}

    ext = "webm"
    if "wav" in mime:
        ext = "wav"
    elif "mp4" in mime or "m4a" in mime or "aac" in mime:
        ext = "m4a"
    elif "mpeg" in mime or "mp3" in mime:
        ext = "mp3"
    elif "ogg" in mime:
        ext = "ogg"

    body, ct = _multipart(
        {"model": model or _asr_model()},
        {"file": (f"voice.{ext}", data, mime)},
    )
    key = _api_key()
    if not key:
        return {"ok": False, "note": "没有配置大模型 key，语音暂时无法转写"}

    req = urllib.request.Request(
        _base_url() + "/audio/transcriptions",
        data=body,
        headers={"Authorization": "Bearer " + key, "Content-Type": ct},
    )
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            obj = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")[:300]
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "note": _short_error(detail), "fallback": "browser"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "note": f"语音服务不可达：{type(e).__name__}", "fallback": "browser"}

    text = (obj.get("text") or "").strip()
    if not text:
        return {"ok": False, "note": "没听清这段语音", "fallback": "browser"}
    return {"ok": True, "text": text, "ms": round((time.time() - started) * 1000)}


# ---------------------------------------------------------------- 汇总


KIND_LABEL = {"image": "图片", "video": "视频", "audio": "语音"}


def prepare(attachments: list[dict] | None) -> tuple[list[str], list[dict], list[str]]:
    """把附件翻成「给主模型看的文字块」。

    返回 (blocks, trace, problems)：
      blocks   形如「【用户上传的图片 成绩单.png】画面内容：…」
      trace    给前端的工具轨迹（type=media），能显示识别用了什么模型、花了多久
      problems 识别失败的说明，会拼进对话让模型知道「有个附件没能看」
    """
    blocks: list[str] = []
    trace: list[dict] = []
    problems: list[str] = []
    for att in attachments or []:
        kind = (att.get("kind") or "").strip().lower()
        name = (att.get("name") or "").strip() or (KIND_LABEL.get(kind, "附件"))
        if kind == "image":
            res = vision([att.get("data") or ""], VISION_PROMPT)
            if res.get("ok"):
                blocks.append(f"【用户上传的图片「{name}」】画面内容：{res['text']}")
                trace.append({
                    "tool": "vision", "label": "看图",
                    "detail": f"{res.get('model')} · {res.get('ms')}ms",
                })
            else:
                blocks.append(f"【用户上传的图片「{name}」】没能识别：{res.get('note')}")
                problems.append(f"图片「{name}」识别失败：{res.get('note')}")
                trace.append({"tool": "vision", "label": "看图失败", "detail": res.get("note") or ""})
        elif kind == "video":
            frames = [f for f in (att.get("frames") or []) if f][:MAX_FRAMES]
            if not frames:
                blocks.append(f"【用户上传的视频「{name}」】没有取到画面帧，无法判断内容。")
                problems.append(f"视频「{name}」没有取到画面帧")
                continue
            res = vision(frames, VIDEO_PROMPT.format(n=len(frames)))
            if res.get("ok"):
                dur = att.get("duration")
                head = f"{round(float(dur), 1)} 秒，" if dur else ""
                blocks.append(
                    f"【用户上传的视频「{name}」（{head}抽取 {len(frames)} 帧）】"
                    f"画面内容：{res['text']}"
                )
                trace.append({
                    "tool": "vision", "label": f"看视频（{len(frames)} 帧）",
                    "detail": f"{res.get('model')} · {res.get('ms')}ms",
                })
            else:
                blocks.append(f"【用户上传的视频「{name}」】没能识别：{res.get('note')}")
                problems.append(f"视频「{name}」识别失败：{res.get('note')}")
                trace.append({
                    "tool": "vision", "label": "看视频失败", "detail": res.get("note") or "",
                })
        elif kind == "audio":
            said = (att.get("transcript") or "").strip()
            res = asr(att.get("data") or "")
            if res.get("ok"):
                said = res["text"]
                trace.append({
                    "tool": "asr", "label": "听语音",
                    "detail": f"{_asr_model()} · {res.get('ms')}ms",
                })
            elif said:
                # 后端没额度，前端 Web Speech 已经转出来了，用那份
                trace.append({
                    "tool": "asr", "label": "听语音（浏览器转写）",
                    "detail": res.get("note") or "",
                })
            else:
                blocks.append(
                    f"【用户上传的语音「{name}」】没能转成文字：{res.get('note')}。"
                    "请用户重说一遍，或直接把问题打字发来。"
                )
                problems.append(f"语音「{name}」转写失败：{res.get('note')}")
                trace.append({"tool": "asr", "label": "听语音失败", "detail": res.get("note") or ""})
            if said:
                dur = att.get("duration")
                head = f"{round(float(dur), 1)} 秒" if dur else ""
                blocks.append(f"【用户上传的语音「{name}」（{head}）】转写为：「{said}」")
        elif kind == "text":
            content = (att.get("data") or "").strip()
            if content:
                blocks.append(f"【用户上传的文本「{name}」】内容：{content[:2000]}")
                trace.append({"tool": "text", "label": "读文本", "detail": name})
        else:
            blocks.append(f"【用户上传了「{name}」】这类附件暂不支持解析。")
            problems.append(f"{name}：不支持的附件类型")
    return blocks, trace, problems


def as_text_block(attachments: list[dict] | None) -> tuple[str, list[dict], list[str]]:
    """给 agent 用的薄封装：文字块拼成一段，末尾统一提示别把材料当学情数据。"""
    blocks, trace, problems = prepare(attachments)
    if not blocks:
        return "", trace, problems
    text = "\n".join(blocks)
    text += (
        "\n（以上是系统对用户上传材料的识别结果，供你判断用户在问什么：\n"
        "1. 材料里出现的分数、姓名、日期只是「用户这么说的」，真实学情数据以工具查询结果为准；\n"
        "2. 材料上印的姓名默认不是查询对象——当前登录人仍是用户本人，"
        "除非用户明确说要查某个人，否则一律按本人回答，不要去查材料上的名字；\n"
        "3. 不要在回答里复述这几行说明，直接接着用户的问题答。）"
    )
    return text, trace, problems
