# -*- coding: utf-8 -*-
"""一次性脚本：生成 4 套学生端「历年真题」试卷（.docx）+ 4 门网课链接资源，
写入 data/teacher_resources/index.json，并把试卷正文抽进知识库。

跑完即可删除，仓库里只留产物。
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
# 这个脚本原先直接放在仓库根目录跑，后来收进了 tools/；data/ 始终在仓库根，
# 跟着脚本目录走会把试卷写进 tools/data/，应用读不到，等于白跑。
BASE = _HERE.parent if _HERE.name == "tools" else _HERE
sys.path.insert(0, str(BASE))

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, Cm

RES_DIR = BASE / "data" / "teacher_resources"
INDEX = RES_DIR / "index.json"


# ---------------------------------------------------------------- docx 排版
def _font(run, name="宋体", size=12, bold=False):
    run.font.name = name
    run.font.size = Pt(size)
    run.bold = bold
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)


def para(doc, text, *, size=12, bold=False, align="left", indent=0, space=4, font="宋体"):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space)
    p.paragraph_format.line_spacing = 1.4
    if indent:
        p.paragraph_format.first_line_indent = Cm(indent)
    p.alignment = {
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
    }[align]
    r = p.add_run(text)
    _font(r, font, size, bold)
    return p


def build_docx(sheet: dict, path: Path) -> None:
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = Cm(2.2)
    sec.bottom_margin = Cm(2.2)
    sec.left_margin = Cm(2.6)
    sec.right_margin = Cm(2.6)

    para(doc, sheet["school"], size=12, align="center", space=2)
    para(doc, sheet["title"], size=18, bold=True, align="center", space=6, font="黑体")
    para(doc, sheet["meta"], size=10.5, align="center", space=10)

    para(doc, "考试说明", size=12, bold=True, space=4, font="黑体")
    for line in sheet["rules"]:
        para(doc, line, size=10.5, indent=0.74, space=3)

    para(doc, "姓名：____________　学号：____________　班级：____________　成绩：__________",
         size=10.5, space=12)

    for section in sheet["sections"]:
        para(doc, section["head"], size=13, bold=True, space=6, font="黑体")
        if section.get("tip"):
            para(doc, section["tip"], size=10, space=4)
        for i, q in enumerate(section["items"], 1):
            para(doc, f"{i}. {q}", size=12, indent=0.74, space=5)

    doc.add_page_break()
    para(doc, f"{sheet['title']}　参考答案与评分标准", size=15, bold=True,
         align="center", space=12, font="黑体")
    para(doc, "（供教师阅卷参考；主观题答案要点齐全即给分，表述不同但逻辑正确同样给分）",
         size=10, space=10)
    for block in sheet["answers"]:
        para(doc, block["head"], size=12, bold=True, space=5, font="黑体")
        for line in block["lines"]:
            para(doc, line, size=11, indent=0.74, space=4)

    doc.save(path)


# ---------------------------------------------------------------- 试卷内容
CS_B = {
    "school": "计算机科学与技术学院",
    "title": "《数据结构》期末考试试卷（B 卷）",
    "meta": "2024—2025 学年第一学期　｜　闭卷　｜　满分 100 分　｜　考试时间 120 分钟",
    "rules": [
        "1. 答案一律写在答题纸对应位置，写在试卷上无效。",
        "2. 考试期间不得使用手机、智能手表等电子设备，不得相互借用文具。",
        "3. 算法题可用 C/C++ 或 Python 描述，关键步骤需加注释，只写思路不写代码酌情扣分。",
    ],
    "sections": [
        {
            "head": "一、单项选择题（每题 2 分，共 20 分）",
            "items": [
                "下列关于线性表的叙述中，正确的是（　）。\n"
                "A. 线性表只能采用顺序存储\n"
                "B. 采用链式存储时，结点之间的物理位置必须相邻\n"
                "C. 在顺序表中等概率插入一个元素，平均需要移动约 n/2 个元素\n"
                "D. 单链表不支持随机访问，因此无法在第 i 个位置插入元素",
                "具有 n 个结点的完全二叉树，其深度为（　）。（记号 [x] 表示不超过 x 的最大整数）\n"
                "A. [log2n]　　B. [log2n]+1　　C. [log2n]−1　　D. log2(n+1)",
                "若入栈序列为 1、2、3、4，则下列序列中不可能是出栈序列的是（　）。\n"
                "A. 1,2,3,4　　B. 4,3,2,1　　C. 3,1,2,4　　D. 2,3,4,1",
                "对静态查找表（建好后只查找、不插删），平均查找长度最小的是（　）。\n"
                "A. 顺序查找　　B. 折半查找　　C. 二叉排序树　　D. 分块查找",
                "具有 n 个顶点的无向连通图，其边数至少为（　）。\n"
                "A. n−1　　B. n　　C. n+1　　D. n(n−1)/2",
                "快速排序在最坏情况下的时间复杂度为（　）。\n"
                "A. O(n)　　B. O(nlog2n)　　C. O(n²)　　D. O(n³)",
                "一棵哈夫曼树中共有 n 个叶结点，则该树的非叶结点个数为（　）。\n"
                "A. n−1　　B. n　　C. n+1　　D. 2n−1",
                "图的深度优先遍历（DFS）在访问次序上类似于树的（　）。\n"
                "A. 先序遍历　　B. 中序遍历　　C. 后序遍历　　D. 层次遍历",
                "若某图的邻接矩阵为对称矩阵，则该图一定是（　）。\n"
                "A. 有向图　　B. 无向图　　C. 完全图　　D. 强连通图",
                "堆排序在平均情况下的空间复杂度为（　）。\n"
                "A. O(1)　　B. O(log2n)　　C. O(n)　　D. O(nlog2n)",
            ],
        },
        {
            "head": "二、填空题（每空 2 分，共 10 分）",
            "items": [
                "在长度为 n 的顺序表第 i 个位置（1 ≤ i ≤ n+1）插入一个元素，需要向后移动 ________ 个元素。",
                "一棵含有 100 个结点的完全二叉树，其叶结点个数为 ________。",
                "已知二叉树的前序遍历为 ABDECF、中序遍历为 DBEAFC，则其后序遍历为 ________。",
                "图的遍历主要有 ________ 和 ________ 两种基本方式。",
                "对 n 个元素进行冒泡排序，若初始序列已有序，则最好情况下的时间复杂度为 ________。",
            ],
        },
        {
            "head": "三、判断题（每题 2 分，共 10 分，正确的打 √，错误的打 ×）",
            "items": [
                "栈和队列都是操作受限的线性表。（　）",
                "二叉树中每个结点都有两棵子树。（　）",
                "折半查找要求线性表必须有序，并且采用顺序存储。（　）",
                "同一个有向无环图的拓扑排序结果一定唯一。（　）",
                "归并排序是稳定排序。（　）",
            ],
        },
        {
            "head": "四、简答与计算题（每题 10 分，共 40 分）",
            "items": [
                "给定权值集合 {5, 7, 2, 3, 6, 8}，请构造哈夫曼树，并计算其带权路径长度 WPL。",
                "已知关键字序列 {49, 38, 65, 97, 76, 13, 27}，请写出以第一个元素为枢轴、"
                "按「挖坑填数」法进行第一趟快速排序后的结果，并说明枢轴的最终位置。",
                "已知无向图 G 的顶点集为 {V1, V2, V3, V4, V5}，边集为 "
                "{(V1,V2,3), (V1,V3,8), (V2,V3,2), (V2,V4,5), (V3,V4,1), (V4,V5,4)}"
                "（括号内依次为顶点、权值）。请画出邻接表，并用 Dijkstra 算法求 V1 到其余各顶点的最短路径及其长度。",
                "请从存储密度、插入删除效率、随机访问能力三个方面，比较顺序存储结构与链式存储结构的优缺点，"
                "并各举一个适合的场景。",
            ],
        },
        {
            "head": "五、算法设计题（每题 10 分，共 20 分）",
            "items": [
                "设单链表结点的结构为 (data, next)，头指针为 head（带头结点）。"
                "请编写算法，统计链表中数据域值等于 x 的结点个数，并返回该个数。要求给出完整函数。",
                "设二叉树以二叉链表存储，结点结构为 (lchild, data, rchild)。"
                "请编写算法判断该二叉树是否为二叉排序树（BST），说明你所采用的方法与时间复杂度。",
            ],
        },
    ],
    "answers": [
        {
            "head": "一、单项选择题（每题 2 分）",
            "lines": [
                "1. C　（顺序表等概率插入平均移动 n/2 次；A、B、D 说法均不成立）",
                "2. B　（深度 = [log2n]+1）",
                "3. C　（3 出栈时栈内为 1、2，下一个只能是 2，不能是 1）",
                "4. B　（折半查找 ASL ≈ log2n，优于顺序查找与分块查找）",
                "5. A　（连通图至少 n−1 条边，即一棵生成树）",
                "6. C　（每次划分只减少一个元素，退化为冒泡的 n²）",
                "7. A　（哈夫曼树是严格二叉树，n0 = n2 + 1）",
                "8. A　（DFS 先访问根再深入子树，同先序遍历）",
                "9. B　（无向图的邻接矩阵关于主对角线对称）",
                "10. A　（堆排序原地进行，仅需常数级辅助空间）",
            ],
        },
        {
            "head": "二、填空题（每空 2 分）",
            "lines": [
                "1. n−i+1",
                "2. 50　（n0 = ⌈n/2⌉ = 50）",
                "3. DEBFCA",
                "4. 深度优先遍历（DFS）、广度优先遍历（BFS）　（两空各 2 分，顺序可互换）",
                "5. O(n)　（只比较 n−1 次，无交换）",
            ],
        },
        {
            "head": "三、判断题（每题 2 分）",
            "lines": ["1. √　　2. ×　　3. √　　4. ×　　5. √"],
        },
        {
            "head": "四、简答与计算题（每题 10 分）",
            "lines": [
                "1.（10 分）先合并 2+3=5，得 {5,5,6,7,8}；再合并 5+5=10，得 {6,7,8,10}；"
                "合并 6+7=13，得 {8,10,13}；合并 8+10=18，得 {13,18}；合并 13+18=31。\n"
                "　 树形正确得 6 分。WPL = 2×3 + 3×3 + 5×3 + 6×3 + 7×2 + 8×2 = 6+9+15+18+14+16 = 78。（4 分）",
                "2.（10 分）枢轴 49 取出。第一轮：右端 27 小于 49，填入位置 0，65 移到右端空位；"
                "第二轮：13 小于 49，填入位置 2，97 移到原 65 的位置；此后 76 不小于 49，"
                "指针相遇于位置 3，将 49 放入。\n"
                "　 第一趟结果：{27, 38, 13, 49, 76, 97, 65}，枢轴 49 落在第 4 个位置（下标 3），"
                "左侧均小于 49、右侧均大于 49。",
                "3.（10 分）邻接表按顶点顺序存储，每个顶点的边表按相邻顶点升序排列（4 分）。\n"
                "　 V1 到各点最短路径：V1→V2 = 3（经 V1-V2）；V1→V3 = 3+2 = 5（经 V2）；"
                "V1→V4 = 5+1 = 6（经 V2、V3）；V1→V5 = 6+4 = 10（经 V2、V3、V4）。（6 分）",
                "4.（10 分）存储密度：顺序存储为 1，链式存储小于 1（有指针开销），顺序存储更省空间；"
                "插入删除：链式存储只需改指针，O(1)（已定位时），顺序表平均移动 O(n)，链式更优；"
                "随机访问：顺序表 O(1)，链表 O(n)，顺序表更优。\n"
                "　 场景：查询多、插删少的成绩表用顺序存储；频繁插删的通讯录、任务队列用链式存储。"
                "（每方面 2 分 + 场景各 2 分）",
            ],
        },
        {
            "head": "五、算法设计题（每题 10 分）",
            "lines": [
                "1.（10 分）参考实现（C）：\n"
                "　 int countX(LinkNode *head, ElemType x) {\n"
                "　     int cnt = 0;\n"
                "　     LinkNode *p = head->next;\n"
                "　     while (p != NULL) { if (p->data == x) cnt++; p = p->next; }\n"
                "　     return cnt;\n"
                "　 }\n"
                "　 评分：遍历逻辑正确 6 分，边界（空表、头结点跳过）2 分，返回值与注释 2 分。"
                "写成 Python 并用 while 遍历同样给满分。",
                "2.（10 分）思路：二叉排序树的中序遍历序列严格递增，故做一次中序遍历，"
                "用变量记录前驱值，若出现当前值 ≤ 前驱值则不是 BST。\n"
                "　 参考实现（C，pre 为引用参数）：\n"
                "　 int isBST(BiTree T, int *pre) {\n"
                "　     if (T == NULL) return 1;\n"
                "　     if (!isBST(T->lchild, pre)) return 0;\n"
                "　     if (*pre != -1 && T->data <= *pre) return 0;\n"
                "　     *pre = T->data;\n"
                "　     return isBST(T->rchild, pre);\n"
                "　 }\n"
                "　 时间复杂度 O(n)，空间复杂度 O(h)（h 为树高）。"
                "只写「中序有序」结论不写实现给 5 分；用中序序列保存到数组再判断亦算正确。",
            ],
        },
    ],
}

CS_CO = {
    "school": "计算机科学与技术学院",
    "title": "《计算机组成原理》期末考试试卷（A 卷）",
    "meta": "2024—2025 学年第一学期　｜　闭卷　｜　满分 100 分　｜　考试时间 120 分钟",
    "rules": [
        "1. 计算题必须写出主要步骤，只写结果不给分。",
        "2. 数字一律注明进制，二进制、十六进制用下标或后缀标明。",
        "3. 考试期间不得使用具有存储功能的计算器。",
    ],
    "sections": [
        {
            "head": "一、单项选择题（每题 2 分，共 20 分）",
            "items": [
                "冯·诺依曼计算机的基本工作方式可以概括为（　）。\n"
                "A. 数据流驱动　　B. 存储程序、按地址顺序执行指令　　C. 并行流水　　D. 微程序控制",
                "某机字长 32 位，主存容量 128 MB，按字节编址，则主存地址线至少需要（　）根。\n"
                "A. 23　　B. 25　　C. 27　　D. 32",
                "8 位补码表示中，十进制数 −1 的机器码为（　）。\n"
                "A. 1000 0001　　B. 1111 1111　　C. 0111 1111　　D. 1000 0000",
                "下列 Cache 替换算法中，实际系统中基本无法实现的是（　）。\n"
                "A. FIFO　　B. LRU　　C. 随机替换　　D. 最优替换（OPT）",
                "某同步总线的时钟频率为 100 MHz，总线宽度为 32 位，每个时钟周期传送一次数据，"
                "则该总线带宽为（　）。\nA. 100 MB/s　　B. 400 MB/s　　C. 800 MB/s　　D. 3200 MB/s",
                "CPU 响应中断的时间是（　）。\n"
                "A. 一条指令执行结束后　　B. 取指周期结束后　　C. 任意时刻　　D. 一个时钟周期结束后",
                "与中断方式相比，DMA 方式的主要优点是（　）。\n"
                "A. 不需要 CPU 参与任何工作　　B. 数据传送不经过 CPU，以数据块为单位高速传送\n"
                "C. 可以实现优先级排队　　D. 传送速度由 CPU 主频决定",
                "IEEE 754 单精度浮点数中，尾数（含隐藏位）共占（　）位。\n"
                "A. 23　　B. 24　　C. 31　　D. 32",
                "微程序控制器中，微指令存放在（　）。\n"
                "A. 主存　　B. 控制存储器（CM）　　C. Cache　　D. 通用寄存器",
                "指令「MOV R1, (R2)+8」中，源操作数的寻址方式属于（　）。\n"
                "A. 立即寻址　　B. 寄存器间接寻址　　C. 基址寻址　　D. 相对寻址",
            ],
        },
        {
            "head": "二、填空题（每空 2 分，共 10 分）",
            "items": [
                "某机主存容量为 4 GB，按字（32 位）编址，则地址寄存器至少需要 ________ 位。",
                "Cache 与主存之间的地址映射方式主要有直接映射、________ 和组相联映射三种。",
                "在三级存储体系中，速度由快到慢依次为 ________、主存、辅存。",
                "一条指令的执行过程通常分为取指、________、执行三个基本阶段。",
                "某浮点数格式为：1 位符号位、8 位阶码（其中 1 位为阶符、7 位为阶码数值）、23 位尾数，"
                "则该格式能表示的最大阶码为 ________（用十进制表示）。",
            ],
        },
        {
            "head": "三、简答题（每题 8 分，共 32 分）",
            "items": [
                "简述 Cache 的作用与工作原理，并说明为什么引入 Cache 能提高访存速度。",
                "比较程序查询方式、程序中断方式和 DMA 方式在数据传送中的异同。",
                "什么是总线仲裁？集中式仲裁有哪几种常见方式？各自特点是什么？",
                "简述 RISC 与 CISC 在指令系统设计上的主要区别。",
            ],
        },
        {
            "head": "四、计算与设计题（每题 12 分，共 36 分）",
            "items": [
                "设 x = −0.1011，y = +0.1101，采用双符号位补码计算 x − y，写出运算过程，"
                "并判断结果是否溢出。",
                "某计算机主存容量 1 MB，Cache 容量 16 KB，每块 32 B，采用直接映射。"
                "求：(1) 主存地址格式各字段位数；(2) 若 CPU 访问地址 0x1A2B3，判断其映射到 Cache 的哪一块。",
                "设某机采用五级流水线（取指 IF、译码 ID、执行 EX、访存 MEM、写回 WB），"
                "每级耗时 1 个时钟周期。现有 100 条指令连续执行，"
                "求：(1) 不使用流水线时的总周期数；(2) 使用流水线时的总周期数；(3) 加速比。",
            ],
        },
    ],
    "answers": [
        {
            "head": "一、单项选择题（每题 2 分）",
            "lines": [
                "1. B　　2. C（128 MB = 2^27 B，按字节编址需 27 位）　　3. B　　4. D",
                "5. B（100 MHz × 4 B = 400 MB/s）　　6. A　　7. B　　8. B（23 位尾数 + 1 位隐藏位）",
                "9. B　　10. C（寄存器间接 + 偏移，属基址寻址形式）",
            ],
        },
        {
            "head": "二、填空题（每空 2 分）",
            "lines": [
                "1. 30　（4 GB / 4 B = 2^30 个字）",
                "2. 全相联映射",
                "3. Cache",
                "4. 译码（分析）",
                "5. +127（8 位阶码含 1 位符号位，数值位 7 位，最大 2^7−1 = 127）",
            ],
        },
        {
            "head": "三、简答题（每题 8 分）",
            "lines": [
                "1. 依据程序访问的局部性原理（时间局部性与空间局部性），把近期将被访问的指令与数据"
                "从主存复制到高速小容量的 Cache 中；CPU 访存时先查 Cache，命中则直接读取，"
                "未命中再访问主存并按替换算法调入。由于命中率通常可达 90% 以上，"
                "平均访存时间接近 Cache 的访问时间，故显著提高速度。（原理 4 分、过程 4 分）",
                "2. 相同点：都用于 CPU 与外设之间的数据传送，都需要相应的接口电路。\n"
                "　 不同点：查询方式由 CPU 反复读状态寄存器，CPU 全程等待，效率最低；"
                "中断方式由外设主动提出请求，CPU 在指令结束时响应，以字（字节）为单位传送，"
                "仍需 CPU 参与；DMA 方式由 DMA 控制器接管总线，以数据块为单位直接在主存与外设间传送，"
                "仅在传送开始与结束时打断 CPU，适合高速大批量数据。（每点 2 分，比较完整再加 2 分）",
                "3. 总线仲裁用于解决多个主设备同时请求总线时的使用权分配。"
                "集中式仲裁主要有：链式查询（结构简单、优先级固定、对故障敏感）、"
                "计数器定时查询（优先级可灵活改变、线数较少）、独立请求（响应最快、控制最复杂、线数最多）。"
                "（概念 2 分，三种方式各 2 分）",
                "4. RISC 指令数量少、格式规整、定长、寻址方式少，绝大多数指令单周期完成，"
                "大量使用寄存器，便于流水线实现，由编译器优化；"
                "CISC 指令数量多、功能强、变长、寻址方式多，多周期完成，微程序控制为主，"
                "汇编程序短小。二者在「把复杂性交给硬件还是软件」上取向不同。（每侧 4 分）",
            ],
        },
        {
            "head": "四、计算与设计题（每题 12 分）",
            "lines": [
                "1.（12 分）[x]补 = 11.0101，[−y]补 = 11.0011（双符号位）。\n"
                "　 11.0101 + 11.0011 = 110.1000，舍去最高位进位得 10.1000。\n"
                "　 双符号位为 10，表示结果发生负溢出（下溢），x−y 的真实值超出定点小数表示范围。"
                "（补码转换 4 分，加法过程 4 分，溢出判断 4 分）",
                "2.（12 分）(1) 块内地址 log2(32) = 5 位；Cache 行数 16 KB / 32 B = 512 = 2^9，"
                "故行号 9 位；主存地址 20 位（1 MB），标记位 = 20 − 9 − 5 = 6 位。\n"
                "　 地址格式：[标记 6 位][行号 9 位][块内地址 5 位]。\n"
                "　 (2) 主存块号 = 0x1A2B3 / 32 = 3349，行号 = 3349 mod 512 = 277；"
                "即映射到 Cache 第 277 行（从 0 开始编号），块内偏移 19。\n"
                "　 也可直接拆地址验证：0x1A2B3 = 0001 1010 0010 1011 0011，"
                "中间 9 位（行号）= 100010101 = 277。（每问 6 分）",
                "3.（12 分）(1) 非流水线：100 × 5 = 500 个周期。\n"
                "　 (2) 流水线：第一条指令 5 个周期，其后每条增加 1 个周期，"
                "总周期 = 5 + (100 − 1) = 104 个周期。\n"
                "　 (3) 加速比 = 500 / 104 ≈ 4.81。（每问 4 分）",
            ],
        },
    ],
}

PROB = {
    "school": "理学院 · 数学公共教学部",
    "title": "《概率论与数理统计》期末考试试卷（A 卷）",
    "meta": "2024—2025 学年第一学期　｜　闭卷　｜　满分 100 分　｜　考试时间 120 分钟",
    "rules": [
        "1. 计算结果保留四位小数，概率用小数或分数表示均可。",
        "2. 需要查表的题目，试卷末附标准正态分布表节选。",
        "3. 证明题须写明所用的定义、定理名称。",
    ],
    "sections": [
        {
            "head": "一、填空题（每题 3 分，共 15 分）",
            "items": [
                "设 P(A) = 0.4，P(B) = 0.5，P(A∪B) = 0.7，则 P(A|B) = ________。",
                "设随机变量 X ~ N(2, 9)，则 P(X < 2) = ________。",
                "设 X ~ B(10, 0.3)，则 E(X²) = ________。",
                "设 X、Y 相互独立，D(X) = 2，D(Y) = 3，则 D(2X − Y) = ________。",
                "设 X1, X2, …, Xn 是来自总体 N(μ, σ²) 的简单随机样本，则样本均值 X̄ 服从 ________ 分布。",
            ],
        },
        {
            "head": "二、单项选择题（每题 3 分，共 15 分）",
            "items": [
                "若事件 A 与 B 互不相容，且 P(A) > 0、P(B) > 0，则（　）。\n"
                "A. A 与 B 相互独立　　B. A 与 B 不独立　　C. P(A|B) = P(A)　　D. 以上都不对",
                "下列函数中可作为某随机变量概率密度函数的是（　）。\n"
                "A. f(x) = 2x, x ∈ (0,2)　　B. f(x) = e^(−x), x > 0\n"
                "C. f(x) = 1/(1+x²), x ∈ R　　D. f(x) = sinx, x ∈ (0, π)",
                "设 X ~ P(λ)（泊松分布），则 D(X) =（　）。\n"
                "A. λ　　B. λ²　　C. 1/λ　　D. 2λ",
                "设 X 与 Y 不相关，则（　）。\n"
                "A. X 与 Y 一定独立　　B. Cov(X, Y) = 0　　C. D(X+Y) = D(X) + D(Y) 一定不成立　　D. E(XY) ≠ E(X)E(Y)",
                "在假设检验中，显著性水平 α 表示（　）。\n"
                "A. 原假设为真时接受它的概率　　B. 原假设为真时拒绝它的概率\n"
                "C. 原假设为假时接受它的概率　　D. 原假设为假时拒绝它的概率",
            ],
        },
        {
            "head": "三、计算题（每题 10 分，共 60 分）",
            "items": [
                "袋中有 5 个白球、3 个黑球，不放回地依次取出 3 个球。求：(1) 第三个球为白球的概率；"
                "(2) 若已知第三个球为白球，求前两个球均为黑球的概率。",
                "设连续型随机变量 X 的密度函数为 f(x) = ax, 0 < x < 2；0, 其他。"
                "求：(1) 常数 a；(2) X 的分布函数 F(x)；(3) P(0.5 < X < 1.5)。",
                "设二维随机变量 (X, Y) 的联合分布列为：P(X=0,Y=0)=0.1，P(X=0,Y=1)=0.2，"
                "P(X=1,Y=0)=0.3，P(X=1,Y=1)=0.4。求：(1) X 与 Y 的边缘分布列；"
                "(2) 判断 X 与 Y 是否独立；(3) 求 Cov(X, Y)。",
                "某元件寿命 X（单位：千小时）服从指数分布，平均寿命为 4 千小时。"
                "求：(1) X 的密度函数；(2) 该元件能正常工作 5 千小时以上的概率；"
                "(3) 已使用 2 千小时的元件还能再用 3 千小时以上的概率。",
                "设总体 X ~ U(0, θ)，θ > 0 未知，X1, …, Xn 为其样本。"
                "求 θ 的矩估计量与最大似然估计量。",
                "某车间用一台包装机包装食盐，额定标准每袋净重 500 g。"
                "随机抽取 9 袋，测得样本均值 ̄x = 498 g，样本标准差 s = 3.6 g。"
                "设袋重服从正态分布，取 α = 0.05，检验包装机工作是否正常。"
                "（t_{0.025}(8) = 2.306）",
            ],
        },
        {
            "head": "四、证明题（10 分）",
            "items": [
                "设 X 为连续型随机变量，其密度函数 f(x) 关于 x = 0 对称，即 f(−x) = f(x)。"
                "证明：E(X) = 0（假定 E|X| < ∞）。",
            ],
        },
    ],
    "answers": [
        {
            "head": "一、填空题（每题 3 分）",
            "lines": [
                "1. 0.4　（P(A∩B) = 0.4+0.5−0.7 = 0.2，P(A|B) = 0.2/0.5 = 0.4）",
                "2. 0.5　（正态分布关于均值对称）",
                "3. 11.1　（E(X) = np = 3，D(X) = np(1−p) = 2.1，"
                "E(X²) = D(X) + [E(X)]² = 2.1 + 9 = 11.1）",
                "4. 11　（D(2X−Y) = 4×2 + 3 = 11）",
                "5. N(μ, σ²/n)",
            ],
        },
        {
            "head": "二、单项选择题（每题 3 分）",
            "lines": ["1. B　　2. B　　3. A　　4. B　　5. B"],
        },
        {
            "head": "三、计算题（每题 10 分）",
            "lines": [
                "1.（10 分）(1) 由对称性，每个位置抽到白球的概率相同，P = 5/8。（5 分）\n"
                "　 (2) P(前两黑 | 第三白) = P(前两黑且第三白) / P(第三白) "
                "= (3/8 × 2/7 × 5/6) / (5/8) = (5/56) / (5/8) = 1/7 ≈ 0.1429。（5 分）",
                "2.（10 分）(1) ∫₀² ax dx = 2a = 1 ⇒ a = 1/2。（3 分）\n"
                "　 (2) x ≤ 0 时 F = 0；0 < x < 2 时 F(x) = x²/4；x ≥ 2 时 F = 1。（4 分）\n"
                "　 (3) P(0.5 < X < 1.5) = F(1.5) − F(0.5) = 0.5625 − 0.0625 = 0.5。（3 分）",
                "3.（10 分）(1) X 的分布列：P(X=0)=0.3，P(X=1)=0.7；Y 的分布列：P(Y=0)=0.4，P(Y=1)=0.6。（4 分）\n"
                "　 (2) P(X=0,Y=0)=0.1，而 P(X=0)P(Y=0)=0.3×0.4=0.12，二者不等，故 X 与 Y 不独立。（3 分）\n"
                "　 (3) E(X)=0.7，E(Y)=0.6，E(XY)=P(X=1,Y=1)=0.4，"
                "Cov(X,Y) = 0.4 − 0.42 = −0.02。（3 分）",
                "4.（10 分）(1) E(X)=4 ⇒ λ=1/4，f(x) = (1/4)e^(−x/4), x > 0。（4 分）\n"
                "　 (2) P(X>5) = e^(−5/4) ≈ 0.2865。（3 分）\n"
                "　 (3) 指数分布无记忆性，P(X>5 | X>2) = P(X>3) = e^(−3/4) ≈ 0.4724。（3 分）",
                "5.（10 分）矩估计：E(X) = θ/2，令 θ/2 = X̄ ⇒ θ̂ = 2X̄。（5 分）\n"
                "　 最大似然：L(θ) = 1/θ^n（0 < xi < θ），要使 L 最大需 θ 尽量小，"
                "约束 θ ≥ max xi，故 θ̂_L = max{X1, …, Xn}。（5 分）",
                "6.（10 分）H0: μ = 500，H1: μ ≠ 500。检验统计量 t = (x̄ − μ0)/(s/√n) "
                "= (498−500)/(3.6/3) = −1.667。\n"
                "　 |t| = 1.667 < t_{0.025}(8) = 2.306，故不拒绝 H0，"
                "没有充分证据认为包装机工作不正常（差异可能由抽样误差造成）。（假设 3 分、统计量 4 分、结论 3 分）",
            ],
        },
        {
            "head": "四、证明题（10 分）",
            "lines": [
                "证明：E(X) = ∫_{−∞}^{+∞} x f(x) dx。将积分拆为 (−∞,0) 与 (0,+∞) 两段。\n"
                "在 (−∞,0) 段令 t = −x，则 ∫_{−∞}^{0} x f(x) dx = ∫_{0}^{+∞} (−t) f(−t) dt "
                "= −∫_{0}^{+∞} t f(t) dt（用到 f(−t) = f(t)）。\n"
                "两段相加得 E(X) = −∫_{0}^{+∞} t f(t) dt + ∫_{0}^{+∞} x f(x) dx = 0。\n"
                "又因 E|X| < ∞，上述积分绝对收敛，可逐段积分，故 E(X) = 0 成立。",
            ],
        },
    ],
}

WEB = {
    "school": "计算机科学与技术学院",
    "title": "《Python Web 开发》期末考试试卷（A 卷）",
    "meta": "2024—2025 学年第一学期　｜　闭卷　｜　满分 100 分　｜　考试时间 120 分钟",
    "rules": [
        "1. 编程题要求代码可运行，缩进错误按语法错误扣分。",
        "2. 允许使用 Python 标准库；框架 API 只需写出核心方法名，不必写出完整导入。",
        "3. 简答题按要点给分，只写名词不作解释不给分。",
    ],
    "sections": [
        {
            "head": "一、单项选择题（每题 2 分，共 20 分）",
            "items": [
                "下列不属于 HTTP 请求方法的是（　）。\nA. GET　　B. POST　　C. FETCH　　D. DELETE",
                "HTTP 状态码 404 表示（　）。\nA. 服务器内部错误　　B. 资源未找到　　C. 未授权　　D. 请求过多",
                "在 Flask 中，把视图函数绑定到 URL 的装饰器是（　）。\n"
                "A. @app.route　　B. @app.url　　C. @app.view　　D. @app.get",
                "Django 中负责处理 URL 与视图映射的文件通常是（　）。\n"
                "A. settings.py　　B. models.py　　C. urls.py　　D. admin.py",
                "下列哪一项符合 RESTful 设计规范（　）。\n"
                "A. GET /getUserById?id=1　　B. POST /deleteUser\n"
                "C. GET /users/1　　D. GET /user/delete/1",
                "Django ORM 中查询所有年龄大于 18 的用户，正确写法是（　）。\n"
                "A. User.objects.filter(age__gt=18)　　B. User.objects.filter(age>18)\n"
                "C. User.query(age__gt=18)　　D. User.objects.get(age>18)",
                "关于 Cookie 与 Session 的说法，正确的是（　）。\n"
                "A. Session 数据保存在客户端　　B. Cookie 数据保存在服务端\n"
                "C. Session 依赖 Cookie（或 URL 重写）传递会话标识　　D. 两者都不能用于登录状态保持",
                "Python 中用于处理 JSON 序列化的标准库是（　）。\nA. pickle　　B. json　　C. csv　　D. xml",
                "WSGI 的作用是（　）。\n"
                "A. 定义 Web 服务器与 Python Web 应用之间的接口规范\n"
                "B. 负责数据库连接池管理\nC. 提供前端模板渲染\nD. 实现 HTTP 缓存",
                "下列哪种做法最可能导致 SQL 注入（　）。\n"
                "A. 使用 ORM 参数化查询　　B. 用 f-string 拼接 SQL 并执行\n"
                "C. 使用预编译语句　　D. 对输入做白名单校验",
            ],
        },
        {
            "head": "二、填空题（每空 2 分，共 10 分）",
            "items": [
                "HTTP 协议默认端口是 ________，HTTPS 默认端口是 ________。",
                "Django 项目的配置文件名为 ________。",
                "在 Flask 中，获取 POST 请求 JSON 体的常用写法是 request.________。",
                "数据库事务的四个特性简称 ________。",
            ],
        },
        {
            "head": "三、简答题（每题 8 分，共 32 分）",
            "items": [
                "简述 MVC 与 MTV 两种架构模式的对应关系，并说明 Django 采用哪一种。",
                "解释什么是跨域（CORS），说明浏览器为什么会阻止跨域请求，以及服务端常用的解决方式。",
                "简述 JWT 的组成结构，并说明它相比传统 Session 的优缺点。",
                "什么是数据库索引？说明 B+ 树索引适合与不适合的场景各一个。",
            ],
        },
        {
            "head": "四、编程题（共 38 分）",
            "items": [
                "（18 分）使用 Flask 实现一个简单的待办事项接口：\n"
                "　 (1) GET /todos 返回全部事项的 JSON 列表；\n"
                "　 (2) POST /todos 接收 JSON {\"title\": \"...\"}，创建事项并返回 201 与新事项；\n"
                "　 (3) DELETE /todos/<int:tid> 删除指定事项，不存在时返回 404。\n"
                "　 要求：使用内存列表存储数据，正确处理请求体解析与错误返回。",
                "（20 分）已知 Django 模型如下：\n"
                "　 class Student(models.Model):\n"
                "　     name = models.CharField(max_length=32)\n"
                "　     grade = models.IntegerField()\n"
                "　     score = models.FloatField()\n"
                "　 请完成：\n"
                "　 (1) 查询 grade 为 2024 且 score 大于 60 的学生，按 score 降序返回前 10 条；\n"
                "　 (2) 统计每个年级的平均分，返回 [(grade, avg_score), ...]；\n"
                "　 (3) 用一次查询把所有 score 低于 60 的学生的 score 置为 0（不得逐条保存）。",
            ],
        },
    ],
    "answers": [
        {
            "head": "一、单项选择题（每题 2 分）",
            "lines": [
                "1. C　　2. B　　3. A　　4. C　　5. C",
                "6. A　　7. C　　8. B　　9. A　　10. B",
            ],
        },
        {
            "head": "二、填空题（每空 2 分）",
            "lines": [
                "1. 80、443",
                "2. settings.py",
                "3. get_json()（写成 request.json 亦正确）",
                "4. ACID（原子性、一致性、隔离性、持久性）",
            ],
        },
        {
            "head": "三、简答题（每题 8 分）",
            "lines": [
                "1. MVC 中的 Model 对应 MTV 的 Model，View 对应 Template，Controller 对应 View（视图函数）。"
                "Django 采用 MTV 模式：Model 负责数据、Template 负责展示、View 负责业务逻辑与请求分发。"
                "（对应关系 5 分，指出 Django 为 MTV 3 分）",
                "2. 跨域指浏览器中页面的源（协议+域名+端口）与请求目标不一致。"
                "浏览器出于同源策略限制，防止恶意站点读取用户在其他站点的数据。"
                "服务端解决方式：设置响应头 Access-Control-Allow-Origin、Allow-Methods、Allow-Headers，"
                "并正确处理预检请求 OPTIONS；也可用同源反向代理规避。（现象 3 分、原因 2 分、方案 3 分）",
                "3. JWT 由三部分组成：Header（算法与类型）、Payload（声明，如用户 id、过期时间）、"
                "Signature（对前两部分用密钥签名），以点号连接。\n"
                "　 优点：无状态、服务端不必存会话、便于水平扩展与跨域；"
                "缺点：签发后无法立即失效（需配合黑名单）、Payload 仅 Base64 编码不可放敏感信息、体积较大。"
                "（结构 4 分、优缺点各 2 分）",
                "4. 索引是对表中一列或多列建立的有序数据结构，用于加速检索。"
                "B+ 树索引适合等值查询与范围查询、排序、前缀匹配，如按学号查询、按分数区间统计；"
                "不适合在区分度极低的列（如性别）上建立，也不适合频繁大量写入的列，因为维护索引有额外开销。"
                "（定义 3 分、适合 2 分、不适合 3 分）",
            ],
        },
        {
            "head": "四、编程题（共 38 分）",
            "lines": [
                "1.（18 分）参考实现：\n"
                "　 from flask import Flask, request, jsonify\n"
                "　 app = Flask(__name__)\n"
                "　 todos, next_id = [], 1\n\n"
                "　 @app.get('/todos')\n"
                "　 def list_todos():\n"
                "　     return jsonify(todos)\n\n"
                "　 @app.post('/todos')\n"
                "　 def add_todo():\n"
                "　     global next_id\n"
                "　     data = request.get_json(silent=True) or {}\n"
                "　     title = (data.get('title') or '').strip()\n"
                "　     if not title:\n"
                "　         return jsonify({'error': 'title required'}), 400\n"
                "　     item = {'id': next_id, 'title': title, 'done': False}\n"
                "　     next_id += 1\n"
                "　     todos.append(item)\n"
                "　     return jsonify(item), 201\n\n"
                "　 @app.delete('/todos/<int:tid>')\n"
                "　 def del_todo(tid):\n"
                "　     global todos\n"
                "　     for i, t in enumerate(todos):\n"
                "　         if t['id'] == tid:\n"
                "　             todos.pop(i)\n"
                "　             return jsonify({'ok': True})\n"
                "　     return jsonify({'error': 'not found'}), 404\n\n"
                "　 评分：三个接口各 5 分，参数校验与状态码 3 分。"
                "不用 jsonify 而用 Response(json.dumps(...), mimetype='application/json') 同样给分。",
                "2.（20 分）(1) 6 分：\n"
                "　 Student.objects.filter(grade=2024, score__gt=60).order_by('-score')[:10]\n"
                "　 (2) 7 分：\n"
                "　 from django.db.models import Avg\n"
                "　 Student.objects.values('grade').annotate(avg=Avg('score')).values_list('grade', 'avg')\n"
                "　 (3) 7 分：\n"
                "　 Student.objects.filter(score__lt=60).update(score=0)\n"
                "　 说明：第 (3) 问若用 for 循环逐条 save() 只给 2 分，因为未满足「一次查询」要求；"
                "用 F() 表达式或 update() 均算正确。",
            ],
        },
    ],
}

SHEETS = [
    ("2024秋-数据结构-期末考试试卷B卷.docx", "数据结构", "周立群", CS_B, "计科2402 期末复习用，含参考答案"),
    ("2024秋-计算机组成原理-期末考试试卷A卷.docx", "计算机组成原理", "何建平", CS_CO, "含计算题与流水线题，参考答案附后"),
    ("2024秋-概率论与数理统计-期末考试试卷A卷.docx", "概率论与数理统计", "宋雅琴", PROB, "含假设检验与证明题"),
    ("2024秋-Python Web开发-期末考试试卷A卷.docx", "Python Web 开发", "林澈", WEB, "含 Flask 接口与 Django ORM 编程题"),
]

ONLINE = [
    {
        "filename": "数据结构（浙江大学 · 陈越）国家精品在线开放课程",
        "course": "数据结构",
        "teacher": "周立群",
        "note": "对应 CS201，1–12 讲全部免费，第 6–8 讲图论可直接对照期末大题",
        "url": "https://www.icourse163.org/course/ZJU-93001",
    },
    {
        "filename": "计算机组成原理（上）（哈尔滨工业大学 · 刘宏伟）",
        "course": "计算机组成原理",
        "teacher": "何建平",
        "note": "对应 CS203，第 4 章存储器、第 5 章 I/O 是期末重点",
        "url": "https://www.icourse163.org/course/HIT-309001",
    },
    {
        "filename": "计算机操作系统（南京大学 · 蒋炎岩）",
        "course": "计算机操作系统",
        "teacher": "何建平",
        "note": "计算机专业核心课，下学期开课前可先看前 3 周",
        "url": "https://www.icourse163.org/course/NJU-1001571004",
    },
    {
        "filename": "计算机网络（哈尔滨工业大学 · 李全龙）",
        "course": "计算机网络",
        "teacher": "林澈",
        "note": "计算机专业核心课，配套协议分析实验，课外拓展",
        "url": "https://www.icourse163.org/course/HIT-154005",
    },
]


def main() -> None:
    RES_DIR.mkdir(parents=True, exist_ok=True)
    rows = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else []

    # 幂等：先清掉本脚本上次生成的条目与文件
    keep = [r for r in rows if not r.get("seed")]
    for r in rows:
        if r.get("seed"):
            p = RES_DIR / f"{r['id']}__{r['filename'].replace('/', '_').replace(chr(92), '_')}"
            if p.exists():
                p.unlink()
    rows = keep

    stamp = int(time.time() * 1000)
    made = []

    # 真题：生成 docx + 入知识库
    from engine import resource_ingest

    for i, (filename, course, teacher, sheet, note) in enumerate(SHEETS):
        rid = f"r{stamp + i}_{uuid.uuid4().hex[:8]}"
        path = RES_DIR / f"{rid}__{filename}"
        build_docx(sheet, path)
        row = {
            "id": rid,
            "kind": "exam",
            "filename": filename,
            "size": path.stat().st_size,
            "course": course,
            "class_name": "计科2402",
            "note": note,
            "teacher": teacher,
            "created_at": "2026-11-12 21:40",
            "seed": True,
        }
        row["kb"] = resource_ingest.ingest(row, path)
        rows.append(row)
        made.append((filename, path.stat().st_size, row["kb"]))

    # 网课：只登记外链，没有文件本体，不入知识库
    for j, it in enumerate(ONLINE):
        rid = f"r{stamp + 100 + j}_{uuid.uuid4().hex[:8]}"
        row = {
            "id": rid,
            "kind": "tutorial",
            "filename": it["filename"],
            "size": 0,
            "course": it["course"],
            "class_name": "",
            "note": it["note"],
            "teacher": it["teacher"],
            "created_at": "2026-11-12 21:40",
            "url": it["url"],
            "seed": True,
        }
        rows.append(row)
        made.append((it["filename"], 0, {"ok": True, "note": "外链课程"}))

    INDEX.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"共 {len(rows)} 条资源")
    for name, size, kb in made:
        print(f"  {name[:44]:<46} {size/1024:6.1f} KB  kb={kb.get('ok')} "
              f"{('sections=' + str(kb.get('sections'))) if kb.get('ok') else kb.get('note')}")


if __name__ == "__main__":
    main()
