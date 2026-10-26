"""干预建议生成：从「一个模板套所有人」改成「按成因分型 + 落到具体证据」。

旧实现的问题很直白：按风险因素查表，出勤差的学生都拿到同一句
「联系任课教师说明情况，设一个提前 20 分钟的闹钟」。数字不同，话是一个模子。

这里换三层：

1. **跨指标归因**（`_diagnose`）
   同样缺勤 12 次，人到了作业也交了、成绩还是低，是基础问题；成绩还行但人不到，
   是投入问题；平台两周没登、迟到一多半，是状态问题。三类对应的动作完全不同。

2. **证据落地**（`Ctx`）
   每条建议必须引用这名学生自己的数据：哪天缺的、哪次作业没交、哪门课、
   任课老师的答疑时间。学生和辅导员都能拿去核对，不是泛泛而谈。

3. **策略轮换**（`_pick`）
   同一分型下准备了多个等价策略，按学号稳定哈希轮换：不同学生读到的建议不同，
   同一学生每次打开都一致（演示可复现，不用 hash()，那玩意每进程随机）。
"""
from __future__ import annotations

import hashlib
from datetime import date

TODAY = date(2026, 10, 21)

PATTERNS = {
    "capability": {
        "label": "基础薄弱型",
        "note": "人基本到课、作业也交了，成绩仍明显低于班均——卡在听不懂，不是不想学。",
    },
    "motivation": {
        "label": "投入不足型",
        "note": "成绩尚有底子，但出勤与作业在掉——问题不在能力，在投入。",
    },
    "life": {
        "label": "状态异常型",
        "note": "缺勤与迟到同时偏高、学习平台长期不活跃——先看作息、情绪或生活是否有变故。",
    },
    "single": {
        "label": "单科短板型",
        "note": "多数课程正常，风险集中在一门课上——属于点状问题，别全面加码。",
    },
    "accumulation": {
        "label": "历史欠账型",
        "note": "上学期挂科较多，本学期风险很大一部分是旧账——先算清重修账再谈本学期。",
    },
    "recovery": {
        "label": "回升观察型",
        "note": "风险较上学期明显下降，正在往回走——重点是别反复，把有效做法固定下来。",
    },
    "balanced": {
        "label": "多项轻度型",
        "note": "没有单项特别突出，几项指标都在边缘——需要的是结构性调整，不是补某一项。",
    },
    "stable": {
        "label": "状态稳定型",
        "note": "各项指标在安全区间，保持即可。",
    },
}

_ORDER = ["recovery", "life", "single", "accumulation", "capability", "motivation", "balanced", "stable"]


# ---------------------------------------------------------------- 小工具

def _md(iso: str) -> str:
    """2026-10-14 -> 10 月 14 日"""
    try:
        _, m, d = iso.split("-")
        return f"{int(m)} 月 {int(d)} 日"
    except Exception:
        return iso


def _when(rec: dict) -> str:
    """10 月 14 日（周三 3-4 节）"""
    return f"{_md(rec['date'])}（{rec['weekday']} {rec['period']}）"


def _pick(sid: str, key: str, pool: list):
    """按学号稳定挑一个策略：不同学生不同，同一学生每次都一样。"""
    h = hashlib.md5(f"{sid}:{key}".encode()).hexdigest()
    return pool[int(h[:8], 16) % len(pool)]


def _short(name: str, n: int = 1) -> str:
    """取课程简称，避免建议句里课程名太长。"""
    return name.split("·")[0].strip() if n else name


# ---------------------------------------------------------------- 证据集合

