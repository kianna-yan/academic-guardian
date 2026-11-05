"""检索评测：Recall@1 / Recall@3 / MRR，三档配置做 ablation。

跑法：
    python -m tests.rag_eval            # 打表格
    python -m tests.rag_eval --detail   # 附带每条命中明细与失败样例

三档配置走的是同一份打分代码，只切开关，所以差异确实来自「向量」「改写」两项：
    A 纯 BM25（关向量、关改写）   —— 传统关键词检索基线
    B BM25 + 查询改写             —— 只补同义词，不补语义
    C 混合检索（向量 + 改写）      —— 线上实际用的配置

标注口径：一条问题允许多个正确章节（同一件事常散在学籍规定、FAQ、校方办法里），
命中其中之一即算对；只对 Top-3 打分，因为线上最多只给模型 3 条。
"""
from __future__ import annotations

import sys
import time

from engine.rag import kb

# (问题, 可接受的章节标题/文档关键词)
CASES: list[tuple[str, list[str]]] = [
    ("挂多少学分会被退学", ["退学警示", "挂几门课会被退学", "劝退与退学"]),
    ("补考没过怎么办", ["补考还没过怎么办", "补考和重修的成绩怎么记"]),
    ("重修怎么报名", ["重修怎么报名"]),
    ("什么情况可以申请缓考", ["缓考申请条件"]),
    ("缺考了会有什么后果", ["缺考与旷考的后果"]),
    ("挂的学分多了还能毕业吗", ["挂科学分和毕业的关系", "毕业差几个学分", "毕业与结业"]),
    ("缺勤多少次会取消考试资格", ["缺勤多少次会取消考试资格", "缺勤怎么认定"]),
    ("旷课太多学校会怎么处理", ["旷课的处理阶梯"]),
    ("请假最长能请多久", ["请假类型与时限"]),
    ("请假期间落下的作业怎么办", ["请假期间的作业与考试"]),
    ("考勤记录有错误怎么申诉", ["考勤记录有异议怎么申诉"]),
    ("学校什么情况下会通知家长", ["学校什么情况下会通知家长", "家长会收到通知吗", "告知与家校联系"]),
    ("通知家长是用电话还是写信", ["通知家长用什么形式"]),
    ("对成绩有异议多久内要提出", ["成绩有异议多久内提出", "申诉的时限和流程"]),
    ("申诉需要准备哪些材料", ["申诉需要准备什么材料"]),
    ("申诉期间原来的处分还执行吗", ["复查期间原决定是否执行"]),
    ("国家奖学金和励志奖学金有什么区别", ["国家奖学金与励志奖学金的区别"]),
    ("学业奖学金要什么条件", ["学业奖学金的评审条件"]),
    ("助学金怎么申请", ["助学金申请流程"]),
    ("学费交不上怎么办", ["绿色通道与缓交学费", "缓交学费与住宿费"]),
    ("勤工助学岗位怎么申请", ["勤工助学岗位怎么申请"]),
    ("受过处分还能拿奖学金吗", ["处分对奖励资助的影响"]),
    ("挂过科还能保研吗", ["推免资格的基本条件", "挂科、重修对保研的影响"]),
    ("辅修的成绩算进绩点吗", ["辅修与微专业"]),
    ("想休学一年可以吗", ["想休学一年可以吗", "休学与复学"]),
    ("转专业什么时候能申请", ["转专业的时间窗口", "转专业需要什么条件"]),
    ("降级试读是什么条件", ["降级试读的条件", "降级试读条件"]),
    ("风险分是怎么算出来的", ["风险分是怎么算出来的"]),
    ("红黄绿三档的分数线", ["红黄绿三档的阈值"]),
    ("学校的学业预警是怎么触发的", ["预警触发条件", "学业警示触发条件", "预警的两类常见触发"]),
    ("心理危机四级预警怎么划分", ["四级心理预警怎么划分"]),
    ("谈话记录应该怎么写", ["谈话记录的写法"]),
    ("在读证明怎么开", ["在读证明怎么开"]),
    ("宿舍想调换怎么申请", ["宿舍调换怎么申请"]),
    ("校园卡丢了怎么补办", ["校园卡丢失与补办"]),
    ("北京科技大学的警示怎么送达", ["送达流程", "北京科技大学"]),
    ("深圳技术大学的预警办法", ["深圳技术大学"]),
]

CONFIGS = [
    ("A 纯 BM25（基线）", {"use_vector": False, "rewrite": False}),
    ("B BM25 + 查询改写", {"use_vector": False, "rewrite": True}),
    ("C 混合检索（线上）", {"use_vector": True, "rewrite": True}),
]

TOP_K = 3


def hit_rank(hits: list[dict], targets: list[str]) -> int | None:
    """返回第一个命中的名次（1 起），没命中返回 None。"""
    for i, h in enumerate(hits, 1):
        hay = f"{h.get('path', '')} {h.get('title', '')} {h.get('doc', '')}"
        if any(t in hay for t in targets):
            return i
    return None


def run_config(knowledge, flags: dict, detail: bool = False) -> dict:
    r1 = r3 = 0
    mrr = 0.0
    ms_total = 0.0
    fails: list[tuple[str, list[str]]] = []
    for q, targets in CASES:
        t0 = time.time()
        hits = knowledge.search(q, top_k=TOP_K, min_score=0.0, **flags)
        ms_total += (time.time() - t0) * 1000
        rank = hit_rank(hits, targets)
        if rank == 1:
            r1 += 1
        if rank and rank <= TOP_K:
            r3 += 1
            mrr += 1.0 / rank
        else:
            fails.append((q, [h.get("path", "") for h in hits]))
        if detail:
            got = [h.get("path", "") for h in hits]
            print(f"    {'✓' if rank == 1 else ('~' if rank else '✗')} {q}  →  {got}")
    n = len(CASES)
    return {
        "recall@1": r1 / n,
        "recall@3": r3 / n,
        "mrr": mrr / n,
        "ms": ms_total / n,
        "fails": fails,
    }


def main() -> None:
    knowledge = kb()
    st = knowledge.stats()
    print(f"知识库：{st['docs']} 篇 / {st['chunks']} 个片段 / {st['chars']} 字"
          f" / 向量通道 {st['vector_mode']} / 评测集 {len(CASES)} 条\n")

    rows = []
    for name, flags in CONFIGS:
        if "--detail" in sys.argv:
            print(f"[{name}]")
        res = run_config(knowledge, flags, detail="--detail" in sys.argv)
        rows.append((name, res))
        if "--detail" in sys.argv:
            print()

    print(f"{'配置':<22}{'Recall@1':>10}{'Recall@3':>10}{'MRR@3':>9}{'平均耗时':>11}")
    print("-" * 62)
    for name, r in rows:
        print(f"{name:<22}{r['recall@1']:>9.1%}{r['recall@3']:>10.1%}"
              f"{r['mrr']:>9.3f}{r['ms']:>9.0f} ms")

    base, ours = rows[0][1], rows[-1][1]
    print(f"\n相对纯 BM25：Recall@1 {base['recall@1']:.1%} → {ours['recall@1']:.1%}"
          f"（+{(ours['recall@1'] - base['recall@1']) * 100:.1f} 个点），"
          f"MRR {base['mrr']:.3f} → {ours['mrr']:.3f}")

    if ours["fails"]:
        print("\n混合检索仍未按标注命中（人工复核这几条是否标注过窄）：")
        for q, got in ours["fails"]:
            print(f"  - {q}\n      实际：{got}")


if __name__ == "__main__":
    main()
