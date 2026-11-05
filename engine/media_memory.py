"""会话级材料记忆：让「刚才那张图」在被追问时还能答。

为什么单独做一层
- 多模态识别结果只拼在「当轮提问」里，下一轮就没了。用户发完成绩单问
  「这学期哪门最危险」，紧接着问「那数学呢」，模型手上已经没有那张图了，
  只能回「我没有看到图片」——这不是模型失忆，是我们没把材料留进会话。
- 所以这里按账号存一份「最近发过的材料」：识别出来的文字 + 原图字节。
  下一轮追问时，文字直接回灌给主模型；问到具体数字/行/名字这类细节，
  再把原图重新送一次视觉模型，按新问题复核一遍——用原文答，不靠猜。

边界
- 只存最近 MAX_ITEMS 次，图片最多留 MAX_IMAGES 张、总字节封顶 MAX_BYTES，
  纯内存、按账号隔离，重启即失效，和 ConversationMemory 同一套生命周期约定。
- 材料里的分数、姓名仍然只当「用户这么说」，学情数据一律以工具查询为准。
"""
from __future__ import annotations

import threading
import time

MAX_ITEMS = 6
MAX_IMAGES = 4
MAX_BYTES = 8 * 1024 * 1024

# 追问材料时会出现的说法：出现任何一个，才把会话里的材料翻出来
RECALL_HINTS = (
    "图", "照片", "截图", "这张", "那张", "刚才", "刚刚", "上面", "上面那",
    "视频", "语音", "录音", "材料", "文档", "表里", "表格里", "单子", "原件",
)

# 问细节的说法：命中就把原图重新看一遍，而不是只复述上次的概括
DETAIL_HINTS = (
    "多少", "几", "第", "哪一", "哪个", "哪门", "写", "名字", "日期", "分数",
    "行", "列", "表", "合计", "总", "几门", "具体", "原文", "再仔细", "看清楚",
)


class MediaMemory:
    def __init__(self, max_items: int = MAX_ITEMS):
        self._max = max_items
        self._store: dict[str, list[dict]] = {}
        self._lock = threading.Lock()

    # ---------- 写 ----------
    def remember(self, key: str, attachments: list[dict] | None, summary: str) -> dict | None:
        """记一轮材料。summary 是当轮识别出的文字块，原图另存一份供追问复核。"""
        if not key or not summary:
            return None
        items: list[dict] = []
        images: list[dict] = []
        total = 0
        for att in attachments or []:
            kind = (att.get("kind") or "").strip().lower()
            name = (att.get("name") or "").strip()
            items.append({"kind": kind, "name": name})
            if kind == "image" and att.get("data"):
                blob = str(att["data"])
                if total + len(blob) <= MAX_BYTES and len(images) < MAX_IMAGES:
                    images.append({"name": name or "图片", "data": blob})
                    total += len(blob)
            elif kind == "video":
                for i, frame in enumerate((att.get("frames") or [])[:MAX_IMAGES]):
                    if not frame:
                        continue
                    blob = str(frame)
                    if total + len(blob) > MAX_BYTES or len(images) >= MAX_IMAGES:
                        break
                    images.append({"name": f"{name or '视频'} 第{i + 1}帧", "data": blob})
                    total += len(blob)
        record = {
            "ts": time.strftime("%H:%M:%S"),
            "kinds": sorted({i["kind"] for i in items if i["kind"]}),
            "items": items,
            "summary": summary,
            "images": images,
        }
        with self._lock:
            rows = self._store.setdefault(key, [])
            rows.append(record)
            if len(rows) > self._max:
                del rows[: len(rows) - self._max]
        return record

    # ---------- 读 ----------
    def latest(self, key: str) -> dict | None:
        with self._lock:
            rows = self._store.get(key) or []
            return rows[-1] if rows else None

    def count(self, key: str) -> int:
        with self._lock:
            return len(self._store.get(key) or [])

    def clear(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)


_STORE: MediaMemory | None = None
_STORE_LOCK = threading.Lock()


def media_memory() -> MediaMemory:
    """进程级单例：Agent 按请求新建，材料记忆必须活在请求之外。"""
    global _STORE
    if _STORE is None:
        with _STORE_LOCK:
            if _STORE is None:
                _STORE = MediaMemory()
    return _STORE


def wants_recall(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return any(h in t for h in RECALL_HINTS)


def wants_detail(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return any(h in t for h in DETAIL_HINTS) or len(t) <= 12


def as_block(record: dict, question: str = "", reread: str = "") -> str:
    """把材料记忆拼成给主模型看的一段话。"""
    kinds = record.get("kinds") or []
    label = "、".join({"image": "图片", "video": "视频", "audio": "语音"}.get(k, k) for k in kinds) or "附件"
    lines = [f"【本会话之前发过的{label}（{record.get('ts', '')}，不是这一轮新发的）】{record.get('summary', '')}"]
    if reread:
        lines.append(
            "【按用户这次追问，又把原图重新看了一遍，以下是图片原文里查到的内容】"
            f"{reread}"
        )
    lines.append(
        "（追问材料时以上面这两段为准：能直接答就直接答，不要说你没看到图片；"
        "如果材料上的数字与系统查询结果不一致，两个都写出来——材料上写的是多少、"
        "系统里记的是多少，并说明学情数据以系统为准；"
        "材料里的分数、姓名仍然只当用户这么说，不要拿它去覆盖系统数据；"
        "不要复述这几行说明。）"
    )
    return "\n".join(lines)