class Ctx:
    """一名学生建议所需的全部证据，只算一次。"""

    def __init__(self, engine, sid: str, score: dict | None = None):
        self.engine = engine
        self.sid = sid
        self.s = engine.get(sid)
        # roster 已经把分数算过了，传进来避免 240 人名单算两遍
        self.r = score if score is not None else engine.score(sid)
        self.raw = self.r["raw"]
        self.courses = self.s["courses"]

        self.absent: list[dict] = []
        self.late: list[dict] = []
        for c in self.courses:
            for a in c["attendance"]:
                if a["status"] == "absent":
                    self.absent.append({**a, "course": c["name"], "teacher": c["teacher"],
                                        "teacher_profile": c.get("teacher_profile", {})})
                elif a["status"] == "late":
                    self.late.append({**a, "course": c["name"]})
        self.absent.sort(key=lambda x: x["date"])
        self.late.sort(key=lambda x: x["date"])

        self.missed: list[dict] = []
        self.late_hw: list[dict] = []
        for c in self.courses:
            for h in c["homework"]:
                if h["status"] == "missing":
                    self.missed.append({**h, "course": c["name"], "code": c["code"],
                                        "overdue": _days_between(h["due"], TODAY)})
                elif h["status"] == "late":
                    self.late_hw.append({**h, "course": c["name"]})
        self.missed.sort(key=lambda x: -x["overdue"])

        # 最弱的一门（期中最低）与最难的一门（挂科概率最高），两个概念不一样：
        # 前者适合"补基础"，后者适合"救分数"。
        self.worst = min(self.courses, key=lambda c: c["midterm"])
        self.probs = {p["code"]: p for p in self.r["pass_probability"]}
        self.hardest = self.courses[0]
        for c in self.courses:
            if self.probs[c["code"]]["fail_probability"] > self.probs[self.hardest["code"]]["fail_probability"]:
                self.hardest = c

        self.absence_ratio = self.raw["absence_ratio"]
        self.miss_ratio = self.raw["miss_ratio"]
        self.mid_avg = self.raw["mid_avg"]
        self.cohort_avg = self.raw["cohort_avg"]
        self.z = self.raw["z"]
        self.missed_n = self.raw["hw_assigned"] - self.raw["hw_submitted"]
        self.pattern, self.secondary = self._diagnose()

    # -- 归因 --
    def _single_gap(self) -> float:
        """一门课比第二弱的低多少分。"""
        mids = sorted((c["midterm"], c["name"]) for c in self.courses)
        return mids[1][0] - mids[0][0] if len(mids) > 1 else 0

    def _diagnose(self) -> tuple[str, str | None]:
        e = self.s["engagement"]
        gap = self.cohort_avg - self.mid_avg
        failed = self.s["history"]["failed_credits"]
        delta = self.r["trend"]["delta"]
        score: dict[str, float] = {}

        # 回升：先看趋势，往回走的人不该再加压
        if delta <= -8:
            score["recovery"] = 3.2 + min(1.0, -delta / 20)

        # 基础薄弱：人到、作业交，成绩还是上不去
        if self.absence_ratio < 0.16 and self.miss_ratio < 0.30 and (self.z <= -0.35 or gap >= 5):
            score["capability"] = 2.0 + min(1.2, gap / 16) + min(1.0, max(0.0, -self.z) / 1.6)

        # 投入不足：成绩还站得住，行为先垮
        if (self.absence_ratio >= 0.18 or self.miss_ratio >= 0.32) and self.z > -1.0:
            score["motivation"] = 1.7 + self.absence_ratio * 2.4 + self.miss_ratio * 1.4

        # 状态异常：行为垮 + 平台近乎不用 + 迟到也多
        if self.absence_ratio >= 0.14 and (e["days_since_active"] >= 9 or e["weekly_logins"] <= 2):
            score["life"] = 1.9 + min(0.8, e["days_since_active"] / 16) + min(0.6, len(self.late) / 24)

        # 单科短板：一门课显著拖后腿
        fp = self.probs[self.worst["code"]]["fail_probability"]
        if self._single_gap() >= 10 and fp >= 0.35 and self.absence_ratio < 0.28:
            score["single"] = 1.9 + min(1.0, self._single_gap() / 20)

        # 历史欠账：数据里多数人挂科在 2-6 学分，6 学分已接近一学期两门课，
        # 阈值定在 6 才能真的浮出来，否则这套判断永远走不到。
        if failed >= 6:
            score["accumulation"] = 1.7 + min(1.0, failed / 12) + (0.3 if failed >= 9 else 0)

        if not score:
            score["balanced" if self.r["score"] >= 32 else "stable"] = 1.0

        ranked = sorted(score.items(), key=lambda kv: (-kv[1], _ORDER.index(kv[0])))
        primary = ranked[0][0]
        secondary = ranked[1][0] if len(ranked) > 1 and ranked[1][1] > 1.2 else None
        return primary, secondary

    # -- 常被引用的短句 --
    def latest_absent(self) -> dict | None:
        return self.absent[-1] if self.absent else None

    def absent_top_course(self) -> tuple[str, int]:
        """缺勤次数最多的一门课。"""
        bag: dict[str, int] = {}
        for a in self.absent:
            bag[a["course"]] = bag.get(a["course"], 0) + 1
        if not bag:
            return self.hardest["name"], 0
        name = max(bag, key=lambda k: bag[k])
        return name, bag[name]

    def recent_absent(self) -> int:
        """近三周缺了几次，用来判断是"偶发"还是"持续"。"""
        return sum(1 for a in self.absent if a["week"] >= 5)

    def prof(self, course: dict | None = None) -> dict:
        c = course or self.hardest
        return c.get("teacher_profile") or {"name": c["teacher"]}

    def prof_line(self, course: dict | None = None) -> str:
        """张三（副教授）· 周二 14:00-16:00 · 信息楼 A503"""
        p = self.prof(course)
        bits = [b for b in (p.get("title"), p.get("office_hour"), p.get("office")) if b]
        return f"{p.get('name', '')}（{' · '.join(bits)}）" if bits else p.get("name", "")

    def hw_line(self, item: dict) -> str:
        over = item["overdue"]
        when = f"已逾期 {over} 天" if over > 0 else "今天截止"
        return f"《{item['course']}》{item['title']}（{_md(item['due'])} 截止，{when}）"


def _days_between(iso: str, ref: date) -> int:
    try:
        y, m, d = (int(x) for x in iso.split("-"))
        return (ref - date(y, m, d)).days
    except Exception:
        return 0


# ---------------------------------------------------------------- 策略库
# 每个因子给 4 组左右等价但侧重不同的策略，靠 _pick 轮换。

def _att_backfill(c: Ctx) -> dict:
    l = c.latest_absent() or c.absent[0]
    name, n = c.absent_top_course()
    # 单科短板型别到处补，只补那门拖后腿的课
    if c.pattern == "single":
        name = c.worst["name"]
        n = sum(1 for a in c.absent if a["course"] == name)
    course = next((x for x in c.courses if x["name"] == name), c.hardest)
    return {
        "factor": "attendance",
        "tag": "补课优先",
        "title": f"把缺掉的 {c.raw['absent']} 次课按课程排一次队，先补《{name}》",
        "detail": f"最近一次是 {_when(l)}那次《{l['course']}》。这门课缺了 {n} 次，落下的内容最多，"
                  f"先找同班同学借笔记把这 {n} 次的板书补上，再决定要不要找老师单独讲一遍。",
        "steps": [
            f"今天借《{name}》缺课那几节的笔记，抄进自己的本子（不是拍照存着）",
            f"补完后带着问题去{c.prof_line(course)}，只问缺的那几节",
            "补完在笔记上写一句「这节讲了什么」，讲不出来说明还没补进去",
        ],
        "owner": "学生",
        "deadline": "本周内",
    }


