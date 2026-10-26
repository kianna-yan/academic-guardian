"""模拟学情数据源。

真实项目里这一层对接教务系统 / 学习平台 / 一卡通，这里用确定性随机生成，
保证每次启动看到的是同一批学生，方便演示和答辩复现。
"""
from __future__ import annotations

import random
from datetime import date, timedelta

SEED = 20261018
TODAY = date(2026, 10, 21)

CLASSES = ["计科2401", "计科2402", "计科2403", "计科2404", "计科2405", "计科2406"]

SURNAMES = list("王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦方白邹孟熊秦邱江尹薛段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤")
GIVEN_M = ["浩然", "子轩", "宇航", "俊杰", "明轩", "志强", "文博", "嘉豪", "天宇", "泽宇",
           "一鸣", "梓豪", "瑞霖", "思远", "皓宇", "昊天", "博文", "晨阳", "子墨", "家豪",
           "永康", "伟诚", "锦程", "立轩", "承泽", "书豪", "若飞", "亦辰", "沐阳", "少卿"]
GIVEN_F = ["雨欣", "梦琪", "佳怡", "思彤", "欣怡", "语嫣", "子涵", "梓萱", "嘉琪", "若曦",
           "雨桐", "晓彤", "诗涵", "一诺", "婉清", "静怡", "佳宁", "可欣", "雅涵", "沐瑶",
           "思远", "明月", "静姝", "佩瑶", "婉如", "语晨", "亦菲", "舒雅", "书瑶", "清越"]

# 2026 秋季学期（第 8 教学周）
# slots 是每周两次课的固定时段，考勤明细按它逐次落到具体日期上。
COURSES = [
    {"code": "CS201", "name": "数据结构", "credit": 4, "kind": "必修", "teacher": "周立群", "period": "周一 1-2 节", "weeks": 16,
     "slots": [(0, "1-2 节"), (2, "3-4 节")]},
    {"code": "CS203", "name": "计算机组成原理", "credit": 4, "kind": "必修", "teacher": "何建平", "period": "周二 3-4 节", "weeks": 16,
     "slots": [(1, "3-4 节"), (3, "1-2 节")]},
    {"code": "MA204", "name": "概率论与数理统计", "credit": 3, "kind": "必修", "teacher": "宋雅琴", "period": "周三 1-2 节", "weeks": 16,
     "slots": [(2, "1-2 节"), (4, "3-4 节")]},
    {"code": "EN203", "name": "大学英语 III", "credit": 2, "kind": "必修", "teacher": "Linda Chen", "period": "周四 5-6 节", "weeks": 16,
     "slots": [(3, "5-6 节"), (0, "7-8 节")]},
    {"code": "PE201", "name": "马克思主义基本原理", "credit": 3, "kind": "必修", "teacher": "吴国强", "period": "周五 3-4 节", "weeks": 16,
     "slots": [(4, "3-4 节"), (1, "7-8 节")]},
    {"code": "CS215", "name": "Python Web 开发", "credit": 2, "kind": "选修", "teacher": "林澈", "period": "周三 7-8 节", "weeks": 12,
     "slots": [(2, "7-8 节"), (4, "1-2 节")]},
]

# 教师档案：学生端「我的老师」直接展示，教务端可覆盖（见 engine/curriculum.py）
TEACHERS = {
    "周立群": {"name": "周立群", "title": "副教授", "dept": "计算机学院", "office": "信息楼 A503",
               "email": "zhoulq@cs.univ.edu.cn", "phone": "138-0013-8001",
               "office_hour": "周二 14:00-16:00", "note": "数据结构课程负责人"},
    "何建平": {"name": "何建平", "title": "教授", "dept": "计算机学院", "office": "信息楼 A612",
               "email": "hejp@cs.univ.edu.cn", "phone": "138-0013-8002",
               "office_hour": "周三 15:00-17:00", "note": "硬件方向，带实验课"},
    "宋雅琴": {"name": "宋雅琴", "title": "副教授", "dept": "数学学院", "office": "理科楼 B208",
               "email": "songyq@math.univ.edu.cn", "phone": "138-0013-8003",
               "office_hour": "周四 10:00-12:00", "note": ""},
    "Linda Chen": {"name": "Linda Chen", "title": "讲师", "dept": "外国语学院", "office": "文科楼 C305",
                   "email": "linda.chen@fl.univ.edu.cn", "phone": "138-0013-8004",
                   "office_hour": "周四 13:00-15:00", "note": "英文授课，Office Hour 可用中文"},
    "吴国强": {"name": "吴国强", "title": "教授", "dept": "马克思主义学院", "office": "文科楼 C110",
               "email": "wugq@marx.univ.edu.cn", "phone": "138-0013-8005",
               "office_hour": "周五 14:00-16:00", "note": ""},
    "林澈": {"name": "林澈", "title": "讲师", "dept": "计算机学院", "office": "信息楼 A518",
             "email": "linc@cs.univ.edu.cn", "phone": "138-0013-8006",
             "office_hour": "周三 19:00-20:30（线上）", "note": "选修课，项目制考核"},
}

