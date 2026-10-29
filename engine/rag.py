"""校规知识库检索（BM25）。

不用向量库是为了让项目零外部依赖就能跑；接口保持与向量检索一致，
换成 embedding 方案时只替换 search() 内部实现即可。
"""
from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

KB_DIR = Path(__file__).resolve().parent.parent / "knowledge"

_WORD_RE = re.compile(r"[a-zA-Z]+|\d+")
_CJK_RE = re.compile(r"[\u4e00-\u9fa5]")


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens = _WORD_RE.findall(text)
    cjk = _CJK_RE.findall(text)
    tokens += ["".join(cjk[i:i + 2]) for i in range(len(cjk) - 1)]
    tokens += cjk
    return tokens


class KnowledgeBase:
    def __init__(self, kb_dir: Path = KB_DIR):
        self.chunks: list[dict] = []
        self._load(kb_dir)
        self._index()

    def _load(self, kb_dir: Path) -> None:
        for path in sorted(kb_dir.glob("*.md")):
            raw = path.read_text(encoding="utf-8")
            header = {}
            body_start = 0
            for line in raw.splitlines():
                if line.startswith("## "):
                    break
                if ":" in line:
                    k, v = line.split(":", 1)
                    header[k.strip()] = v.strip()
                body_start += 1
            sections = re.split(r"\n##\s*", raw)[1:]
            for i, sec in enumerate(sections):
                lines = sec.strip().splitlines()
                if not lines:
                    continue
                title = lines[0].strip()
                text = "\n".join(lines[1:]).strip()
                if not text:
                    continue
                self.chunks.append({
                    "id": f"{path.stem}-{i + 1}",
                    "file": path.name,
                    "school": header.get("学校", path.stem),
                    "source": header.get("文件", ""),
                    "title": title,
                    "text": text,
                })

    def _index(self) -> None:
        self.df: Counter = Counter()
        self.docs: list[Counter] = []
        for c in self.chunks:
            toks = _tokenize(c["title"] + " " + c["text"])
            c["_len"] = len(toks)
            tf = Counter(toks)
            self.docs.append(tf)
            for t in tf:
                self.df[t] += 1
        self.n = len(self.chunks)
        self.avg_len = sum(c["_len"] for c in self.chunks) / max(1, self.n)

    def search(self, query: str, top_k: int = 3, school: str | None = None, min_score: float = 0.8) -> list[dict]:
        q = [t for t in _tokenize(query) if len(t) > 1 or t.isdigit()]
        if not q:
            return []
        k1, b = 1.5, 0.75
        scored = []
        for i, c in enumerate(self.chunks):
            if school and school not in c["school"] and "教育部" not in c["school"]:
                continue
            tf = self.docs[i]
            score = 0.0
            for t in q:
                f = tf.get(t, 0)
                if not f:
                    continue
                idf = math.log((self.n - self.df[t] + 0.5) / (self.df[t] + 0.5) + 1)
                score += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * c["_len"] / self.avg_len))
            if score > 0:
                scored.append((score, i))
        scored.sort(reverse=True)
        out = []
        for score, i in scored[:top_k]:
            if score < min_score:
                continue
            c = dict(self.chunks[i])
            c["score"] = round(score, 2)
            c["citation"] = f"{c['school']}·{c['title']}"
            out.append(c)
        # school 限定太严导致一条都没命中时，回退全库再检索一次，
        # 避免「配了学校名但学生问的是通用政策」时返回空回答
        if not out and school:
            return self.search(query, top_k=top_k, school=None, min_score=min_score)
        return out

    def schools(self) -> list[str]:
        return sorted({c["school"] for c in self.chunks})


_KB: KnowledgeBase | None = None


def kb() -> KnowledgeBase:
    global _KB
    if _KB is None:
        _KB = KnowledgeBase()
    return _KB
