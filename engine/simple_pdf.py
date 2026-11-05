"""不装依赖也能出中文 PDF。

线上环境只有 fastapi / uvicorn / python-docx / python-pptx，没有 reportlab，
也没有能嵌进 PDF 的中文字体文件。「为了一个下载按钮去装 reportlab + 传 10MB
字体」在演示现场是负担，所以这里手写一个够用的 PDF 生成器：

- 字体用 PDF 内置的 **STSong-Light + UniGB-UCS2-H**（Adobe 中文 CID 字体，
  Acrobat / Chrome / Edge / WPS 的阅读器都自带映射），不需要嵌入字体文件；
- 文本按 UCS-2（UTF-16BE）十六进制字符串写入，中文不会变方块；
- 只做左对齐的段落排版：自动换行、自动分页、标题/正文两级字号，
  加粗用「填充 + 描边」的文字渲染模式模拟（PDF 里没有真正的伪粗体，这是通行写法）；
- 输出 A4、页边距 56pt、页脚带页码。

这不是通用排版引擎：表格、图片、多栏都不支持。学情报告这种"标题 + 条目"
的版式够用，也是它唯一的用途。
"""
from __future__ import annotations

A4_W = 595
A4_H = 842
MARGIN_X = 56
MARGIN_TOP = 62
MARGIN_BOTTOM = 62
FONT = "STSong-Light"

# 中文按 1 个字宽算，ASCII 约 0.52；用这个估算值换行，不追求像素级精确
_ASCII_W = 0.52


def _hex(text: str) -> str:
    """PDF 文本字符串：UTF-16BE + BOM，包成 <FEFF....>。"""
    return "<FEFF" + text.encode("utf-16-be", errors="replace").hex().upper() + ">"


def _text_width(text: str, size: float) -> float:
    w = 0.0
    for ch in text:
        w += _ASCII_W if ord(ch) < 128 else 1.0
    return w * size


def _wrap(text: str, size: float, width: float) -> list[str]:
    """按估算宽度折行。中文按字符断，英文尽量在空格处断。"""
    out: list[str] = []
    for para in text.replace("\r", "").split("\n"):
        if not para.strip():
            out.append("")
            continue
        line = ""
        for ch in para:
            if _text_width(line + ch, size) <= width:
                line += ch
                continue
            # 这一行放不下了：英文退到最近的空格，中文直接断
            if ord(ch) < 128 and " " in line:
                sp = line.rfind(" ")
                if sp > 0:
                    out.append(line[:sp])
                    line = line[sp + 1:] + ch
                    continue
            out.append(line.rstrip())
            line = ch
        if line:
            out.append(line)
    return out


