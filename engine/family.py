"""家校沟通演练：AI 扮演不同类型的家长，导员先练一遍再打真电话。

为什么不用大模型来演
- 校园内网、演示环境的模型出口都不稳定，一旦模型不可用，「家长」就会变成
  客服话术，演练反而教坏话术；
- 角色扮演要能复盘：得说清「你这句话里做了什么、家长为什么这么接」。规则化的
  判断可以逐条解释，也能写进自动化测试。

所以这里只做一件事：把导员这句话里**做了哪几个动作**识别出来
（共情 / 摆事实 / 给方案 / 划边界 / 空承诺），再按家长类型给出对应的下一句。
家长说的每个数字都来自学情库——演练里也不能出现系统里没有的事实。
"""
from __future__ import annotations

import random
import zlib

# 家长的类型：不是性格标签，而是「他这通电话真正想要的东西」
PARENTS: list[dict] = [
    {
        "key": "anxious",
        "name": "焦虑型家长",
        "tag": "情绪先到，反复确认",
        "want": "怕的是没人管，需要一句「我们会盯着」",
        "who": "妈妈",
        "chips": ["我理解您现在的着急", "先把三个事实摆清楚", "我们每周固定同步一次"],
    },
    {
        "key": "demanding",
        "name": "强势质问型家长",
        "tag": "先要说法，再要承诺",
        "want": "要的是有人负责、有时间点，不是解释",
        "who": "爸爸",
        "chips": ["学校这边确实通知晚了", "给您一个明确的时间点", "书面材料我今天发您"],
    },
    {
        "key": "detached",
        "name": "放任疏离型家长",
        "tag": "人在外地，管不了",
        "want": "不是不在乎，是不知道怎么管；要一个「他能做到的小事」",
        "who": "爸爸",
        "chips": ["您在外地也不容易", "只需要您每周做一件事", "其他交给我们"],
    },
    {
        "key": "cooperative",
        "name": "配合型家长",
        "tag": "愿意配合，缺方法",
        "want": "要具体到每天做什么，别讲大道理",
        "who": "妈妈",
        "chips": ["给您一份每天能做的清单", "家里只需要盯两件事", "有变化我第一时间告诉您"],
    },
]
BY_KEY = {x["key"]: x for x in PARENTS}

# 导员这句话里的动作，按「越具体越优先」排序
MOVES: list[tuple[str, tuple[str, ...]]] = [
    ("promise", ("保证", "一定能", "包过", "包他", "担保", "绝对没问题", "肯定没问题", "我承诺")),
    ("plan", ("计划", "安排", "辅导", "补课", "一对一", "每周", "跟进", "约", "帮扶",
              "自习", "学习小组", "联系任课", "盯", "打卡", "同步")),
    ("data", ("成绩", "均分", "缺勤", "缺课", "旷课", "作业", "排名", "风险", "期中",
              "学分", "数据", "挂科", "出勤")),
    ("empathy", ("理解", "明白", "着急", "别急", "辛苦", "不容易", "抱歉", "担心",
                 "换成我", "换我", "感同身受")),
    ("boundary", ("规定", "政策", "流程", "教务处", "手续", "程序", "制度", "学院")),
]

MOVE_LABEL = {"empathy": "共情", "data": "摆事实", "plan": "给方案",
              "boundary": "划边界", "promise": "空承诺", "vague": "没说具体"}