SESSIONS_HELD = 14          # 已上课次数（第 1-7 周，每周两次）
SESSIONS_TOTAL = 16
HOMEWORK_ASSIGNED = 6       # 已布置作业数
HOMEWORK_TOTAL = 8

# 学期基线：第 8 教学周 = 2026-10-19 那一周，往前推 7 周为第 1 周
WEEK1_MONDAY = date(2026, 8, 31)
SLOT_LABEL = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 学生在校的 5 个学期：前 4 个已出总评，最后一个是本学期（只有期中，口径不同，图上单独标注）
TERMS = [
    {"term": "2024-2025 秋", "label": "大一上", "kind": "final"},
    {"term": "2024-2025 春", "label": "大一下", "kind": "final"},
    {"term": "2025-2026 秋", "label": "大二上", "kind": "final"},
    {"term": "2025-2026 春", "label": "大二下", "kind": "final"},
    {"term": "2026-2027 秋", "label": "大三上", "kind": "ongoing"},
]

# 随堂测落在第 2/3/5/6 周，期中安排在第 7 周周六（都已发生，学生端可以直接回看）
QUIZ_WEEKS = [2, 3, 5, 6]
MIDTERM_WEEK = 7

# 作业模板：每门课 6 次，标题按章节推进，便于学生看懂"要交什么"
HOMEWORK_PLAN = {
    "CS201": ["第 1 章 绪论 · 复杂度分析习题", "第 2 章 线性表 · 顺序表与链表实现",
              "第 3 章 栈与队列 · 表达式求值", "第 4 章 串与数组 · KMP 实现",
              "第 5 章 树与二叉树 · 遍历与重建", "第 6 章 图 · 最短路与拓扑排序"],
    "CS203": ["第 1 章 计算机系统概论 · 习题 1.3-1.9", "第 2 章 数据表示 · 浮点数转换实验",
              "第 3 章 运算方法与运算器 · ALU 设计", "第 4 章 存储系统 · Cache 命中率计算",
              "第 5 章 指令系统 · 汇编片段分析", "第 6 章 中央处理器 · 单周期 CPU 数据通路"],
    "MA204": ["第 1 章 概率论基本概念 · 习题", "第 2 章 随机变量及其分布 · 计算题",
              "第 3 章 多维随机变量 · 联合分布", "第 4 章 数字特征 · 期望与方差",
              "第 5 章 大数定律与中心极限定理", "第 6 章 数理统计基础 · 参数估计"],
    "EN203": ["Unit 1 Reading Report", "Unit 2 Listening & Note-taking",
              "Unit 3 Argumentative Essay (500 words)", "Unit 4 Presentation Script",
              "Unit 5 Translation Practice", "Unit 6 Academic Summary"],
    "PE201": ["第一章 世界的物质性 · 思考题", "第二章 实践与认识 · 案例分析",
              "第三章 人类社会及其发展规律 · 小论文", "第四章 资本主义的本质 · 读书报告",
              "第五章 社会主义的发展 · 调研提纲", "第六章 共产主义 · 课程总结"],
    "CS215": ["环境搭建与第一个 Flask 路由", "模板渲染与表单处理",
              "数据库建模与 ORM 实践", "RESTful 接口设计", "用户认证与权限控制",
              "期末项目 · 需求文档与原型"],
}