def _att_teacher(c: Ctx) -> dict:
    name, n = c.absent_top_course()
    course = next((x for x in c.courses if x["name"] == name), c.hardest)
    held = course.get("sessions_held") or 14
    ratio = n / max(1, held)
    if ratio >= 0.22:
        stake = f"已缺 {n}/{held} 次（{ratio:.0%}），可能触及取消考试资格的线"
    elif ratio >= 0.12:
        stake = f"已缺 {n}/{held} 次（{ratio:.0%}），平时分会被扣掉一块"
    else:
        stake = f"已缺 {n}/{held} 次，次数不算多，但要看学校口径会不会累计"
    return {
        "factor": "attendance",
        "tag": "先问清楚规则",
        "title": f"先问《{name}》老师：缺的 {n} 次能不能补",
        "detail": f"《{name}》{stake}。找{c.prof_line(course)}当面问清三件事："
                  f"还能不能补、已缺的算不算旷课、能不能用作业或补课的方式补回平时分。",
        "steps": [
            f"按答疑时间去{c.prof_line(course)}，别在课后堵人",
            "带上已补的笔记，说明哪几节是自己看回放补的",
            "把老师给的口径记下来，回来告诉辅导员",
        ],
        "owner": "学生 + 任课教师",
        "deadline": "本周内",
    }