# 每类家长 × 每种动作的反应。{...} 里的数字全部来自学情库。
_REPLIES: dict[str, dict[str, list[str]]] = {
    "anxious": {
        "vague": [
            "老师，这些我不太听得懂。您就跟我说一句实话：孩子现在到底危不危险？",
            "您说的我都记下来了，可我还是不知道该做什么……是不是很严重？",
        ],
        "empathy": [
            "谢谢您这么说……我这两天整宿睡不着，就怕他在学校出了事我们都不知道。",
            "您能理解就好。我们做家长的，最怕学校觉得我们不管孩子。",
        ],
        "data": [
            "缺了 {absent} 次课？他跟我说都去了呀……那期中 {mid} 分是不是就没救了？",
            "期中 {mid} 分，比班里平均还低？他以前不这样的，是不是交了什么坏朋友？",
        ],
        "plan": [
            "每周同步一次……那是您盯还是我盯？我们也不懂这些课，说重了他就不接电话了。",
            "您说的这个安排，他要是又不做呢？我在家说一句他顶三句。",
        ],
        "boundary": [
            "那按规定，最坏会怎么样？会不会劝退？您给我个准话，我心里才有底。",
            "走流程要多久？这期间孩子的课还上不上？",
        ],
        "promise": [
            "您这么说我就放心一点了……那您能保证他这学期不会再掉下去吗？",
            "真的吗？那我就全拜托您了，出了事我可找您啊。",
        ],
    },
    "demanding": {
        "vague": [
            "您这话等于没说。我要的是具体谁来管、什么时候见效。",
            "老师，我不是来听原则的。给我一个方案，或者告诉我该找谁。",
        ],
        "empathy": [
            "理解归理解，孩子的前途不是一句理解能解决的。",
            "我知道你们也不容易，可这半学期学校干什么去了？",
        ],
        "data": [
            "数据我认。但学校发现问题为什么不早通知？我要一个解释。",
            "缺勤 {absent} 次、作业交了 {hw} 次，这些你们早就知道了吧？为什么现在才说？",
        ],
        "plan": [
            "计划可以，白纸黑字吗？多长时间我能看到变化？一个月还是两个月？",
            "每周同步我同意。谁签字？出了问题找谁？",
        ],
        "boundary": [
            "规定是规定，我们家长的知情权呢？我要书面答复。",
            "流程我配合，但我要求把今天的沟通记进孩子的档案里。",
        ],
        "promise": [
            "空话我听得多了。你给我一个时间点，做不到怎么说？",
            "保证？上回班主任也这么说。我要写下来的东西。",
        ],
    },
    "detached": {
        "vague": [
            "老师您说的这些我也听不太懂，反正就拜托你们了。",
            "唉，我一年到头在外面，能做的也就是给他打钱。",
        ],
        "empathy": [
            "您这么说，我心里也过意不去……可工地这边走不开。",
            "不是我不想管，是我们说了他也不听。",
        ],
        "data": [
            "缺了 {absent} 次课？那我过年回去得说说他。",
            "期中才 {mid} 分啊……他初中成绩还行的，怎么变成这样了。",
        ],
        "plan": [
            "让我每周跟他视频一次？行，我尽量，就怕他嫌我烦。",
            "您让我盯什么？我在电话里也看不见他写作业啊。",
        ],
        "boundary": [
            "需要签字的话您发我手机上，我签。",
            "学校有什么政策，您直接跟我说要多少钱、要办什么。",
        ],
        "promise": [
            "那就麻烦老师多费心了，孩子交给学校我放心。",
            "行，那就全靠你们了。",
        ],
    },
    "cooperative": {
        "vague": [
            "您说的方向我认同，具体到每一天我们该做什么呢？",
            "道理我们懂，就是不知道从哪一步开始。",
        ],
        "empathy": [
            "谢谢老师，孩子能遇到您这样的辅导员是他的运气。",
            "您别这么说，孩子的事我们也有责任。",
        ],
        "data": [
            "那 {top} 这块，我们在家能怎么帮他？需要请个家教吗？",
            "缺勤 {absent} 次……他早上起不来，这个我们能管。",
        ],
        "plan": [
            "这个计划我们能执行。要不要我每周把他在家的作息发给您？",
            "行，我先按您说的做一周，有变化我随时跟您说。",
        ],
        "boundary": [
            "需要办什么手续您说，我们配合。",
            "学校这边要开什么证明，我明天就去办。",
        ],
        "promise": [
            "老师您别把话说死，我们尽力配合就好。",
            "保证不敢说，但我们肯定配合。",
        ],
    },
}