# 每次作业的提交要求，学生端直接显示
HOMEWORK_BRIEF = {
    "CS201": "提交 .c/.cpp 源码 + 实验报告 PDF，需含时间复杂度分析和测试用例",
    "CS203": "提交手写推导扫描件或 LaTeX 排版 PDF，实验题需附截图",
    "MA204": "提交完整解题过程，仅写答案不计分",
    "EN203": "提交 Word/PDF，格式按 Unit 要求，逾期按 10%/天扣分",
    "PE201": "提交 PDF，须注明引用来源，字数不少于 800 字",
    "CS215": "提交 Git 仓库链接 + README，能本地跑通为及格线",
}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _gauss(rng: random.Random, mu: float, sigma: float) -> float:
    return rng.gauss(mu, sigma)


def _build_students() -> list[dict]:
    rng = random.Random(SEED)
    students: list[dict] = []
    used_names: set[str] = set()
    sid = 0
    for cls in CLASSES:
        for _ in range(40):
            sid += 1
            gender = "男" if rng.random() < 0.68 else "女"
            pool = GIVEN_M if gender == "男" else GIVEN_F
            while True:
                name = rng.choice(SURNAMES) + rng.choice(pool)
                if name not in used_names:
                    used_names.add(name)
                    break
            ability = _clamp(_gauss(rng, 74, 11), 38, 97)
            diligence = _clamp(_gauss(rng, 0.70, 0.17), 0.18, 1.0)
            # 少数学生会出现"能力不错但完全不投入"的组合，这是预警真正要抓的
            if rng.random() < 0.05:
                ability = _clamp(ability + 10, 38, 97)
                diligence = _clamp(diligence - 0.35, 0.08, 0.6)

            students.append({
                "id": f"2024{sid:04d}",
                "name": name,
                "gender": gender,
                "class_name": cls,
                "major": "计算机科学与技术",
                "grade": "2024级",
                "enroll_year": 2024,
                "advisor": "陈静" if cls.endswith(("01", "02", "03")) else "刘畅",
                "ability": round(ability, 2),
                "diligence": round(diligence, 2),
                "_rng": rng,
            })
    return students


def _semester_history(rng: random.Random, cur_avg: float) -> dict:
    """上学期（2025-2026 春）的总评成绩。

    关键点：它**锚在本学期期中之上**，而不是另起一套随机数。
    学期总评含平时分（作业、出勤、课堂表现），通常比期中高几分，
    所以这里加一个 +2.6 的偏移和小幅浮动即可。

    早先的写法是"GPA 和期中各自独立生成、只在期望意义下一致"，
    结果出现了"上学期 95 分、本学期期中 74.7 分"这种同一个人身上的断崖 ——
    曲线一画出来就像数据错了。现在两者同源，画面上永远是连贯的。
    """
    avg = round(_clamp(cur_avg + _gauss(rng, 2.6, 3.8), 40.0, 95.0), 1)
    gpa = _gpa_of_avg(avg)
    failed = 0
    if gpa < 1.6:
        failed = rng.choice([9, 12, 15, 18])
    elif gpa < 2.2:
        failed = rng.choice([3, 4, 6])
    elif gpa < 2.8 and rng.random() < 0.25:
        failed = rng.choice([2, 3])
    return {
        "term": "2025-2026 春",
        "avg": avg,
        "gpa": round(gpa, 2),
        "failed_credits": failed,
        "credits_earned": 24 + rng.choice([0, 0, 0, 2, 4]),
        "credits_plan": 26,
    }


def _avg_of_gpa(gpa: float) -> float:
    """把 GPA 折算成同量纲的百分制均分。

    这个映射不是随便拍的：生成 GPA 时用的是 base = 0.45*能力 + 0.55*投入，
    生成期中分数用的是 46 + base*52，两式联立就得到下面的线性关系。
    有了它，"上学期 GPA" 和 "本学期期中均分" 才能画在同一条折线上。

    GPA 3.3 以上把斜率压平：满绩再往上加 0.7 也只多 6.5 分，
    否则 4.0 会被折算成 99.6 这种明显不真实的均分。
    """
    if gpa <= 3.3:
        avg = 46 + (gpa - 0.6) / 3.3 * 52
    else:
        avg = 88.5 + (gpa - 3.3) / 0.7 * 6.5
    return round(max(38.0, min(95.0, avg)), 1)


def _gpa_of_avg(avg: float) -> float:
    """上面那个映射的反函数：均分改了，GPA 跟着改，两张图不会自相矛盾。"""
    if avg <= 88.5:
        gpa = 0.6 + (avg - 46) / 52 * 3.3
    else:
        gpa = 3.3 + (avg - 88.5) / 6.5 * 0.7
    return round(_clamp(gpa, 0.6, 4.0), 2)


