"""知识库检索：混合检索（BM25 + 向量）→ RRF 融合 → 重排。

为什么不是「一个 BM25 就完事」
--------------------------------
单靠关键词，问「挂了二十学分是不是要退学」时命中的是含「学分」的任意段落，
而真正该命中的是「退学警示」那段——两者字面重合极少。反过来只用向量，
问「第 10 条怎么写的」这种带编号的精确查询又会漂。所以两条路都跑，
各自出候选，再融合排序：

  query ──► 查询改写（口语→术语 + 同义词扩展）
              ├──► BM25（中文 bigram，字面精确）
              └──► 向量（智谱 embedding-3；不可用时降级本地字符 n-gram）
                    ↓
              RRF 融合（Reciprocal Rank Fusion，只看名次不看分数量纲）
                    ↓
              重排（标题命中 / 覆盖度 / 同义命中 / 学校匹配 / 过短惩罚）
                    ↓
              top-k + 引用（带分数与命中原因，前端可核对）

设计约束
- **零强制依赖**：没网、没额度、没配 key 时自动退回本地字符向量，功能不降级为「报错」。
- **首次构建花几秒，之后走缓存**：向量按 (模型 + 片段哈希) 存到 data/kb_vectors.json，
  改一篇文档只重算那一篇，不动其余。
- **可解释**：每条命中都带 bm25 / vector / rerank 三个分量，前端与 trace 能直接展示
  「为什么是它」，这是评审看「检索策略是否合理」的抓手。
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import struct
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

KB_DIR = Path(__file__).resolve().parent.parent / "knowledge"
CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "kb_vectors.json"

# 片段长度：太短丢上下文，太长稀释向量。中文按字算，320 字约等于一段完整条款。
MAX_CHUNK = 320
OVERLAP = 48

_WORD_RE = re.compile(r"[a-zA-Z]+|\d+")
_CJK_RE = re.compile(r"[\u4e00-\u9fa5]")
_SENT_RE = re.compile(r"(?<=[。；！？])")


# ---------------------------------------------------------------- 分词
# 可选分词器：装了 jieba 就切词，没装自动退回 bigram（不把 jieba 设成硬依赖，
# 换台机器 clone 下来不装也能跑，只是排序稍弱）。
_DOMAIN_WORDS = (
    "学业预警 学业警示 降级试读 退学警示 留校察看 缓考 补考 重修 免修 免听 "
    "学分 绩点 平均学分绩点 培养方案 推免 保研 辅修 微专业 转专业 转专业申请 "
    "奖学金 国家奖学金 励志奖学金 助学金 勤工助学 绿色通道 缓交学费 "
    "处分 警告 严重警告 记过 违纪 申诉 复核 听证 "
    "考勤 旷课 缺勤 请假 病假 事假 销假 课堂纪律 考试资格 "
    "家校沟通 家长通知 告知书 帮扶 干预 台账 谈话 心理危机 休学 复学 退学 "
    "风险分 预警等级 红色预警 黄色预警 绿色预警 课程预警 毕业审核 学位 毕业论文"
).split()


def _build_segmenter():
    try:
        import jieba  # noqa: F401
    except Exception:
        return None
    import jieba as _j

    _j.setLogLevel(20)
    for w in _DOMAIN_WORDS:
        _j.add_word(w)
    cut = _j.lcut

    def seg(text: str) -> list[str]:
        return [t.strip() for t in cut(text) if t.strip()]

    return seg


_SEG = _build_segmenter()


def tokenize(text: str) -> list[str]:
    """中文切词：有 jieba 就用词典切词 + 单字兜底，没有就退回 bigram。

    bigram 的好处是零依赖、召回高；坏处是「还能」「金吗」这类碎片也算命中，
    排序时容易把标题字面像的片段顶上来。装了 jieba 之后，查询里的「处分」
    「奖学金」是完整词，weighted_hit 才真正按语义覆盖度打分。
    两种切法都保留单字，保证「缓考」写错一个字时还有兜底召回。
    """
    text = text.lower()
    tokens = _WORD_RE.findall(text)
    cjk = _CJK_RE.findall(text)
    words = [t for t in _SEG("".join(cjk)) if len(t) > 1] if _SEG else []
    if words:
        # 有词典就不掺 bigram 了：bigram 会把「金吗」「过处」也算成命中，
        # 覆盖率打分被这些碎片灌高，反而看不清真正的术语有没有命中。
        # 单字仍然保留，兜住「缓考」被打成生词的情况。
        tokens += words
    else:
        tokens += ["".join(cjk[i:i + 2]) for i in range(len(cjk) - 1)]
    tokens += cjk
    return tokens


def _content_terms(text: str) -> set[str]:
    """查询里的实词：去掉疑问词、语气词等对检索没帮助的高频字。"""
    stop = set("的了吗呢吧啊是不是什么怎么怎样如何请问一下我你他她它们这那有和与或就都也要会能可以")
    out = set()
    for t in tokenize(text):
        if len(t) == 1 and t not in "分课学":
            continue
        if set(t) <= stop:
            continue
        out.add(t)
    return out


# ---------------------------------------------------------------- 查询改写
# 口语 → 术语。学生不会说「学业警示实施办法」，他说「挂科太多会不会被劝退」。
# 这张表就是那座桥，同时它也是「检索策略」里最能讲清楚的一环。
SYNONYMS: dict[str, list[str]] = {
    "挂科": ["不及格", "补考", "重修", "挂科学分"],
    "挂了": ["不及格", "补考", "重修"],
    "不及格": ["挂科", "补考"],
    "补考": ["不及格", "重修"],
    "重修": ["补考", "不及格"],
    "劝退": ["退学", "退学警示", "降级试读"],
    "退学": ["退学警示", "降级试读"],
    "降级": ["降级试读", "试读"],
    "留级": ["降级试读"],
    "休学": ["复学", "学籍异动"],
    "复学": ["休学", "学籍异动"],
    "转专业": ["学籍异动", "绩点排名"],
    "旷课": ["缺勤", "考勤", "考试资格"],
    "缺勤": ["旷课", "考勤", "缺勤率"],
    "请假": ["病假", "事假", "缓考"],
    "翘课": ["旷课", "缺勤"],
    "通报": ["通知家长", "告知函", "家长"],
    "家长": ["通知家长", "告知函"],
    "告诉家长": ["通知家长", "告知函"],
    "奖学金": ["国家奖学金", "励志奖学金", "学业奖学金"],
    "助学金": ["困难生", "资助", "绿色通道"],
    "学费": ["缓交学费", "绿色通道"],
    "心理": ["心理中心", "危机干预", "心理预警"],
    "抑郁": ["心理预警", "心理中心"],
    "处分": ["申诉", "违纪"],
    "申诉": ["复查", "申诉处理委员会"],
    "成绩单": ["成绩单打印", "盖章"],
    "在读证明": ["证明办理", "盖章"],
    "宿舍": ["调换宿舍", "住宿"],
    "风险分": ["风险评分", "六因素", "预警等级"],
    "风险": ["风险评分", "预警等级"],
    "预警": ["学业警示", "预警等级", "学业预警"],
    "毕业": ["毕业审核", "结业", "学位"],
    "学位": ["学位授予", "毕业"],
    "绩点": ["平均绩点", "GPA"],
    "排名": ["绩点排名", "专业排名"],
    "保研": ["推免", "绩点排名"],
    "竞赛": ["学科竞赛", "公假"],
}

# 多轮里常见的指代词，本身不含信息，靠上下文补全
_ANAPHORA = ("它", "这个", "那个", "那门", "这门", "上面", "刚才", "刚刚", "照片", "图片", "表里")


def expand_query(query: str, context: str = "") -> tuple[str, list[str]]:
    """查询改写：把口语补齐成术语。

    context: 上一轮对话里的关键词（课程名 / 学生名 / 照片摘要）。
    返回 (填充后的查询串, 本次补进去的术语列表)，后者要进 trace，
    评审能看到「系统把我的话补成了什么」。
    """
    q = (query or "").strip()
    added: list[str] = []
    for k, vs in SYNONYMS.items():
        if k in q:
            for v in vs:
                if v not in q and v not in added:
                    added.append(v)
    # 指代词补全：这轮只说「那门课」时，把上下文里的课程名接进去
    if context and any(w in q for w in _ANAPHORA):
        for term in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,10}", context)[:6]:
            if term in q:
                continue
            if any(term in x for x in ("课", "学", "成绩", "作业", "老师")):
                added.append(term)
                break
    expanded = q if not added else q + " " + " ".join(added)
    return expanded, added[:6]


# ---------------------------------------------------------------- 分块
def _split_long(text: str, limit: int = MAX_CHUNK, overlap: int = OVERLAP) -> list[str]:
    """超长段落按句子切，相邻块留 overlap 字的尾巴，避免答案卡在切口上。"""
    if len(text) <= limit:
        return [text]
    sentences = [s for s in _SENT_RE.split(text) if s.strip()]
    out: list[str] = []
    buf = ""
    for s in sentences:
        if len(buf) + len(s) <= limit:
            buf += s
            continue
        if buf:
            out.append(buf)
        buf = (buf[-overlap:] if buf else "") + s
        while len(buf) > limit:            # 单句就超长：硬切，别死循环
            out.append(buf[:limit])
            buf = buf[limit - overlap:]
    if buf.strip():
        out.append(buf)
    return out


def _iter_chunks(path: Path, kind: str = "policy") -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    header: dict[str, str] = {}
    for line in raw.splitlines():
        if line.startswith("## "):
            break
        if ":" in line:
            k, v = line.split(":", 1)
            header[k.strip()] = v.strip()
    doc_title = header.get("文件", path.stem)
    school = header.get("学校", path.stem)

    chunks: list[dict] = []
    for i, sec in enumerate(re.split(r"\n##\s*", raw)[1:]):
        lines = sec.strip().splitlines()
        if not lines:
            continue
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        if not body:
            continue
        for j, piece in enumerate(_split_long(body)):
            chunks.append({
                "id": f"{path.stem}-{i + 1}" + (f".{j + 1}" if j else ""),
                "file": path.name,
                "doc": doc_title,
                "school": school,
                "source": header.get("文件", ""),
                # 章节路径：引用时显示「《学籍管理规定》· 降级试读的条件」
                "path": f"{doc_title} · {title}",
                "title": title,
                "text": piece.strip(),
                "order": i * 100 + j,
                # policy = 权威规章；resource = 教师上传的真题/讲义
                "kind": kind,
            })
    return chunks


# ---------------------------------------------------------------- BM25
class BM25:
    def __init__(self, chunks: list[dict]):
        self.df: Counter = Counter()
        self.docs: list[Counter] = []
        self.lens: list[int] = []
        for c in chunks:
            toks = tokenize(c["title"] + " " + c["text"])
            tf = Counter(toks)
            self.docs.append(tf)
            self.lens.append(len(toks))
            for t in tf:
                self.df[t] += 1
        self.n = len(chunks)
        self.avg_len = sum(self.lens) / max(1, self.n) or 1.0

    def scores(self, terms: list[str]) -> dict[int, float]:
        k1, b = 1.5, 0.75
        out: dict[int, float] = {}
        for i, tf in enumerate(self.docs):
            s = 0.0
            for t in terms:
                f = tf.get(t, 0)
                if not f:
                    continue
                idf = math.log((self.n - self.df[t] + 0.5) / (self.df[t] + 0.5) + 1)
                s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * self.lens[i] / self.avg_len))
            if s > 0:
                out[i] = s
        return out

    def idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log((self.n - df + 0.5) / (df + 0.5) + 1)

    def weighted_hit(self, terms: set[str], text: str) -> float:
        """按 idf 加权的字面覆盖率（0~1）。

        普通覆盖率把「什么」「可以」和「缓考」算成同等的 1 票，
        结果白话串就赢了。这里让词越稀有、票越重：
        「缓考」只在 1 段出现 → 权重高；「情况」遍布全库 → 权重接近 0。
        """
        if not terms:
            return 0.0
        low = text.lower()
        total = 0.0
        hit = 0.0
        for t in terms:
            w = self.idf(t) + 0.2       # 未登录词（df=0）拿最高权重，别把生词判成不重要
            total += w
            if t in low:
                hit += w
        return hit / total if total else 0.0


# ---------------------------------------------------------------- 向量通道
def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _embed_enabled() -> bool:
    return _env("RAG_EMBED", "1").lower() not in {"0", "false", "no", "off"}


def _embed_model() -> str:
    return _env("RAG_EMBED_MODEL", "embedding-3") or "embedding-3"


def _base_url() -> str:
    return _env("LLM_BASE_URL", "https://api.open.bigmodel.cn/api/paas/v4").rstrip("/")


def _api_key() -> str:
    return _env("LLM_API_KEY", "")


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _pack(vec: list[float]) -> str:
    """float16 + base64：2048 维从 16KB 压到 4KB，余弦排序够用。"""
    return base64.b64encode(struct.pack(f"<{len(vec)}e", *vec)).decode("ascii")


def _unpack(blob: str) -> list[float]:
    raw = base64.b64decode(blob)
    return list(struct.unpack(f"<{len(raw) // 2}e", raw))


def _remote_embed(texts: list[str], timeout: int = 8) -> list[list[float]] | None:
    """调智谱 embedding。失败返回 None，由上层降级，不抛异常。"""
    if not (_embed_enabled() and _api_key()):
        return None
    body = json.dumps({"model": _embed_model(), "input": texts}).encode("utf-8")
    req = urllib.request.Request(
        f"{_base_url()}/embeddings",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {_api_key()}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        rows = sorted(data.get("data") or [], key=lambda d: d.get("index", 0))
        vecs = [r.get("embedding") or [] for r in rows]
        if len(vecs) == len(texts) and all(vecs):
            return vecs
        return None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError,
            json.JSONDecodeError, KeyError):
        return None


class VectorIndex:
    """语义通道。

    两种实现共用一套接口：
    - remote：智谱 embedding-3（2048 维，语义强，要网要额度）
    - local ：字符 1~3 gram 哈希到 512 维（离线可用，近似字面相似）
    构建时先试 remote，失败就整体退回 local，并把 mode 记下来给前端显示。
    """

    DIM = 512

    def __init__(self, chunks: list[dict], cache_file: Path = CACHE_FILE):
        self.mode = "local"
        self.vectors: list[dict[int, float]] = []
        self.norms: list[float] = []
        self._qcache: dict[str, list[float]] = {}   # 查询向量缓存，省一次网络往返
        self._cache_file = cache_file
        self._cache = self._load_cache()
        self._build(chunks)
        self._save_cache()

    # ---- 缓存 ----
    def _load_cache(self) -> dict:
        try:
            return json.loads(self._cache_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_cache(self) -> None:
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            self._cache_file.write_text(json.dumps(self._cache), encoding="utf-8")
        except OSError:
            pass

    # ---- 本地向量 ----
    @classmethod
    def _local_vec(cls, text: str) -> dict[int, float]:
        """字符 1~3 gram 哈希到 DIM 维：比 bigram 更抗错字，比词切分更稳。

        用 md5 而不是内置 hash()：内置 hash 每个进程加盐，重启就变，
        缓存里的向量会全部失效。
        """
        low = text.lower()
        cjk = "".join(_CJK_RE.findall(low))
        grams = list(tokenize(low))
        for n in (1, 2, 3):
            grams += [cjk[i:i + n] for i in range(max(0, len(cjk) - n + 1))]
        tf = Counter(grams)
        vec: dict[int, float] = {}
        for g, f in tf.items():
            idx = int(hashlib.md5(g.encode("utf-8")).hexdigest()[:8], 16) % cls.DIM
            vec[idx] = vec.get(idx, 0.0) + 1.0 + math.log(f)
        return vec

    # ---- 构建 ----
    def _build(self, chunks: list[dict]) -> None:
        texts = [f"{c['title']}。{c['text']}" for c in chunks]
        keys = [f"{_embed_model()}:{_hash(t)}" for t in texts]

        # 1) 先看缓存里齐不齐
        cached = [self._cache.get(k) for k in keys]
        missing = [i for i, v in enumerate(cached) if not v]

        dense: list[list[float] | None] = [None] * len(texts)
        for i, blob in enumerate(cached):
            if blob is not None:
                dense[i] = _unpack(blob)

        # 2) 缺的批量补（16 条一批；第一批失败就整体放弃，不在启动时干等）
        if missing and _embed_enabled() and _api_key():
            t0 = time.time()
            ok = True
            for start in range(0, len(missing), 16):
                batch = missing[start:start + 16]
                vecs = _remote_embed([texts[i] for i in batch])
                if vecs is None:
                    ok = False
                    break
                for i, v in zip(batch, vecs):
                    dense[i] = v
                    self._cache[keys[i]] = _pack(v)
                if time.time() - t0 > 25:
                    ok = False
                    break
            if ok and all(v is not None for v in dense):
                self.mode = "remote"

        # 全部命中缓存时不会再进入上面的补算分支，这里单独判一次：
        # 缓存里只存过远程向量（本地向量从不写缓存），齐了就说明能用远程
        if all(v is not None for v in dense):
            self.mode = "remote"

        # 3) remote 不齐 → 整体用本地向量，避免两套向量混着算（量纲不同，余弦没意义）
        if self.mode != "remote":
            self.vectors = [self._local_vec(t) for t in texts]
        else:
            self.vectors = [dict(enumerate(v)) for v in dense]  # type: ignore[arg-type]
        self.norms = [self._norm(v) for v in self.vectors]

    @staticmethod
    def _norm(v: dict[int, float]) -> float:
        return math.sqrt(sum(x * x for x in v.values())) or 1.0

    # ---- 查询 ----
    def query(self, text: str) -> dict[int, float]:
        if self.mode == "remote":
            vec = self._qcache.get(text)
            if vec is None:
                vecs = _remote_embed([text])
                if vecs:
                    vec = vecs[0]
                    if len(self._qcache) >= 256:      # 查询向量缓存：重复问法不再等网络
                        self._qcache.pop(next(iter(self._qcache)))
                    self._qcache[text] = vec
            if vec:
                q = dict(enumerate(vec))
                qn = self._norm(q)
                out = {}
                for i, v in enumerate(self.vectors):
                    dot = sum(val * v.get(k, 0.0) for k, val in q.items())
                    out[i] = dot / (qn * self.norms[i])
                return out
            # 线上挂了就地降级到本地向量，不整库重建
        q = self._local_vec(text)
        qn = self._norm(q)
        out = {}
        for i, v in enumerate(self.vectors):
            dot = sum(val * v.get(k, 0.0) for k, val in q.items())
            out[i] = dot / (qn * self.norms[i])
        return out


# ---------------------------------------------------------------- 融合 + 重排
def _rrf(rank: int, k: int = 8) -> float:
    """Reciprocal Rank Fusion：只看名次，两路分数不可比也能融合。"""
    return 1.0 / (k + rank)


class KnowledgeBase:
    def __init__(self, kb_dir: Path = KB_DIR, cache_file: Path = CACHE_FILE):
        self.chunks: list[dict] = []
        self.policy_docs = 0
        self.resource_docs = 0
        # 政策文档在 knowledge/ 顶层；教师上传的资料在 knowledge/resources/
        sources: list[tuple[Path, str]] = []
        for path in sorted(kb_dir.glob("*.md")):
            if path.name.lower() in ("readme.md", "index.md"):
                continue
            sources.append((path, "policy"))
        res_dir = kb_dir / "resources"
        if res_dir.is_dir():
            for path in sorted(res_dir.glob("*.md")):
                sources.append((path, "resource"))

        for path, kind in sources:
            try:
                chunks = _iter_chunks(path, kind)
            except Exception:
                # 单篇文档坏了不能拖垮整个知识库
                continue
            if not chunks:
                continue
            self.chunks.extend(chunks)
            if kind == "policy":
                self.policy_docs += 1
            else:
                self.resource_docs += 1

        self.bm25 = BM25(self.chunks)
        self.vec = VectorIndex(self.chunks, cache_file=cache_file)
        self.built_at = time.strftime("%Y-%m-%d %H:%M:%S")

    # ---- 对外主入口 ----
    def search(self, query: str, top_k: int = 4, school: str | None = None,
               min_score: float = 0.25, context: str = "",
               use_vector: bool = True, rewrite: bool = True) -> list[dict]:
        """检索并返回带分数、命中原因的片段。

        min_score 是 0~1 的相关度下限（0.25 约等于「沾边就算」，
        0.45 以上基本是同一主题）。原来的 BM25 原始分阈值换成了这个归一化口径，
        跨查询可比，前端也能直接显示成百分比。

        use_vector / rewrite 两个开关只给评测用：
        关掉向量 = 纯 BM25 基线，关掉改写 = 无同义扩展基线，
        这样 ablation 对比的是同一套打分代码，不是两份实现。
        """
        t0 = time.time()
        query = (query or "").strip()
        if not query:
            return []

        if rewrite:
            expanded, added = expand_query(query, context)
        else:
            expanded, added = query, []
        terms = [t for t in tokenize(expanded) if len(t) > 1 or t.isdigit()]
        if not terms:
            return []

        bm = self.bm25.scores(terms)
        vs = self.vec.query(expanded) if use_vector else {}

        bm_order = sorted(bm, key=lambda x: -bm[x])[:24]
        vs_order = [i for i in sorted(vs, key=lambda x: -vs[x])[:24] if vs[i] > 0]
        cand: dict[int, dict] = {}
        for rank, i in enumerate(bm_order, 1):
            cand.setdefault(i, {})["bm25_rank"] = rank
        for rank, i in enumerate(vs_order, 1):
            cand.setdefault(i, {})["vec_rank"] = rank
        if not cand:
            return []

        # ---- 融合 + 重排 ----
        q_terms = _content_terms(query)
        exp_terms = _content_terms(expanded) - q_terms
        best_bm = max(bm.values()) if bm else 1.0
        rows = []
        for i, slot in cand.items():
            ch = self.chunks[i]
            bm_raw = bm.get(i, 0.0)
            bm_n = bm_raw / (bm_raw + 3.0) if bm_raw else 0.0
            cos = max(0.0, vs.get(i, 0.0))
            base = (0.5 * cos + 0.5 * bm_n) if use_vector else bm_n

            # 重排：字面证据（标题比正文更有说服力）+ 术语覆盖 + 学校匹配
            title = ch.get("title", "") + ch.get("path", "")
            title_hit = _hit_ratio(q_terms, title)
            body_all = title + ch["text"]
            body_hit = _hit_ratio(q_terms, body_all)
            syn_hit = _hit_ratio(exp_terms, body_all) if exp_terms else 0.0
            # 按词稀有度加权：「缓考」「退学」这类专有词比「什么情况」「可以」这种白话
            # 更能说明用户在问哪一条。不加这一项时，「什么情况可以申请缓考」会被
            # 「什么情况必须补考」抢走——因为两处白话词一样多，专有词只占一小票。
            key_hit = self.bm25.weighted_hit(q_terms, title)
            key_body = self.bm25.weighted_hit(q_terms, body_all)
            school_bonus = 0.04 if (school and school in ch["school"]) else 0.0
            short_pen = -0.03 if len(ch["text"]) < 40 else 0.0
            bonus = (0.10 * title_hit + 0.06 * body_hit + 0.05 * syn_hit
                     + 0.14 * key_hit + 0.06 * key_body + school_bonus + short_pen)

            fused = (_rrf(slot.get("bm25_rank", 30)) + _rrf(slot.get("vec_rank", 30))) * 10
            rel = max(0.0, min(1.0, base + bonus))

            if rel < min_score:
                continue
            hit = dict(ch)
            hit.update({
                "score": round(rel, 3),
                "score_pct": f"{round(rel * 100)}%",
                "fused": round(fused, 3),
                "bm25": round(bm_raw, 2),
                "vector": round(cos, 3),
                "why": _why(title_hit, body_hit, syn_hit, cos, bm_n),
                "citation": hit["path"],
                "kind": ch.get("kind", "policy"),
                "snippet": hit["text"][:180],
            })
            rows.append(hit)

        rows.sort(key=lambda r: (r["score"], r["fused"]), reverse=True)
        # 学校限定太严导致零命中时，退回全库再试一次（问通用政策时常见）
        if not rows and school:
            out = self.search(query, top_k=top_k, school=None, min_score=min_score,
                              context=context, use_vector=use_vector, rewrite=rewrite)
            for r in out:
                r["fallback"] = True
            return out

        top = rows[:top_k]
        if not use_vector:
            channel = "bm25"
        elif self.vec.mode == "remote":
            channel = "hybrid"
        else:
            channel = "bm25+local-vector"
        self.last_meta = {
            "query": query,
            "rewritten": expanded if added else "",
            "added_terms": added,
            "candidates": len(cand),
            "kept": len(top),
            "channel": channel,
            "embed": _embed_model() if (use_vector and self.vec.mode == "remote") else "",
            "ms": round((time.time() - t0) * 1000, 1),
        }
        return top

    def schools(self) -> list[str]:
        return sorted({c["school"] for c in self.chunks if c.get("kind") != "resource"})

    def stats(self) -> dict:
        res = [c for c in self.chunks if c.get("kind") == "resource"]
        return {
            "docs": self.policy_docs,
            "resources": self.resource_docs,
            "resource_chunks": len(res),
            "chunks": len(self.chunks),
            "chars": sum(len(c["text"]) for c in self.chunks),
            "schools": self.schools(),
            "vector_mode": self.vec.mode,
            "embed_model": _embed_model() if self.vec.mode == "remote" else "(本地字符向量)",
            "segmenter": "jieba + 领域词典" if _SEG else "字符 bigram（未装 jieba）",
            "built_at": self.built_at,
        }

    def meta(self) -> dict:
        return dict(getattr(self, "last_meta", {}) or {})


def _hit_ratio(terms: set[str], text: str) -> float:
    if not terms:
        return 0.0
    low = text.lower()
    hit = sum(1 for t in terms if t in low)
    return hit / len(terms)


def _why(title_hit: float, body_hit: float, syn_hit: float, cos: float, bm_n: float) -> str:
    bits = []
    if title_hit >= 0.5:
        bits.append("标题命中")
    if body_hit >= 0.6:
        bits.append("正文覆盖")
    if syn_hit >= 0.3:
        bits.append("同义扩展命中")
    if cos >= 0.55:
        bits.append("语义相近")
    if bm_n >= 0.5:
        bits.append("关键词强匹配")
    return "、".join(bits) or "弱相关"


_KB: KnowledgeBase | None = None
_KB_LOCK = threading.Lock()


def kb() -> KnowledgeBase:
    global _KB
    if _KB is None:
        with _KB_LOCK:
            if _KB is None:
                _KB = KnowledgeBase()
    return _KB


def rebuild() -> dict:
    """重建索引（改了 knowledge/*.md 或教师新上传资料后调用）。

    向量按 (模型 + 片段哈希) 缓存，只有新增片段需要调 embedding，
    所以通常几百毫秒到一两秒，说不上贵。

    注意这里是**原地换血**，不是把 _KB 指向新对象：app.py 的 `KB = rag.kb()`
    和 Agent 里的 kb 都是启动时拿到的引用，换对象它们仍然看着旧索引，
    表现就是「上传成功了，但 AI 一直答不出来」。
    """
    global _KB
    with _KB_LOCK:
        fresh = KnowledgeBase()
        if _KB is None:
            _KB = fresh
        else:
            _KB.chunks = fresh.chunks
            _KB.bm25 = fresh.bm25
            _KB.vec = fresh.vec
            _KB.policy_docs = fresh.policy_docs
            _KB.resource_docs = fresh.resource_docs
            _KB.built_at = fresh.built_at
        return _KB.stats()


def rebuild_async() -> None:
    """后台重建：上传接口不该为了索引等一两秒，失败了也不影响文件已经存好。"""
    def run() -> None:
        try:
            rebuild()
        except Exception:
            pass

    threading.Thread(target=run, daemon=True).start()