_OPENINGS = {
    "anxious": ("老师，我是{name}的{who}。孩子昨天回家一句话不说，我问他成绩他就摔门。"
                "我看他期中才 {mid} 分，是不是要留级了？您别安慰我，就跟我说最坏的情况。"),
    "demanding": ("刘老师是吧？我是{name}的{who}。孩子成绩掉成这样，学校之前一次都没通知过我们，"
                  "现在才说预警——我想知道这是谁的责任。"),
    "detached": ("老师，我在外地工地上，孩子的事我真管不了。他从小就不爱学习，"
                 "你们学校管得严，该咋办咋办吧。"),
    "cooperative": ("老师您好，{name}回家说了预警的事。我们想配合，但不知道该从哪儿下手，"
                    "您给个具体的做法行吗？"),
}

# 空承诺在所有类型里都要被顶回来，且要提示导员——这句话最容易把沟通变成投诉
PROMISE_WARN = ("⚠️ 刚才那句里有「{word}」。学校无法担保结果，这类话在真实沟通里"
                "最容易被家长当成承诺，事后变成投诉依据。可以换成「我能保证的是每周盯一次，"
                "结果要一起努力」。")


def student_ctx(engine, sid: str) -> dict:
    """演练用的事实底座。取不到的字段一律给「—」，不编。"""
    s = engine.get(sid)
    r = engine.score(sid)
    raw = r.get("raw") or {}
    factors = r.get("factors") or []
    top = max(factors, key=lambda f: float(f.get("points") or 0))["label"] if factors else "课堂投入"
    return {
        "sid": sid,
        "name": s.get("name") or "该同学",
        "class_name": s.get("class_name") or "",
        "advisor": s.get("advisor") or "",
        "score": r.get("score"),
        "level_label": r.get("level_label") or "",
        "top": top,
        "absent": raw.get("absent", "—"),
        "sessions": raw.get("sessions", "—"),
        "hw": f"{raw.get('hw_submitted', '—')}/{raw.get('hw_assigned', '—')}",
        "mid": raw.get("mid_avg", "—"),
        "cohort": raw.get("cohort_avg", "—"),
    }


# 一句话里往往同时有共情和数据。反应按这个顺序挑一个代表性的，
# 但「做过哪些动作」要把命中的全记下来——否则复盘会把共情算漏。
REACT_ORDER = ("promise", "plan", "data", "empathy", "boundary")


def _detect(text: str) -> tuple[str, str, list[str]]:
    """返回 (代表性动作, 命中的词, 全部命中动作)。全不命中是 vague。"""
    found: list[str] = []
    words: dict[str, str] = {}
    for move, keys in MOVES:
        for w in keys:
            if w in text:
                found.append(move)
                words[move] = w
                break
    if not found:
        return "vague", "", []
    primary = next((m for m in REACT_ORDER if m in found), found[0])
    return primary, words.get(primary, ""), found


def _rng(seed: str) -> random.Random:
    """同一场演练里可复现：同样的输入给同样的反应，测试才写得稳。

    用 crc32 而不是内置 hash：hash 对字符串每个进程都加了随机盐，
    重启一次同一句话就换个反应，回归测试会莫名其妙地飘。
    """
    return random.Random(zlib.crc32(seed.encode("utf-8")))


def opening(kind: str, ctx: dict) -> str:
    p = BY_KEY[kind]
    line = _OPENINGS[kind].format(who=p["who"], **ctx)
    return (
        f"**家长（{p['name']}）**\n\n"
        f"「{line}」\n\n"
        f"> 潜台词：{p['want']}\n\n"
        "—— 演练开始。你可以直接回话，说「复盘」随时结束。"
    )