def _failed_of_gpa(rng: random.Random, gpa: float) -> int:
    """单个学期的不及格学分，量级和 history.failed_credits 保持一致。"""
    if gpa < 1.6:
        return rng.choice([6, 9, 12])
    if gpa < 2.2:
        return rng.choice([2, 3, 4])
    if gpa < 2.7 and rng.random() < 0.3:
        return rng.choice([1, 2])
    return 0


def _grade_history(
    rng: random.Random, history: dict, current_avg: float, credits_now: int
) -> list[dict]:
    """逐学期的成绩走势。

    大二下那一格用已经生成好的 history.gpa 钉住（风险分的历史因子就是按它算的），
    前三个学期则以它为锚点、按"个人成长形状"上下浮动：

    - up   一路上升（大一最吃力，后来开窍）
    - down 一路下滑（大一开始就顶不住，越读越差）
    - hump 大一下到大二上最好，之后走低（最典型的一种）
    - flat 四平八稳

    用"形状 + 幅度"而不是"每学期累加一个漂移"，是为了让曲线有界：
    否则满绩的学生往前倒推三个学期会被夹到 4.0，画出来是三个一模一样的点。
    """
    a3 = history.get("avg") or _avg_of_gpa(history["gpa"])
    shape = rng.choices(["up", "down", "hump", "flat"], weights=[34, 32, 19, 15])[0]
    amp = min(16.0, abs(_gauss(rng, 7.0, 4.2)))

    # 相对大二下（i=3）的偏移量，i=3 处恒为 0
    offsets = []
    for i in range(4):
        if shape == "up":
            off = -amp * (3 - i) / 3
        elif shape == "down":
            off = amp * (3 - i) / 3
        elif shape == "hump":
            off = -amp * ((((i - 1.3) / 2.8) ** 2) - (((3 - 1.3) / 2.8) ** 2)) * 1.6
        else:
            off = 0.0
        offsets.append(off)

    rows: list[dict] = []
    for i, t in enumerate(TERMS):
        if t["kind"] == "ongoing":
            rows.append({
                "term": t["term"],
                "label": t["label"],
                "status": "ongoing",
                "avg": round(current_avg, 1),
                "gpa": None,
                "rank": None,
                "rank_total": None,
                "credits": credits_now,
                "failed": None,
                "cohort_avg": None,
                "cohort_gpa": None,
                "note": "期中成绩·学期未结束",
            })
            continue
        avg = round(_clamp(a3 + offsets[i] + _gauss(rng, 0, 2.0), 40.0, 95.0), 1) if i < 3 else round(a3, 1)
        gpa = _gpa_of_avg(avg)
        rows.append({
            "term": t["term"],
            "label": t["label"],
            "status": "final",
            "avg": avg,
            "gpa": gpa,
            "rank": None,
            "rank_total": None,
            "credits": history["credits_earned"] if i == 3 else 24 + rng.choice([0, 0, 2, 4]),
            "failed": history["failed_credits"] if i == 3 else _failed_of_gpa(rng, gpa),
            "cohort_avg": None,
            "cohort_gpa": None,
            "note": "",
        })
    return rows


def _assessments(
    rng: random.Random, course: dict, midterm: int
) -> tuple[list[dict], list[int]]:
    """本学期的成绩序列：4 次随堂测 + 期中，学生能看到自己是越考越好还是越考越差。

    期中成绩是权威值（风险引擎在用它），所以从期中往前倒推随堂测，
    保证"图上最后一点"和"课程明细里的期中"永远是同一个数。
    """
    slots = course.get("slots") or [(0, "1-2 节")]
    weekday = slots[0][0]
    drift = _gauss(rng, 0.0, 2.1)          # 正：越考越好；负：一次不如一次
    scores = [0.0] * len(QUIZ_WEEKS)
    cur = float(midterm)
    for i in reversed(range(len(QUIZ_WEEKS))):
        cur = cur - drift + _gauss(rng, 0, 2.6)
        scores[i] = round(_clamp(cur, 8, 100))

    rows: list[dict] = []
    for i, wk in enumerate(QUIZ_WEEKS):
        day = WEEK1_MONDAY + timedelta(weeks=wk - 1, days=weekday)
        rows.append({
            "label": f"随堂测 {i + 1}",
            "short": f"测{i + 1}",
            "date": day.isoformat(),
            "week": wk,
            "kind": "quiz",
            "score": scores[i],
        })
    day = WEEK1_MONDAY + timedelta(weeks=MIDTERM_WEEK - 1, days=5)
    rows.append({
        "label": "期中考试",
        "short": "期中",
        "date": day.isoformat(),
        "week": MIDTERM_WEEK,
        "kind": "exam",
        "score": midterm,
    })
    return rows, [int(s) for s in scores]


