"""教师上传的真题 / 讲义 → 知识库文档。

原来的上传链路只做两件事：文件落盘 `data/teacher_resources/`，元数据写 `index.json`。
学生能下载，但 AI 完全读不到——问「老师发的第三章讲义讲了什么」只能兜底回答。

这里补第三件事：把可解析的文本抽出来，按知识库的格式（front-matter + `## 章节`）
重写成 markdown，放到 `knowledge/resources/res-<rid>.md`，混合检索直接可用。

设计约束
- **解析失败不阻断上传**：文件照样存、照样能下载，只是不进知识库，并把原因回给前端
- 只处理能抽文本的格式；视频 / 压缩包 / 图片跳过（入库没有检索价值，还会灌水索引）
- 生成的文档用 rid 命名，删除资源时一对一清掉，不会留孤儿
"""
from __future__ import annotations

import re
from pathlib import Path

RES_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "resources"

TEXT_SUFFIX = {".txt", ".md", ".markdown", ".csv"}
DOCX_SUFFIX = {".docx"}
PDF_SUFFIX = {".pdf"}

# 单份资料最多入库 6 万字：再多对问答没帮助，却会拖慢索引与检索
MAX_CHARS = 60_000
# 没有小标题的纯文本，按这个字数聚合成一节（约等于一段完整讲解）
SECTION_MAX = 420

# 小标题识别分两档：
# 1) 原文本身带 markdown 井号 → 只认井号，别的一律当正文（最可靠）
# 2) 没有井号才用「第X章 / 一、 / （一）/ 3.1」这类弱标题
#    故意不认「1. 」这种列表编号：试卷里的题号会被误当成章节，把正文切碎
_MD_HEAD = re.compile(r"^#{1,4}\s*\S")
_WEAK_HEAD = re.compile(
    r"^\s*(?:第[一二三四五六七八九十百]+[章节讲部篇]"
    r"|[一二三四五六七八九十]+[、.．]"
    r"|（[一二三四五六七八九十]+）"
    r"|\d+(?:\.\d+)+\s)\S?"
)


def _read_text(path: Path) -> str:
    """文本类直接读：先 utf-8，再退回 gbk（老师们的 Word 导出常是 GBK）。"""
    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return ""


def _pdf_text(path: Path) -> tuple[str, str]:
    try:
        import pypdfium2 as pdfium
    except Exception:
        return "", "PDF 解析需要 pypdfium2（文件已存盘可下载，但没进知识库）"
    try:
        pdf = pdfium.PdfDocument(str(path))
        out = []
        for i in range(len(pdf)):
            page = pdf[i]
            tp = page.get_textpage()
            out.append(tp.get_text_range())
            tp.close()
            page.close()
        pdf.close()
        return "\n".join(out), ""
    except Exception as e:  # 损坏的 PDF、加密 PDF
        return "", f"PDF 解析失败：{e}"


def _docx_text(path: Path) -> tuple[str, str]:
    try:
        from docx import Document
    except Exception:
        return "", "Word 解析需要 python-docx"
    try:
        doc = Document(str(path))
        parts = [p.text for p in doc.paragraphs]
        # 表格里的内容也要抽：真题的答题卡、评分标准常在表里
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells]
                if any(cells):
                    parts.append(" | ".join(cells))
        return "\n".join(x for x in parts if x.strip()), ""
    except Exception as e:
        return "", f"Word 解析失败：{e}"


def extract(path: Path) -> tuple[str, str]:
    """返回 (正文, 错误说明)。错误非空表示没有可入库的文本。"""
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIX:
        return _read_text(path), ""
    if suffix in PDF_SUFFIX:
        return _pdf_text(path)
    if suffix in DOCX_SUFFIX:
        return _docx_text(path)
    return "", f"{suffix or '未知'} 格式暂不支持入库（文件已存盘，学生仍可下载）"


def _auto_title(body: str) -> str:
    first = re.split(r"[。；！？\n]", body.strip())[0].strip()
    first = re.sub(r"^[#\s\-*·]+", "", first)
    if len(first) > 18:
        cut = first[:18]
        # 英文别切出 "Fi" 这种半截词，退到最近的空格
        if re.search(r"[A-Za-z]$", cut) and " " in first[:19]:
            cut = cut.rsplit(" ", 1)[0]
        first = cut
    return (first or "正文").strip()