def _att_anchor(c: Ctx) -> dict:
    a = c.absent
    bag: dict[str, int] = {}
    for x in a:
        bag[x["weekday"]] = bag.get(x["weekday"], 0) + 1
    top_day, top_n = max(bag.items(), key=lambda kv: kv[1]) if bag else ("", 0)
    morning = sum(1 for x in a if x["period"].startswith("1-2"))
    if morning >= max(3, len(a) // 3):
        focus = f"{morning} 次是 1-2 节的早课"
        why = "早课缺勤多数不是「不想去」，是起不来。别一上来要求全勤，先把第一节课的出勤单独拉出来看。"
    else:
        focus = f"「{top_day}」这一天就占了 {top_n} 次"
        why = f"同一时段反复缺，通常和当天的实际安排有关（兼职、通勤、连堂太累）。先弄清{top_day}这一天有什么别的事。"
    return {
        "factor": "attendance",
        "tag": "改作息",
        "title": f"缺勤 {c.raw['absent']} 次里，{focus}——先动作息，别先谈态度",
        "detail": why + " 设一个能真正做到的小目标，比要求全勤有效。",
        "steps": [
            "固定一个睡觉时间，手机放桌上充电（不放床头）",
            "找一门早课的同桌，课前 30 分钟互相发一条消息",
            "连续 5 个工作日达标就奖励自己一次，不达标只重来、不补考",
        ],
        "owner": "学生 + 室友/同桌",
        "deadline": "两周内",
    }


def _att_gap(c: Ctx) -> dict:
    name, n = c.absent_top_course()
    if n < 3:
        return _att_backfill(c)
    return {
        "factor": "attendance",
        "tag": "查是不是听不懂",
        "title": f"先确认《{name}》缺的 {n} 次，是躲课还是听不懂",
        "detail": "缺勤集中在一门课上，通常不是懒，是坐在教室里听不懂、干脆不来。"
                  "和本人确认这一点，再决定是补课还是换学习方式。",
        "steps": [
            "问一句：「这门课你坐第几排？听不听得懂？」",
            "如果听不懂，先补上一次课的内容再进教室",
            "如果只是没兴趣，改为「每次课记 3 个关键词」的低门槛要求",
        ],
        "owner": "辅导员",
        "deadline": "本周内",
    }


def _hw_triage(c: Ctx) -> dict:
    m = c.missed
    if c.pattern == "single":
        own = [x for x in m if x["course"] == c.worst["name"]]
        if own:
            m = own
    first = m[0]
    recover = [x for x in m if x["overdue"] <= 10]
    return {
        "factor": "homework",
        "tag": "挑补得回来的",
        "title": f"未交 {len(m)} 次作业，先补逾期 10 天内的 {len(recover)} 次",
        "detail": f"拖得最久的一次是 {_md(first['due'])} 截止的《{first['course']}》{first['title']}，"
                  f"逾期 {first['overdue']} 天，补回来把握不大。先补逾期短的，性价比最高。",
        "steps": [
            f"按截止时间排个序，先做 {_md(recover[0]['due']) if recover else _md(first['due'])} 那一次",
            "每次只补一门课，别六门摊开同时补",
            "补完截个图，作为和老师沟通的凭据",
        ],
        "owner": "学生",
        "deadline": "下次课前",
    }


def _hw_window(c: Ctx) -> dict:
    pool = c.missed
    if c.pattern == "single":
        own = [x for x in pool if x["course"] == c.worst["name"]]
        pool = own or pool
    top = pool[0]
    course = next((x for x in c.courses if x["code"] == top["code"]), c.worst)
    return {
        "factor": "homework",
        "tag": "问补交窗口",
        "title": f"先问《{top['course']}》还能不能补交——{len(c.missed)} 次未交里有几次是白丢的",
        "detail": f"《{top['course']}》{top['title']}，{_md(top['due'])} 截止、逾期 {top['overdue']} 天。有些课允许交 60% 分数，有些直接 0 分，"
                  f"可以直接问{c.prof_line(course)}，别自己先判死刑。",
        "steps": [
            "整理一张未交清单（课程、作业名、截止日）",
            "带着清单去答疑时间问一次，逐个确认能否补",
            "能补的当场定下交的时间，写在日历里",
        ],
        "owner": "学生 + 任课教师",
        "deadline": "本周内",
    }


def _hw_slot(c: Ctx) -> dict:
    return {
        "factor": "homework",
        "tag": "固定时段",
        "title": f"把 {c.missed_n} 次未交作业压进两个固定时段，而不是「有空再写」",
        "detail": "作业不是靠意志力交的，是靠时间表交的。「有空再写」等于不写。"
                  "每周固定两个 90 分钟写作业，写不完也停，下一周继续。",
        "steps": [
            "选两个不会被打断的时段（比如周二晚、周日下午）",
            "进自习室前把手机放包里，只带纸笔和电脑",
            "90 分钟结束就收，没写完记下卡在哪，下次从那儿继续",
        ],
        "owner": "学生",
        "deadline": "本周内",
    }


def _hw_pair(c: Ctx) -> dict:
    return {
        "factor": "homework",
        "tag": "找同伴监督",
        "title": f"{c.missed_n} 次没交这件事，可以借一个人的手",
        "detail": "自己盯自己，多数人盯不住。找同班一个作业交得齐的同学，约成「他写完喊你一声」，"
                  "比任何提醒软件都管用。",
        "steps": [
            "找一名同班同学，明确约定互相提醒交作业",
            "把两门课的截止日记进同一个日历，共享给对方",
            "连续漏交一次，就换成一起自习",
        ],
        "owner": "学生 + 同班同学",
        "deadline": "两周内",
    }


def _exam_prereq(c: Ctx) -> dict:
    w = c.worst
    stat = c.engine.course_stats[w["code"]]
    return {
        "factor": "exam",
        "tag": "补前置",
        "title": f"《{w['name']}》期中 {w['midterm']} 分（班均 {stat['mean']}），问题多半在第 1-2 章",
        "detail": f"这门课缺勤只有 {w['absent']} 次、作业交了 {w['hw_submitted']}/{w['hw_assigned']}，说明人是在的。"
                  f"成绩上不去，通常是前两章的概念没打通，后面越听越懵。回头把前两章例题重做一遍。",
        "steps": [
            f"把《{w['name']}》教材前两章例题遮住答案重做，做不出的标记出来",
            "只带着这些标记去答疑，问具体那一步",
            "补完再重做一次期中卷，看分数变化",
        ],
        "owner": "学生 + 学业导师",
        "deadline": "两周内",
    }


def _exam_office(c: Ctx) -> dict:
    w = c.worst
    return {
        "factor": "exam",
        "tag": "用足答疑",
        "title": f"约一次{c.prof_line(w)}，把《{w['name']}》的错题过一遍",
        "detail": f"《{w['name']}》期中 {w['midterm']} 分，比班均低 "
                  f"{round(c.engine.course_stats[w['code']]['mean'] - w['midterm'], 1)} 分。"
                  f"任课老师每周有固定答疑时间，多数学生从来不去——这是最被浪费的资源。",
        "steps": [
            "考前把错题按「不会/粗心/没看到」分三类",
            "只带「不会」那一类去答疑，一次问 3 题",
            "回来当天把答案写成自己的话",
        ],
        "owner": "学生 + 任课教师",
        "deadline": "两周内",
    }


def _exam_paper(c: Ctx) -> dict:
    w = c.worst
    return {
        "factor": "exam",
        "tag": "对着题型练",
        "title": f"《{w['name']}》别从头复习，先摸清考什么题型",
        "detail": "分数低的时候，「把书看一遍」是最没效率的做法。先拿到近两年卷子或课后重点题，"
                  "按题型归类，再倒回去补对应的知识点。",
        "steps": [
            "找学长或助教要一份往年题",
            "把题目按章节归堆，看哪几章占分最多",
            "只攻占分最高的两章，做透再扩展",
        ],
        "owner": "学生",
        "deadline": "两周内",
    }


def _exam_single(c: Ctx) -> dict:
    w = c.worst
    return {
        "factor": "exam",
        "tag": "单点突破",
        "title": f"这学期只救《{w['name']}》一门，其他先维持",
        "detail": f"《{w['name']}》{w['midterm']} 分，比第二弱的课低 {round(c._single_gap(), 1)} 分。"
                  f"科目多的时候平均用力等于都没救，集中两周只攻一门，先把最可能挂的拉回 60 分线。",
        "steps": [
            "把其他课的作业压到最低要求，腾出每周 6 小时",
            "这 6 小时全部给《" + w["name"] + "》",
            "两周后小测看是否过 60，过了再换下一门",
        ],
        "owner": "学生 + 学业导师",
        "deadline": "两周内",
    }


def _eng_replay(c: Ctx) -> dict:
    e = c.s["engagement"]
    return {
        "factor": "engagement",
        "tag": "先恢复节奏",
        "title": f"平台 {e['days_since_active']} 天没登录，先把上周的课回放看掉",
        "detail": f"每周登录 {e['weekly_logins']} 次、视频完成率 {round(e['video_rate'] * 100)}%。"
                  f"先别看全部，只看最近一周的 3 段回放，每段 30 分钟，看完做课后小测。",
        "steps": [
            "今天只看一段回放，看完立刻做对应小测",
            "连续 3 天各看一段，把断掉的节奏接上",
            "第四天开始按课程表预习，不再补回放",
        ],
        "owner": "学生",
        "deadline": "本周内",
    }


def _eng_micro(c: Ctx) -> dict:
    return {
        "factor": "engagement",
        "tag": "降低启动成本",
        "title": f"把「学习」拆成 15 分钟能做完的动作（当前每周登录 {c.s['engagement']['weekly_logins']} 次）",
        "detail": "登录次数低，往往不是不想学，是每次打开都觉得「要干很多事」于是不打开。"
                  "把入口降到「打开—看一页—关掉」，先恢复打开这个动作。",
        "steps": [
            "设一个每天 21:00 的提醒，只要求打开平台",
            "打开后只做一件事：看一页讲义或一道题",
            "做完就在日历上打勾，连续 7 天算过关",
        ],
        "owner": "学生",
        "deadline": "一周内",
    }


def _eng_notify(c: Ctx) -> dict:
    return {
        "factor": "engagement",
        "tag": "让提醒替你盯",
        "title": "把作业截止和上课时间交给日历，不再靠记",
        "detail": f"平台 {c.s['engagement']['days_since_active']} 天未活跃，说明主动查看的习惯还没建立。"
                  f"与其要求「每天登录」，不如让提醒推着走：所有截止日提前 2 天提醒一次。",
        "steps": [
            "把这学期剩余作业截止日一次性录进手机日历",
            "每条设两个提醒：提前 2 天、当天早上",
            "每周日花 5 分钟过一遍下周安排",
        ],
        "owner": "学生",
        "deadline": "本周内",
    }


def _hist_window(c: Ctx) -> dict:
    h = c.s["history"]
    return {
        "factor": "history",
        "tag": "算清重修账",
        "title": f"上学期挂的 {h['failed_credits']} 学分，先查清哪几门还能重修",
        "detail": "旧账不清，本学期再怎么努力分数也上不去。重修一般有窗口期和门数限制，"
                  "先确认能修几门、什么时候报名，再谈本学期安排。",
        "steps": [
            "去教务系统查不及格课程清单与重修开课时间",
            "算一下按当前进度毕业还差多少学分",
            "本学期最多再压 1 门重修课，避免和正课冲突",
        ],
        "owner": "学生 + 教务",
        "deadline": "选课结束前",
    }


def _hist_one(c: Ctx) -> dict:
    h = c.s["history"]
    return {
        "factor": "history",
        "tag": "一次只清一门",
        "title": f"累计挂科 {h['failed_credits']} 学分，这个学期只清一门",
        "detail": "想把旧账一次清完，结果往往是本学期又挂新的。挑学分最少、最有把握的一门先过，"
                  "拿到「我能过」的证据比什么都重要。",
        "steps": [
            "从挂科清单里挑学分最少的一门",
            "查它的考核方式（考试/大作业），选自己更擅长的",
            "这一门过了再考虑第二门",
        ],
        "owner": "学生 + 教务",
        "deadline": "本学期",
    }


def _credit_summer(c: Ctx) -> dict:
    return {
        "factor": "credit",
        "tag": "补进度",
        "title": f"学分落后 {c.raw['credits_deficit']} 分，暑期小学期是最省力的补法",
        "detail": "小学期课程集中、通过率高，两门通识课就能补 4-6 学分。"
                  "本学期不要再退课，退一门要补两门。",
        "steps": [
            "查暑期小学期开课清单与选课时间",
            "挑 2 门通过率高的通识课，别挑硬课",
            "本学期任何一门都先别退",
        ],
        "owner": "学生 + 教务",
        "deadline": "本学期",
    }


def _credit_plan(c: Ctx) -> dict:
    return {
        "factor": "credit",
        "tag": "重排计划",
        "title": "按「还能不能按期毕业」重排一次选课计划",
        "detail": f"已修 {c.s['credits']['earned']} 学分，培养方案 {c.s['credits']['plan_total']} 学分，"
                  f"缺口 {c.raw['credits_deficit']} 分。算清楚剩余学期每学期要修多少，比焦虑有用。",
        "steps": [
            "列出剩余学期数与每学期可修学分上限",
            "把必修课先排满，选修课往后放",
            "把计划写下来交给辅导员留一份",
        ],
        "owner": "学生 + 教务",
        "deadline": "本月内",
    }


def _root_capability(c: Ctx) -> dict:
    w = c.worst
    return {
        "factor": "root",
        "tag": "先定性质",
        "title": f"人到了、作业交了大半（{c.raw['hw_submitted']}/{c.raw['hw_assigned']}），还是只考 "
                 f"{w['midterm']} 分——不是态度问题",
        "detail": f"缺勤 {c.raw['absent']} 次、作业交 {c.raw['hw_submitted']}/{c.raw['hw_assigned']}，"
                  f"但期中均分 {c.mid_avg}（班均 {c.cohort_avg}）。行为没问题，是某几门课的基础断了。"
                  f"别再谈「要努力」，直接定位到《{w['name']}》哪一章开始听不懂。",
        "steps": [
            f"问：「从哪一章开始跟不上的？」把断点找出来",
            "只补断点之前的两章，不要从头再来",
            f"安排一次{c.prof_line(w)}的答疑",
        ],
        "owner": "辅导员 + 学业导师",
        "deadline": "本周内",
    }


def _root_motivation(c: Ctx) -> dict:
    return {
        "factor": "root",
        "tag": "先定性质",
        "title": f"期中 {c.mid_avg} 分不算差，缺勤 {c.raw['absent']} 次、少交 {c.missed_n} 次——"
                 f"别用补课解决投入问题",
        "detail": f"期中均分 {c.mid_avg}，接近班均 {c.cohort_avg}，说明底子在；"
                  f"但缺勤 {c.raw['absent']} 次、作业少交 {c.missed_n} 次。这类学生补课没用，"
                  f"要找的是「为什么不想来」。",
        "steps": [
            "先问近况，别先报缺勤数字",
            "问一个具体问题：「最近一次觉得这门课有意思，是什么时候？」",
            "只约定一件事，越小越好（比如下周来上 3 次课）",
        ],
        "owner": "辅导员",
        "deadline": "本周内",
    }


def _root_life(c: Ctx) -> dict:
    e = c.s["engagement"]
    return {
        "factor": "root",
        "tag": "先定性质",
        "title": f"先别谈成绩：平台 {e['days_since_active']} 天没登录、迟到 {len(c.late)} 次、"
                 f"缺勤 {c.raw['absent']} 次",
        "detail": "缺勤与迟到同时高、平台长期不活跃，通常指向作息紊乱、情绪问题或家庭/经济变故。"
                  "这种状态下加压只会更糟，先确认生活层面发生了什么。",
        "steps": [
            "问作息：「最近几点睡？」比问成绩有效",
            "观察是否有情绪低落、经济压力、兼职过度的迹象",
            "必要时转介学校心理中心，不要自己硬扛",
        ],
        "owner": "辅导员 (+ 心理中心)",
        "deadline": "本周内",
    }


def _root_single(c: Ctx) -> dict:
    w = c.worst
    return {
        "factor": "root",
        "tag": "先定性质",
        "title": f"风险集中在一门课：《{w['name']}》比第二弱的低 {round(c._single_gap(), 1)} 分",
        "detail": f"其余课程期中均分都在正常范围，问题不是全面滑坡，是这一门卡住了。"
                  f"全面加码只会让他更抵触，集中资源处理这一门就够了。",
        "steps": [
            f"确认《{w['name']}》卡在哪（听不懂 / 不喜欢老师 / 觉得没用）",
            "只给这一门定目标，其他课维持现状",
            "两周后再看这一门的分数变化",
        ],
        "owner": "辅导员 + 学业导师",
        "deadline": "本周内",
    }


def _root_accumulation(c: Ctx) -> dict:
    h = c.s["history"]
    return {
        "factor": "root",
        "tag": "先定性质",
        "title": f"分数里有一大块是旧账：挂科 {h['failed_credits']} 学分、GPA {h['gpa']}",
        "detail": "历史欠账会把风险分整体抬高，看上去像「这学期也全面崩了」，实际未必。"
                  "先把旧账和本学期分开看，学生才不会被数字吓住。",
        "steps": [
            "把本学期课程表现单独拉出来讲",
            "旧账只谈「这学期清一门」",
            "把重修报名时间写进跟进表",
        ],
        "owner": "辅导员 + 教务",
        "deadline": "本周内",
    }


def _root_recovery(c: Ctx) -> dict:
    d = c.r["trend"]["delta"]
    return {
        "factor": "root",
        "tag": "先定性质",
        "title": f"在往回走（较上学期 {d:+.0f} 分），重点是别反复",
        "detail": "进步期的学生最怕被当成问题学生反复敲打——那会让刚建立的行为退回原点。"
                  "这次谈话的目的应该是确认「哪件事起了作用」，然后固定下来。",
        "steps": [
            "先肯定具体变化（哪门课出勤变好了），别泛泛表扬",
            "问：「这学期你做了什么不一样的事？」",
            "把那个做法变成固定安排，而不是临时努力",
        ],
        "owner": "辅导员",
        "deadline": "本周内",
    }


def _root_balanced(c: Ctx) -> dict:
    return {
        "factor": "root",
        "tag": "先定性质",
        "title": f"没有单项特别差，但缺勤 {c.raw['absent']}、少交 {c.missed_n}、期中 {c.mid_avg} "
                 f"全在边缘——要改的是节奏",
        "detail": f"缺勤 {c.raw['absent']} 次、作业少交 {c.missed_n} 次、期中 {c.mid_avg} 分，"
                  f"每一项都不到红线，合起来才把风险推上去。这种情况改一件事不够，要改节奏。",
        "steps": [
            "先定一个固定作息表，把上课、作业、自习都排进去",
            "每周日花 10 分钟复盘：哪件事没做到，为什么",
            "连续三周做到，再看风险分变化",
        ],
        "owner": "学生 + 辅导员",
        "deadline": "两周内",
    }


def _keep(c: Ctx) -> dict:
    """状态正常的学生：给的是维持策略，也有多种说法。"""
    pool = [
        ("保持当前节奏，别在期中后松劲",
         f"各项指标在安全区间。期中之后课程难度会上一档，把现在这套作息原样保持到期末就可以。"),
        ("把有效的做法记下来，别让它只停留在感觉里",
         "现在状态不错，但很多人期末崩盘是因为「不知道自己之前做对了什么」。写下三条现在在坚持的习惯。"),
        ("提前给下半学期留一点缓冲",
         f"当前 {c.raw['absent']} 次缺勤、作业交齐 {c.raw['hw_submitted']}/{c.raw['hw_assigned']}，余量充足。"
         "建议把最难的一门课提前两周开始复习，别挤到考前。"),
    ]
    title, detail = _pick(c.sid, "keep", pool)
    return {
        "factor": "keep",
        "tag": "维持",
        "title": title,
        "detail": detail,
        "steps": [],
        "owner": "学生",
        "deadline": "持续",
        "priority": "low",
    }


ROOT = {
    "capability": _root_capability,
    "motivation": _root_motivation,
    "life": _root_life,
    "single": _root_single,
    "accumulation": _root_accumulation,
    "recovery": _root_recovery,
    "balanced": _root_balanced,
}

POOL = {
    "attendance": [_att_backfill, _att_teacher, _att_anchor, _att_gap],
    "homework": [_hw_triage, _hw_window, _hw_slot, _hw_pair],
    "exam": [_exam_prereq, _exam_office, _exam_paper, _exam_single],
    "engagement": [_eng_replay, _eng_micro, _eng_notify],
    "history": [_hist_window, _hist_one],
    "credit": [_credit_summer, _credit_plan],
}

# 某些策略只在特定成因下才成立。比如「这学期只救一门」对多项轻度型是误导，
# 「先补前置章节」对投入不足型是答非所问。没列出的策略对所有成因都适用。
FITS = {
    "_exam_single": {"single"},
    "_exam_prereq": {"capability", "single", "balanced"},
    "_att_gap": {"capability", "motivation", "single"},
    "_att_anchor": {"motivation", "life", "balanced"},
    "_att_teacher": {"motivation", "life", "balanced", "single"},
    "_hw_pair": {"motivation", "balanced"},
    "_eng_replay": {"life", "capability", "balanced", "stable"},
    "_eng_micro": {"motivation", "life"},
    "_hist_window": {"accumulation", "balanced", "motivation", "life", "recovery"},
    "_hist_one": {"accumulation", "balanced", "life", "recovery"},
}


def _pool(factor: str, pattern: str) -> list:
    """按成因筛掉不成立的策略。筛空了就跳过该因子，不要退回整套。"""
    return [b for b in POOL[factor] if pattern in FITS.get(b.__name__, {pattern})]

# 不同成因下，优先把哪些因子的建议放前面（第一个是主攻方向）
FOCUS = {
    "capability": ["exam", "engagement", "attendance", "homework", "history", "credit"],
    "motivation": ["homework", "attendance", "exam", "engagement", "history", "credit"],
    # 状态异常型先恢复节奏（平台/回放），再谈缺勤规则——顺序反了会把人推远
    "life": ["engagement", "attendance", "exam", "homework", "history", "credit"],
    "single": ["exam", "homework", "attendance", "engagement", "history", "credit"],
    "accumulation": ["history", "credit", "exam", "attendance", "homework", "engagement"],
    "recovery": ["engagement", "homework", "attendance", "exam", "history", "credit"],
    "balanced": ["attendance", "homework", "exam", "engagement", "history", "credit"],
    "stable": ["attendance", "homework", "exam", "engagement", "history", "credit"],
}

# 成因决定主攻方向：分数高不等于该先谈它
LEAD = {
    "life": "engagement",
    "recovery": "engagement",
    "single": "exam",
    "accumulation": "history",
}


def _rank(factor_points: dict, pattern: str) -> list[str]:
    ranked = sorted(
        [k for k in POOL if factor_points.get(k, 0) >= 3],
        key=lambda k: (-factor_points.get(k, 0), FOCUS[pattern].index(k)),
    )
    lead = LEAD.get(pattern)
    if lead and lead in ranked:
        ranked.remove(lead)
        ranked.insert(0, lead)
    return ranked


DEADLINE = {
    "attendance": {"high": "本周五前", "medium": "本周内"},
    "homework": {"high": "下次课前", "medium": "本周内"},
    "exam": {"high": "两周内", "medium": "三周内"},
    "engagement": {"high": "本周内", "medium": "两周内"},
    "history": {"high": "选课结束前", "medium": "本月内"},
    "credit": {"high": "本月内", "medium": "本学期"},
}


# ---------------------------------------------------------------- 支持资源

def _support(c: Ctx) -> list[dict]:
    """能真正指给人用的资源，都带具体时间和地点。"""
    out: list[dict] = []
    w, h = c.worst, c.hardest
    p = c.prof(h)
    if p.get("office_hour") or p.get("email"):
        out.append({
            "kind": "任课教师答疑",
            "text": f"{p.get('name')}《{h['name']}》· {p.get('office_hour') or '时间待约'} · {p.get('office') or ''}".strip(" ·"),
            "contact": p.get("email", ""),
        })
    if c.pattern in ("capability", "single", "balanced") and w["code"] != h["code"]:
        p2 = c.prof(w)
        out.append({
            "kind": "学业导师",
            "text": f"{p2.get('name')}《{w['name']}》· {p2.get('office_hour') or '时间待约'}".strip(" ·"),
            "contact": p2.get("email", ""),
        })
    out.append({
        "kind": "学业辅导中心",
        "text": "一对一学业咨询，可指定课程；提前 3 天预约",
        "contact": "studysupport@univ.edu.cn",
    })
    if c.pattern == "life":
        out.append({
            "kind": "心理健康教育中心",
            "text": "免费咨询，可匿名预约；工作日 9:00-17:00",
            "contact": "counsel@univ.edu.cn",
        })
    if c.pattern == "accumulation" or c.s["history"]["failed_credits"] >= 6:
        out.append({
            "kind": "教务重修窗口",
            "text": "重修报名与学分认定，线下办理需带学生证",
            "contact": "教务处 3 号窗口",
        })
    if c.pattern == "motivation":
        out.append({
            "kind": "同伴学习小组",
            "text": f"本班《{h['name']}》学习小组每周两次，可申请加入",
            "contact": "辅导员登记",
        })
    return out[:3]


def _watch(c: Ctx) -> dict:
    """下次复查看什么，尽量具体到指标和课程。"""
    h = c.hardest
    if c.pattern == "stable":
        return {"when": "期末前", "what": "不必单独跟进，随班级周报复查即可"}
    if c.pattern == "recovery":
        return {"when": "两周后", "what": f"确认回升是否延续：看《{h['name']}》的作业是否仍按时交，出勤是否稳定"}
    if c.pattern == "life":
        return {"when": "一周后", "what": "先看平台登录是否恢复、迟到是否减少，不看分数"}
    if c.missed:
        first = c.missed[0]
        return {"when": "一周后", "what": f"看《{first['course']}》{first['title'][:14]}…是否补交，未交则升级处理"}
    if c.absent:
        name, n = c.absent_top_course()
        return {"when": "一周后", "what": f"看《{name}》接下来两次课是否到课，当前已缺 {n} 次"}
    return {"when": "两周后", "what": "复查期中后小测与作业提交率"}


# ---------------------------------------------------------------- 对外

def plan(engine, sid: str, score: dict | None = None) -> dict:
    """完整的个性化干预方案：判断 + 证据 + 动作 + 资源 + 复查点。"""
    c = Ctx(engine, sid, score)
    meta = PATTERNS[c.pattern]

    # 1) 归纳性判断（先讲性质，再讲数字）
    factor_points = {p["key"]: p["points"] for p in c.r["factors"]}
    evidence = [f"风险分 {c.r['score']}（{c.r['level_label']}），较上学期 {c.r['trend']['delta']:+.0f} 分"]

    if c.absent:
        name, n = c.absent_top_course()
        evidence.append(f"缺勤 {c.raw['absent']} 次，其中《{name}》{n} 次，最近一次 {_when(c.absent[-1])}")
    if c.missed:
        evidence.append(f"作业未交 {len(c.missed)} 次，最久的一次逾期 {c.missed[0]['overdue']} 天")
    if c.mid_avg < c.cohort_avg:
        evidence.append(f"期中均分 {c.mid_avg}，低于班均 {round(c.cohort_avg - c.mid_avg, 1)} 分")
    if c.s["engagement"]["days_since_active"] >= 7:
        evidence.append(f"学习平台已 {c.s['engagement']['days_since_active']} 天未活跃")
    if c.s["history"]["failed_credits"] >= 6:
        evidence.append(
            f"上学期挂科 {c.s['history']['failed_credits']} 学分、GPA {c.s['history']['gpa']}"
        )

    # 2) 动作：归因结论单独放（前端用它渲染"这次要解决的是什么"），
    #    建议清单只留"可以立刻做的"，避免两处说同一件事。
    actions: list[dict] = []
    root_act = None
    if c.pattern == "stable":
        # 状态正常的学生不该被塞「缺的 2 次还能不能救」这种警报式建议
        actions.append(_keep(c))
    else:
        if c.pattern in ROOT:
            root_act = ROOT[c.pattern](c)

        for key in _rank(factor_points, c.pattern):
            if len(actions) >= 4:
                break
            pool = _pool(key, c.pattern)
            if not pool:
                continue
            builder = _pick(sid, key, pool)
            act = builder(c)
            pts = factor_points.get(key, 0)
            act["priority"] = "high" if pts >= 10 else ("medium" if pts >= 5 else "low")
            act["deadline"] = DEADLINE.get(key, {}).get(act["priority"], act.get("deadline", "本周内"))
            act.setdefault("owner", "学生")
            act["points"] = round(pts, 1)
            actions.append(act)

    if not actions:
        actions.append(_keep(c))

    # 3) 一句话版（名单、卡片上用）
    line = actions[0]["title"]
    if len(line) > 26:
        line = actions[0].get("tag", "本周动作")

    return {
        "pattern": c.pattern,
        "pattern_label": meta["label"],
        "diagnosis": meta["note"],
        "evidence": evidence,
        "headline": root_act["title"] if root_act else actions[0]["title"],
        "one_liner": actions[0].get("tag", "本周动作"),
        # 归因动作：定性用，带"从这一步开始"的具体动作/提问
        "root": root_act,
        "first_steps": root_act.get("steps", []) if root_act else [],
        # 执行动作：可以立刻安排的事
        "actions": actions,
        "support": _support(c),
        "watch": _watch(c),
        "counselor_tip": _tip(c),
    }


def _tip(c: Ctx) -> str:
    """给辅导员的一句切入建议，按成因换口径。"""
    w = c.worst
    tips = {
        "capability": [
            f"别问「为什么不好好学」，问「《{w['name']}》从第几章开始听不懂」——他会立刻具体起来。",
            f"先把「学不会」和「不想学」分开。这个学生人到了、作业交了，缺的是《{w['name']}》的基础。",
        ],
        "motivation": [
            "这类学生不怕被说成绩差，怕被问「你最近在忙什么」——那才是真问题。",
            "别用补课解决动力问题。先弄清他每天的时间花在哪，再谈课程。",
        ],
        "life": [
            "第一句别问成绩，问「最近几点睡」。作息乱的背后往往有更实际的事。",
            "缺勤和迟到一起高，通常是生活出了问题。先解决状态，再谈出勤率。",
        ],
        "single": [
            f"只用谈一门课《{w['name']}》。全面加码会让本来正常的部分也开始崩。",
            f"先把「只有这一门不行」说清楚，他的抵触会小很多。",
        ],
        "accumulation": [
            "把旧账和本学期分开讲。只说总分多少，学生会直接放弃。",
            "先算清重修能修几门、什么时候报名，再谈这学期怎么过。",
        ],
        "recovery": [
            "这次谈话重点是「你做了什么不一样的事」，不是再提一次风险分。",
            "在往回走的学生，最怕被当成问题学生反复敲打。",
        ],
        "balanced": [
            "没有单项特别差，别挑一项猛攻。谈的是作息和节奏，不是某一门课。",
            "让他自己说哪一周最乱，比辅导员列举数据有效。",
        ],
        "stable": [
            "状态正常，谈的是「怎么保持」，不必再走预警流程。",
        ],
    }
    return _pick(c.sid, "tip", tips[c.pattern])


def brief(engine, sid: str, score: dict | None = None) -> dict:
    """名单用的一行建议，不做完整方案，省算力。"""
    c = Ctx(engine, sid, score)
    meta = PATTERNS[c.pattern]
    acts = []
    factor_points = {p["key"]: p["points"] for p in c.r["factors"]}
    for key in _rank(factor_points, c.pattern):
        pool = _pool(key, c.pattern)
        if pool:
            acts.append(_pick(sid, key, pool)(c))
            break
    if c.pattern in ROOT:
        acts.append(ROOT[c.pattern](c))
    head = acts[0] if acts else _keep(c)
    return {
        "pattern": c.pattern,
        "pattern_label": meta["label"],
        "line": head["title"],
        "tag": head.get("tag", ""),
    }