def _attendance_detail(rng: random.Random, diligence: float, course: dict) -> list[dict]:
    """把这门课已上的每一节课落到具体日期上，学生端据此看到"哪天旷了"。

    第 1-7 周每周两节，共 14 节，全部发生在今天之前，和 SESSIONS_HELD 对齐。
    """
    slots = course.get("slots") or [(0, "1-2 节"), (0, "3-4 节")]
    p_abs = _clamp((1 - diligence) * 0.34, 0.0, 0.55)
    rows: list[dict] = []
    for week in range(1, 8):                      # 第 1..7 周
        monday = WEEK1_MONDAY + timedelta(weeks=week - 1)
        for weekday, period in slots:
            day = monday + timedelta(days=weekday)
            r = rng.random()
            if r < p_abs:
                status, note = "absent", "未到课，未请假"
            elif r < p_abs + 0.07:
                status, note = "late", f"迟到 {rng.choice([5, 8, 10, 12, 15, 20])} 分钟"
            else:
                status, note = "present", ""
            rows.append({
                "date": day.isoformat(),
                "weekday": SLOT_LABEL[weekday],
                "week": week,
                "period": period,
                "status": status,
                "note": note,
            })
    return rows


def _homework_detail(rng: random.Random, diligence: float, course: dict) -> list[dict]:
    """作业清单：交给什么、什么时候交、交没交，一次说清。"""
    titles = HOMEWORK_PLAN.get(course["code"], [f"第 {i} 次作业" for i in range(1, 7)])
    brief = HOMEWORK_BRIEF.get(course["code"], "按课程要求提交")
    p_miss = _clamp((1 - diligence) * 0.42, 0.0, 0.62)
    rows: list[dict] = []
    for i in range(HOMEWORK_ASSIGNED):
        week = 1 + i                       # 第 1..6 周布置
        assigned = WEEK1_MONDAY + timedelta(weeks=week - 1, days=4)   # 周五布置
        due = assigned + timedelta(days=10)                            # 下下周一截止
        r = rng.random()
        if r < p_miss:
            if rng.random() < 0.35:
                status, submitted_at = "late", (due + timedelta(days=rng.choice([1, 2, 3]))).isoformat() + " 22:40"
            else:
                status, submitted_at = "missing", ""
        else:
            status = "submitted"
            submitted_at = (due - timedelta(days=rng.choice([0, 1, 2, 3]))).isoformat() + f" {rng.choice(['19:20', '21:05', '22:48', '09:31'])}"
        rows.append({
            "id": f"{course['code']}-HW{i + 1}",
            "title": titles[i] if i < len(titles) else f"第 {i + 1} 次作业",
            "brief": brief,
            "assigned": assigned.isoformat(),
            "due": due.isoformat(),
            "status": status,
            "submitted_at": submitted_at,
        })
    return rows


def _course_state(rng: random.Random, ability: float, diligence: float, course: dict) -> dict:
    quality = 0.55 * (ability / 100) + 0.45 * diligence
    hard = 0.06 if course["code"] in {"CS201", "CS203", "MA204"} else 0.0
    midterm = _clamp(_gauss(rng, 46 + quality * 52 - hard * 100, 8.5), 16, 99)

    assessments, quizzes = _assessments(rng, course, round(midterm))
    attendance = _attendance_detail(rng, diligence, course)
    homework = _homework_detail(rng, diligence, course)

    # 汇总数字一律从明细派生，保证"学生看到的明细"和"预警算的分数"是同一份数据
    absent = sum(1 for a in attendance if a["status"] == "absent")
    late = sum(1 for a in attendance if a["status"] == "late")
    hw_submitted = sum(1 for h in homework if h["status"] in ("submitted", "late"))

    return {
        "code": course["code"],
        "name": course["name"],
        "credit": course["credit"],
        "kind": course["kind"],
        "teacher": course["teacher"],
        "period": course["period"],
        "midterm": round(midterm),
        "quizzes": quizzes,
        "assessments": assessments,
        "absent": absent,
        "late": late,
        "sessions_held": len(attendance),
        "hw_submitted": hw_submitted,
        "hw_assigned": len(homework),
        "attendance": attendance,
        "homework": homework,
    }


