"""「上传文档」背后的一次性解析：任意常见文件 → 一段纯文本。

为什么不复用 `resource_ingest.extract` 就完事：那套解析是为「进知识库」服务的，
只认 txt/md/csv/pdf/docx，碰到 pptx/xlsx 直接判不支持。但学生手里要发给 AI 看的
往往是导出成 Excel 的成绩单、老师发的 PPT 讲义，这两种恰好被挡在外面。

所以这里在它的基础上补两类：
- .pptx：python-pptx 遍历所有形状与表格，按「第 N 页」分段；
- .xlsx：不依赖 openpyxl，直接解 zip 里的 sharedStrings + sheet xml，
  按行拼成 `值 | 值 | 值`，够模型读懂一张成绩表。

统一约定：返回 (正文, 提示)。提示非空表示「文件收到了，但这段内容没进来」，
前端会如实告诉用户，而不是假装读过。
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from engine import resource_ingest

# 一篇文章塞进对话，4000 字已经能覆盖一份讲义的核心；再多只会挤掉系统提示
MAX_CHARS = 4000
XLSX_MAX_ROWS = 120
XLSX_MAX_COLS = 14

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _pptx_text(path: Path) -> tuple[str, str]:
    try:
        from pptx import Presentation
    except Exception:
        return "", "PPT 解析需要 python-pptx"
    try:
        prs = Presentation(str(path))
        out: list[str] = []
        for i, slide in enumerate(prs.slides, 1):
            parts: list[str] = []
            for shape in slide.shapes:
                if getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
                    parts.append(shape.text_frame.text.strip())
                if getattr(shape, "has_table", False):
                    for row in shape.table.rows:
                        cells = [c.text.strip() for c in row.cells]
                        if any(cells):
                            parts.append(" | ".join(cells))
            if parts:
                out.append(f"第 {i} 页\n" + "\n".join(parts))
        text = "\n\n".join(out).strip()
        return (text, "") if text else ("", "这份 PPT 里没有可读的文字（可能都是图片）")
    except Exception as e:  # noqa: BLE001
        return "", f"PPT 解析失败：{e}"


def _col_index(ref: str) -> int:
    """A1 → 0，AB12 → 27。"""
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + (ord(ch.upper()) - 64)
        else:
            break
    return max(0, n - 1)


def _xlsx_text(path: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(path) as z:
            shared: list[str] = []
            if "xl/sharedStrings.xml" in z.namelist():
                root = ET.fromstring(z.read("xl/sharedStrings.xml"))
                for si in root.findall("m:si", NS):
                    shared.append("".join(t.text or "" for t in si.iter(
                        "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")))

            sheets = sorted(n for n in z.namelist()
                            if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
            if not sheets:
                return "", "这个 Excel 里没有工作表"
            out: list[str] = []
            root = ET.fromstring(z.read(sheets[0]))
            for row in root.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"):
                cells: dict[int, str] = {}
                for c in row.findall("m:c", NS):
                    ref = c.get("r") or ""
                    idx = _col_index(ref)
                    if idx >= XLSX_MAX_COLS:
                        continue
                    v = c.find("m:v", NS)
                    is_ = c.find("m:is", NS)
                    if c.get("t") == "s" and v is not None and v.text is not None:
                        try:
                            val = shared[int(v.text)]
                        except (ValueError, IndexError):
                            val = v.text or ""
                    elif is_ is not None:
                        val = "".join(t.text or "" for t in is_.iter(
                            "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))
                    else:
                        val = (v.text if v is not None else "") or ""
                    val = val.strip()
                    if val:
                        cells[idx] = val
                if not cells:
                    continue
                width = max(cells) + 1
                out.append(" | ".join(cells.get(i, "") for i in range(width)))
                if len(out) >= XLSX_MAX_ROWS:
                    out.append("…（表格后面还有内容，只读了前 %d 行）" % XLSX_MAX_ROWS)
                    break
            text = "\n".join(out).strip()
            return (text, "") if text else ("", "这张表里没有读到内容")
    except Exception as e:  # noqa: BLE001
        return "", f"Excel 解析失败：{e}"


def read(path: Path) -> tuple[str, str]:
    """返回 (正文, 提示)。提示非空时正文可能为空。"""
    suffix = path.suffix.lower()
    if suffix == ".pptx":
        text, note = _pptx_text(path)
    elif suffix == ".xlsx":
        text, note = _xlsx_text(path)
    elif suffix == ".xls":
        return "", "旧的 .xls 格式读不了，另存为 .xlsx 再传一次"
    else:
        text, note = resource_ingest.extract(path)

    text = (text or "").strip()
    # 有些 PDF 用 UTF-16 文本字符串，抽取时会带一串 BOM；对模型来说是噪声
    text = text.replace("\ufeff", "")
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n…（后面还有内容，先读到这里）"
    return text, note