class _Doc:
    def __init__(self) -> None:
        self.pages: list[list[str]] = []
        self.ops: list[str] = []
        self.y = A4_H - MARGIN_TOP

    # ---------- 基础绘制 ----------
    def _new_page(self) -> None:
        if self.ops:
            self.pages.append(self.ops)
        self.ops = []
        self.y = A4_H - MARGIN_TOP

    def _room(self, h: float) -> None:
        if self.y - h < MARGIN_BOTTOM:
            self._new_page()

    def line(self, text: str, size: float = 10.5, bold: bool = False,
             color: tuple[float, float, float] = (0.23, 0.18, 0.14),
             indent: float = 0, before: float = 0, after: float = 0) -> None:
        """写一段（可能折成多行）文本。"""
        width = A4_W - MARGIN_X * 2 - indent
        rows = _wrap(text, size, width) if text else [""]
        leading = round(size * 1.62, 2)
        if before:
            self.y -= before
        for row in rows:
            self._room(leading)
            self.y -= leading
            if not row:
                continue
            r = f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg"
            tr = "2 Tr 0.32 w" if bold else "0 Tr"
            self.ops.append(
                f"q {r} BT /{'F2' if bold else 'F1'} {size} Tf {tr} "
                f"{MARGIN_X + indent} {self.y:.2f} Td {_hex(row)} Tj ET Q"
            )
        if after:
            self.y -= after

    def gap(self, h: float) -> None:
        self.y -= h

    def rule(self) -> None:
        """一条细分割线（用来分开页眉与正文）。"""
        self._room(10)
        self.y -= 6
        self.ops.append(
            f"q 0.85 0.80 0.74 RG 0.6 w {MARGIN_X} {self.y:.2f} m "
            f"{A4_W - MARGIN_X} {self.y:.2f} l S Q"
        )
        self.y -= 4

    def page_break(self) -> None:
        self._new_page()

    # ---------- 输出 ----------
    def build(self, footer: str = "") -> bytes:
        if self.ops:
            self.pages.append(self.ops)
            self.ops = []

        # 页脚：页码 + 一句来源说明
        for i, ops in enumerate(self.pages, 1):
            foot = f"{footer}    第 {i} / {len(self.pages)} 页" if footer else f"第 {i} / {len(self.pages)} 页"
            ops.append(
                f"q 0.55 0.50 0.45 rg BT /F1 8.5 Tf 0 Tr "
                f"{MARGIN_X} 34 Td {_hex(foot)} Tj ET Q"
            )

        objs: list[bytes] = []

        def add(body: bytes) -> int:
            objs.append(body)
            return len(objs)  # 1-based

        # 1 catalog / 2 pages / 3-4 F1 / 5-6 F2 固定占位，稍后回填 pages 的 Kids
        add(b"")  # 1
        add(b"")  # 2
        add(f"<</Type/Font/Subtype/Type0/BaseFont/{FONT}/Encoding/UniGB-UCS2-H"
            f"/DescendantFonts[4 0 R]>>".encode())  # 3
        # /W[1 95 500]：UniGB-UCS2-H 下 ASCII（CID 1-95）按半角 500 宽。
        # 少了这行，阅读器一律按 /DW 1000 排，数字和英文会被拉成全角，整篇字距发虚。
        add(f"<</Type/Font/Subtype/CIDFontType0/BaseFont/{FONT}"
            f"/CIDSystemInfo<</Registry(Adobe)/Ordering(GB1)/Supplement 2>>"
            f"/FontDescriptor 7 0 R/DW 1000/W[1 95 500]>>".encode())  # 4
        add(f"<</Type/Font/Subtype/Type0/BaseFont/{FONT}/Encoding/UniGB-UCS2-H"
            f"/DescendantFonts[6 0 R]>>".encode())  # 5
        add(f"<</Type/Font/Subtype/CIDFontType0/BaseFont/{FONT}"
            f"/CIDSystemInfo<</Registry(Adobe)/Ordering(GB1)/Supplement 2>>"
            f"/FontDescriptor 7 0 R/DW 1000/W[1 95 500]>>".encode())  # 6
        # 7 字体描述：没有它，严格的阅读器（Preview / 部分打印机驱动）可能不肯显示
        add(b"<</Type/FontDescriptor/FontName/STSong-Light/Flags 6"
            b"/FontBBox[-25 -254 1000 880]/ItalicAngle 0/Ascent 880/Descent -120"
            b"/CapHeight 880/StemV 93>>")  # 7

        kids: list[str] = []
        for ops in self.pages:
            stream = "\n".join(ops).encode("latin-1", errors="replace")
            content_id = add(
                b"<</Length " + str(len(stream)).encode() + b">>\nstream\n" + stream + b"\nendstream"
            )
            page_id = add(
                f"<</Type/Page/Parent 2 0 R/MediaBox[0 0 {A4_W} {A4_H}]"
                f"/Resources<</Font<</F1 3 0 R/F2 5 0 R>>>>"
                f"/Contents {content_id} 0 R>>".encode()
            )
            kids.append(f"{page_id} 0 R")

        objs[0] = b"<</Type/Catalog/Pages 2 0 R>>"
        objs[1] = (
            f"<</Type/Pages/Count {len(self.pages)}/Kids[{' '.join(kids)}]>>".encode()
        )

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets: list[int] = []
        for i, body in enumerate(objs, 1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"

        xref_at = len(out)
        out += f"xref\n0 {len(objs) + 1}\n".encode()
        out += b"0000000000 65535 f \n"
        for off in offsets:
            out += f"{off:010d} 00000 n \n".encode()
        out += (
            f"trailer\n<</Size {len(objs) + 1}/Root 1 0 R>>\nstartxref\n{xref_at}\n%%EOF\n"
        ).encode()
        return bytes(out)


def build_pdf(title: str, subtitle: str, sections: list[tuple[str, list[str]]],
              footer: str = "") -> bytes:
    """把「标题 + 若干（小标题, 条目）小节」排成一份 A4 PDF。"""
    doc = _Doc()
    doc.line(title, size=20, bold=True, color=(0.76, 0.25, 0.05), after=2)
    if subtitle:
        doc.line(subtitle, size=9.5, color=(0.55, 0.50, 0.45))
    doc.rule()

    for head, items in sections:
        doc.line(head, size=12.5, bold=True, color=(0.30, 0.22, 0.16), before=8, after=1)
        for it in items:
            if it.startswith("- "):
                doc.line("· " + it[2:], size=10.5, indent=10)
            elif it.startswith("  "):
                doc.line(it.strip(), size=9.8, indent=22, color=(0.42, 0.36, 0.30))
            else:
                doc.line(it, size=10.5, indent=4)
        doc.gap(2)

    return doc.build(footer)