def _engagement(rng: random.Random, diligence: float) -> dict:
    weekly_logins = max(0, round(_gauss(rng, 3 + diligence * 9, 2.2)))
    video_rate = _clamp(_gauss(rng, 0.32 + diligence * 0.6, 0.13), 0.02, 1.0)
    library_visits = max(0, round(_gauss(rng, diligence * 10 - 1, 3)))
    last_active_days = max(0, round(_gauss(rng, 9 - diligence * 8, 3.5)))
    return {
        "weekly_logins": weekly_logins,
        "video_rate": round(video_rate, 2),
        "library_visits": library_visits,
        "days_since_active": last_active_days,
    }


def _attach_cohort(students: list[dict]) -> None:
    """按班级补排名与班级均分：同一学期、同一口径比，跨学期才谈得上"退步"。"""
    for ti in range(len(TERMS)):
        for cls in CLASSES:
            group = [s for s in students if s["class_name"] == cls]
            if not group:
                continue
            avgs = [s["grade_history"][ti]["avg"] for s in group]
            c_avg = round(sum(avgs) / len(avgs), 1)
            gpas = [s["grade_history"][ti]["gpa"] for s in group if s["grade_history"][ti]["gpa"] is not None]
            c_gpa = round(sum(gpas) / len(gpas), 2) if gpas else None
            for rank, s in enumerate(sorted(group, key=lambda x: -x["grade_history"][ti]["avg"]), start=1):
                cell = s["grade_history"][ti]
                cell["rank"] = rank
                cell["rank_total"] = len(group)
                cell["cohort_avg"] = c_avg
                cell["cohort_gpa"] = c_gpa


def build_dataset() -> dict:
    rng = random.Random(SEED)
    raw = _build_students()
    students: list[dict] = []
    for s in raw:
        sub = random.Random(SEED + int(s["id"][-4:]))
        # 先算本学期课程，再用期中均分反推上学期总评 —— 顺序不能反，
        # 否则两条线各自随机，会在个别学生身上走出"95 → 74"这种断崖。
        courses = [_course_state(sub, s["ability"], s["diligence"], c) for c in COURSES]
        for c in courses:
            c["teacher_profile"] = dict(TEACHERS.get(c["teacher"], {"name": c["teacher"]}))
        total_credit = sum(c["credit"] for c in courses)
        credits_now = total_credit
        cur_avg = sum(c["midterm"] * c["credit"] for c in courses) / total_credit
        history = _semester_history(sub, cur_avg)
        engagement = _engagement(sub, s["diligence"])
        # 已修学分：大三上应修 105（前四学期 + 本学期在修）
        plan_total = 165
        earned = 79 + history["credits_earned"] - history["failed_credits"]
        students.append({
            "id": s["id"],
            "name": s["name"],
            "gender": s["gender"],
            "class_name": s["class_name"],
            "major": s["major"],
            "grade": s["grade"],
            "advisor": s["advisor"],
            "phone_tail": f"{int(s['id'][-4:]) % 10000:04d}",
            "history": history,
            "grade_history": _grade_history(sub, history, cur_avg, credits_now),
            "courses": courses,
            "engagement": engagement,
            "credits": {
                "earned": max(0, earned),
                "in_progress": credits_now,
                "plan_total": plan_total,
            },
            "term": "2026-2027 秋",
            "week": 8,
        })
    _attach_cohort(students)
    return {
        "students": students,
        "courses": [{k: v for k, v in c.items() if k != "slots"} for c in COURSES],
        "teachers": TEACHERS,
        "classes": CLASSES,
        "term": "2026-2027 秋",
        "week": 8,
        "updated_at": TODAY.isoformat(),
    }


_DB: dict | None = None


def db() -> dict:
    global _DB
    if _DB is None:
        _DB = build_dataset()
    return _DB