def _sections(text: str) -> list[tuple[str, str]]:
    """切成 (小标题, 正文) 列表，尽量沿着原文的标题走。"""
    lines = text.splitlines()
    # 原文有 markdown 标题就只按它切；否则才启用弱标题规则
    head_re = _MD_HEAD if any(_MD_HEAD.match(l) for l in lines) else _WEAK_HEAD

    title, buf, out = "", [], []
    for line in lines:
        s = line.strip()
        if s and len(s) <= 40 and head_re.match(line):
            # 上一节有正文才收，避免连续标题把上一节记成空节
            if any(x.strip() for x in buf):
                out.append((title or "全文", "\n".join(buf).strip()))
            title, buf = re.sub(r"^#+\s*", "", s), []
            continue
        buf.append(line)
    if any(x.strip() for x in buf):
        out.append((title or "全文", "\n".join(buf).strip()))
    elif not out and title:
        out.append((title, text.strip()))

    if len(out) > 1:
        return out

    # 没有识别到小标题：按段落聚合成 SECTION_MAX 字一节，标题取首句
    body = "\n".join(buf).strip() or text.strip()
    out, cur = [], ""
    for para in re.split(r"\n\s*\n", body):
        para = para.strip()
        if not para:
            continue
        if cur and len(cur) + len(para) > SECTION_MAX:
            out.append((_auto_title(cur), cur))
            cur = para
        else:
            cur = f"{cur}\n{para}".strip()
    if cur:
        out.append((_auto_title(cur), cur))
    return out


def to_markdown(row: dict, text: str) -> str:
    """按知识库既有格式生成文档：front-matter 用 `键: 值`，正文按 `## 标题` 分节。"""
    filename = (row.get("filename") or "未命名").strip()
    course = (row.get("course") or "").strip() or "课程资料"
    teacher = (row.get("teacher") or "").strip()
    kind = "真题试卷" if row.get("kind") == "exam" else "网课讲义"
    head = [
        f"文件: {course} · {filename}",
        "学校: 教师上传",
        f"类型: {kind}",
    ]
    if teacher:
        head.append(f"上传教师: {teacher}")
    if row.get("created_at"):
        head.append(f"上传时间: {row['created_at']}")
    if row.get("note"):
        head.append(f"备注: {row['note']}")

    lines = head + [""]
    for title, body in _sections(text)[:80]:
        lines.append(f"## {title}")
        lines.append(body)
        lines.append("")
    return "\n".join(lines)


def doc_path(rid: str) -> Path:
    return RES_DIR / f"res-{rid}.md"


def ingest(row: dict, stored_path: Path) -> dict:
    """把一份上传文件写进知识库。返回给前端展示的结果，不抛异常。"""
    rid = (row.get("id") or "").strip()
    if not rid:
        return {"ok": False, "note": "缺少资源 id，未入库"}

    text, err = extract(stored_path)
    if err:
        return {"ok": False, "note": err}

    text = text.strip()
    if len(text) < 20:
        return {"ok": False, "note": "抽取到的正文太少（可能是扫描件或图片型 PDF），未入库"}
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]

    try:
        RES_DIR.mkdir(parents=True, exist_ok=True)
        md = to_markdown(row, text)
        path = doc_path(rid)
        path.write_text(md, encoding="utf-8")
    except OSError as e:
        return {"ok": False, "note": f"写入知识库失败：{e}"}

    return {
        "ok": True,
        "note": "",
        "doc": path.name,
        "chars": len(text),
        "sections": md.count("\n## "),
    }


def remove(rid: str) -> bool:
    """删除资源时同步清掉知识库文档，避免留下检索得到、点开却是已删资源的引用。"""
    path = doc_path(rid)
    try:
        if path.exists():
            path.unlink()
            return True
    except OSError:
        pass
    return False


def prune(valid_ids: set[str]) -> int:
    """清掉没有对应资源记录的孤儿文档（比如手工删了 index.json）。"""
    if not RES_DIR.is_dir():
        return 0
    n = 0
    for path in RES_DIR.glob("res-*.md"):
        rid = path.stem[4:]
        if rid not in valid_ids:
            try:
                path.unlink()
                n += 1
            except OSError:
                pass
    return n


def count() -> int:
    if not RES_DIR.is_dir():
        return 0
    return len(list(RES_DIR.glob("res-*.md")))