def reply(kind: str, text: str, ctx: dict, turn: int, moves: list[str],
          last_move: str | None = None) -> dict:
    """家长对导员这句话的反应。

    turn: 这是第几轮家长发言（从 1 开始）。
    moves: 此前用过的动作，用来判断「方案说过了但没给事实」这类结构问题。
    last_move: 上一轮的代表动作。连着两轮落在同一个动作上时换一句，
        否则家长会把同一句质疑说两遍，看起来像复读机。
    """
    p = BY_KEY[kind]
    move, word, found = _detect(text)
    pool = list(_REPLIES[kind].get(move) or _REPLIES[kind]["vague"])
    if last_move == move and len(pool) > 1:
        pool = pool[1:] + pool[:1]
    line = _rng(f"{kind}:{turn}:{move}:{text[:12]}").choice(pool).format(**ctx)

    out = [f"**家长（{p['name']}，第 {turn} 轮）**", "", f"「{line}」"]

    # 只给「该补的动作」，不刷屏：一条提醒上限。
    # 判断要带上本轮：这句话里已经共情了，就不能再提醒「你没共情」。
    all_moves = moves + (found or [move])
    notes: list[str] = []
    if move == "promise":
        notes.append(PROMISE_WARN.format(word=word))
    elif move == "vague":
        notes.append("这句话没给出任何可核实的信息。家长会继续追问，直到听见事实或方案。")
    elif move == "plan" and "data" not in all_moves:
        notes.append("先给方案、后给事实，家长容易觉得「你连情况都没搞清楚就让我配合」。"
                     "下次把分数、缺勤这些数字放在方案前面。")
    elif move == "data" and "empathy" not in all_moves and turn >= 2:
        notes.append("全程只讲数据，家长会觉得你在给孩子定罪。补一句「我知道您着急」成本很低。")
    if notes:
        out += ["", "> " + notes[0]]

    return {
        "text": "\n".join(out),
        "move": move,
        "moves": all_moves,
        "turn": turn,
        "suggestions": _next_chips(kind, all_moves, ctx),
    }


def _next_chips(kind: str, moves: list[str], ctx: dict) -> list[str]:
    """下一句可以怎么接：按缺的动作给，不是按家长类型给。"""
    p = BY_KEY[kind]
    chips: list[str] = []
    if "empathy" not in moves:
        chips.append("我理解您现在的着急")
    if "data" not in moves:
        chips.append(f"先把事实说清楚：缺勤 {ctx['absent']} 次、期中 {ctx['mid']} 分")
    if "plan" not in moves:
        chips.append("我们每周固定同步一次")
    if "boundary" not in moves:
        chips.append("按学校规定，这一步需要您签个字")
    if len(moves) >= 3 or len(chips) < 2:
        chips = chips[:2] + ["复盘：这场沟通怎么样"]
    return chips[:3]


def review(kind: str, ctx: dict, moves: list[str], turn: int) -> str:
    """复盘：覆盖了哪几个动作、漏了什么、这个家庭真正卡在哪。"""
    p = BY_KEY[kind]
    good = {"empathy", "data", "plan", "boundary"}
    used = [m for m in dict.fromkeys(moves) if m in good]
    missed = [m for m in ("empathy", "data", "plan", "boundary") if m not in used]
    n = len(used)

    lines = [f"**复盘 · 家长（{p['name']}）× 共 {turn} 轮**", ""]
    lines.append("你覆盖到的：" + ("、".join(MOVE_LABEL[m] for m in used) if used else "（没有明确动作）"))
    if missed:
        lines.append("还缺的：" + "、".join(MOVE_LABEL[m] for m in missed))
    if "promise" in moves:
        lines.append("需要改掉的：空承诺（「保证」「包过」这类话）")

    lines += ["", f"**这个家庭真正卡住的地方**：{p['want']}。"]
    lines.append(f"**事实底子**：{ctx['name']}（{ctx['class_name']}）风险 {ctx['score']} 分"
                 f"（{ctx['level_label']}），主因是{ctx['top']}；缺勤 {ctx['absent']}/{ctx['sessions']} 次，"
                 f"作业 {ctx['hw']}，期中 {ctx['mid']} 分（班均 {ctx['cohort']}）。")

    if n >= 3:
        lines.append("**结论**：四个关键动作已经覆盖了大部分，这场沟通可以真打。"
                     "记得把结论记进干预台账，下次谈话接着这条线。")
    else:
        lines.append(f"**结论**：还差 {4 - n} 个关键动作。建议下一句先补"
                     f"「{MOVE_LABEL[missed[0]] if missed else '共情'}」，再谈方案。")
    return "\n".join(lines)


def chips_for(kind: str) -> list[str]:
    return list(BY_KEY[kind].get("chips") or [])


def opening_chips(kind: str, ctx: dict) -> list[str]:
    """开场给的三句：按「还没做过的动作」给，直接照着说就行。"""
    return _next_chips(kind, [], ctx)
