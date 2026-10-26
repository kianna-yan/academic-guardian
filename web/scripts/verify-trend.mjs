/**
 * 成绩走势专项验收。
 *
 * 检查学生端「成绩走势 + 本学期各课测评」与辅导员端名单 sparkline / 抽屉走势图，
 * 并且真的去 hover、去切指标、去点行 —— 只截静态图看不出图有没有画上去。
 *
 * 用法：node scripts/verify-trend.mjs   （需要本机 Edge，服务跑在 8600）
 */
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = process.env.BASE_URL || "http://127.0.0.1:8600";
const OUT = process.env.OUT_DIR || "shots";
mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
function check(name, ok, extra = "") {
  results.push({ name, ok, extra });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  " + extra : ""}`);
}

const browser = await puppeteer.launch({
  executablePath: EXE,
  headless: true,
  args: ["--disable-gpu", "--no-sandbox", "--font-render-hinting=none"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 940 });

const errors = [];
page.on("console", (m) => {
  if (m.type() === "error") errors.push(`console: ${m.text()}`);
});
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("requestfailed", (r) => {
  const u = r.url();
  if (u.startsWith(BASE)) errors.push(`requestfailed: ${u} ${r.failure()?.errorText}`);
});

async function loginAs(role, account, password) {
  const res = await page.evaluate(
    async (body) => {
      const r = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      return { status: r.status, data: await r.json().catch(() => ({})) };
    },
    { role, account, password },
  );
  if (!res.data?.token) throw new Error(`登录失败 ${role}: ${JSON.stringify(res.data)}`);
  await page.evaluate((t) => localStorage.setItem("ag.token", t), res.data.token);
  return res.data.profile;
}

/** canvas 是否真的画了东西：抽样看像素里有没有非白点 */
async function canvasPainted(selectorOrHeading, byHeading = false) {
  return page.evaluate(
    (sel, isHeading) => {
      let c = null;
      if (isHeading) {
        const card = [...document.querySelectorAll(".card")].find((k) =>
          k.querySelector(".card-head h3")?.textContent.includes(sel),
        );
        c = card?.querySelector("canvas");
      } else {
        c = document.querySelector(sel);
      }
      if (!c || c.tagName !== "CANVAS") return { ok: false, reason: "no canvas" };
      const w = c.width;
      const h = c.height;
      if (!w || !h) return { ok: false, reason: "zero size" };
      const ctx = c.getContext("2d");
      const data = ctx.getImageData(0, 0, w, h).data;
      let ink = 0;
      for (let i = 0; i < data.length; i += 4 * 37) {
        if (data[i + 3] > 0 && data[i] + data[i + 1] + data[i + 2] < 720) ink++;
      }
      return { ok: ink > 20, reason: `ink=${ink} size=${w}x${h}` };
    },
    selectorOrHeading,
    byHeading,
  );
}

const DEMO = await (async () => {
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
  return page.evaluate(async () => (await fetch("/api/meta")).json());
})();

/* ==================== 学生端 ==================== */
await loginAs("student", DEMO.demo.student, "0000");
await page.goto(`${BASE}/student`, { waitUntil: "networkidle2" });
// 对话即首页：先点「我的学情档案」进入数据看板
await page.waitForSelector(".ch-go-dash", { timeout: 15000 });
await page.click(".ch-go-dash");
await page.waitForSelector(".gt", { timeout: 15000 });
await sleep(900);

const stu = await page.evaluate(() => {
  const cards = [...document.querySelectorAll(".card")];
  const head = [...document.querySelectorAll(".card-head h3")].map((h) => h.textContent.trim());
  const gt = document.querySelector(".gt");
  const canvas = gt?.querySelector("canvas");
  return {
    heads: head,
    hasGt: !!gt,
    summary: document.querySelector(".gt-sum")?.textContent.trim() || "",
    chip: document.querySelector(".gt-chip")?.textContent.replace(/\s+/g, " ").trim() || "",
    canvasBox: canvas ? { w: canvas.getBoundingClientRect().width, h: canvas.getBoundingClientRect().height } : null,
    chips: [...document.querySelectorAll(".ct-chip")].map((c) => c.textContent.replace(/\s+/g, " ").trim()),
    cardCount: cards.length,
  };
});
check("学生端出现「成绩走势」卡片", stu.heads.some((h) => h.includes("成绩走势")), stu.heads.join(" | "));
check("走势图 canvas 有尺寸", !!stu.canvasBox && stu.canvasBox.w > 200 && stu.canvasBox.h > 150, JSON.stringify(stu.canvasBox));
let painted = await canvasPainted(".gt canvas");
check("走势图真的画上了", painted.ok, painted.reason);
check("结论文案非空", stu.summary.includes("分"), stu.summary);
check("趋势标签非空", !!stu.chip, stu.chip);
check("课程走势标签 6 个", stu.chips.length === 6, stu.chips.join(" / "));
painted = await canvasPainted("本学期每门课的测评走势", true);
check("课程走势图真的画上了", painted.ok, painted.reason);

await page.screenshot({ path: `${OUT}/trend_student.png`, fullPage: true });

// 单独截课程走势这张卡：主内容区是内部滚动的，整页截图截不到它
await page.evaluate(() => {
  const card = [...document.querySelectorAll(".card")].find((c) =>
    c.querySelector(".card-head h3")?.textContent.includes("测评走势"),
  );
  if (card) {
    card.id = "ct-card";
    card.scrollIntoView({ block: "center" });
  }
});
await sleep(500);
// 2 倍像素密度单独截这张卡，方便人工复核线条细节
await page.setViewport({ width: 1440, height: 940, deviceScaleFactor: 2 });
await sleep(600);
const ctCard = await page.$("#ct-card");
if (ctCard) await ctCard.screenshot({ path: `${OUT}/trend_course.png` });
await page.setViewport({ width: 1440, height: 940, deviceScaleFactor: 1 });
await sleep(400);
await page.evaluate(() => window.scrollTo(0, 0));
await page.evaluate(() => document.querySelector(".gt")?.scrollIntoView({ block: "center" }));
await sleep(400);

// 切换指标：分数 → 班级排名
const tabSwitched = await page.evaluate(() => {
  const tabs = [...document.querySelectorAll(".gt-tab")];
  const t = tabs.find((x) => x.textContent.includes("班级排名"));
  if (!t) return false;
  t.click();
  return true;
});
await sleep(700);
check("切换到「班级排名」", tabSwitched);
const rankMode = await page.evaluate(() => {
  const on = document.querySelector(".gt-tab.on")?.textContent.trim();
  const canvas = document.querySelector(".gt canvas");
  return { on, box: canvas ? canvas.getBoundingClientRect().width : 0 };
});
check("排名模式已生效", rankMode.on === "班级排名" && rankMode.box > 200, JSON.stringify(rankMode));
painted = await canvasPainted(".gt canvas");
check("排名图重绘成功", painted.ok, painted.reason);
await page.screenshot({ path: `${OUT}/trend_student_rank.png`, fullPage: true });

// hover 出 tooltip
const chartBox = await page.evaluate(() => {
  const r = document.querySelector(".gt canvas").getBoundingClientRect();
  return { x: r.x, y: r.y, w: r.width, h: r.height };
});
await page.mouse.move(chartBox.x + chartBox.w * 0.45, chartBox.y + chartBox.h * 0.55);
await sleep(600);
const tip = await page.evaluate(() => {
  const el = [...document.querySelectorAll("div")].find(
    (d) => d.style?.position === "absolute" && /班级排名|均分/.test(d.textContent || "") && d.offsetParent,
  );
  return el ? el.innerText.replace(/\s+/g, " ").trim().slice(0, 90) : "";
});
check("hover 弹出明细 tooltip", !!tip, tip);
await page.screenshot({ path: `${OUT}/trend_student_tip.png` });

/* ==================== 辅导员端 ==================== */
await loginAs("counselor", "2024014589", "1111");
await page.goto(`${BASE}/counselor`, { waitUntil: "networkidle2" });
// 对话即首页：先点「预警名单 · 台账」进入看板
await page.waitForSelector(".ch-go-dash", { timeout: 15000 });
await page.click(".ch-go-dash");
await page.waitForSelector(".el-table__row", { timeout: 15000 });
await sleep(800);

const coun = await page.evaluate(() => {
  const rows = document.querySelectorAll(".el-table__row");
  const cells = document.querySelectorAll(".gt-cell");
  const sparks = document.querySelectorAll(".gt-cell svg.spark");
  const deltas = [...document.querySelectorAll(".gt-meta")].slice(0, 6).map((d) => d.textContent.replace(/\s+/g, " ").trim());
  const paths = [...document.querySelectorAll(".gt-cell svg.spark path")].filter((p) => (p.getAttribute("stroke") || "") !== "");
  // 迷你线不能是一根横线：抽查前 40 行里纵向有起伏的比例
  const varied = paths.slice(0, 80).filter((p) => {
    const ys = (p.getAttribute("d") || "").match(/[ML][\d.]+,([\d.]+)/g) || [];
    const vals = ys.map((s) => parseFloat(s.split(",")[1]));
    return Math.max(...vals) - Math.min(...vals) > 1.5;
  }).length;
  const docW = document.documentElement.scrollWidth;
  const viewW = document.documentElement.clientWidth;
  const wrap = document.querySelector(".table-wrap");
  return {
    rows: rows.length,
    cells: cells.length,
    sparks: sparks.length,
    deltas,
    varied,
    probed: Math.min(80, paths.length),
    overflowX: docW - viewW,
    tableScroll: wrap ? wrap.scrollWidth - wrap.clientWidth : 0,
  };
});
check("名单每行都有走势单元格", coun.cells === coun.rows && coun.rows > 200, `${coun.cells}/${coun.rows}`);
check("sparkline 全部渲染", coun.sparks === coun.rows, `${coun.sparks}/${coun.rows}`);
check("迷你线有实际起伏", coun.varied > coun.probed * 0.5, `${coun.varied}/${coun.probed}`);
check("名次文案可读", coun.deltas.every((d) => /第 \d+ 名/.test(d)), coun.deltas.join(" / "));
check("1440 宽下页面无横向溢出", coun.overflowX <= 0, `overflow=${coun.overflowX}, tableScroll=${coun.tableScroll}`);
await page.screenshot({ path: `${OUT}/trend_counselor.png`, fullPage: true });

// 抽屉里的完整走势图
await page.click(".el-table__row");
await page.waitForFunction(() => {
  const d = document.querySelector(".el-drawer");
  return d && d.getBoundingClientRect().width > 0;
});
await sleep(1200);
const drawer = await page.evaluate(() => {
  const d = document.querySelector(".el-drawer");
  // 小节标题里现在带「问 AI」按钮，取第一个文本节点才是纯标题
  const secs = [...d.querySelectorAll("h3.sec")].map((h) => h.firstChild.textContent.trim());
  const canvas = d.querySelector(".gt canvas");
  const minis = d.querySelectorAll(".mini-row").length;
  return {
    secs,
    hasCanvas: !!canvas,
    canvasW: canvas ? canvas.getBoundingClientRect().width : 0,
    minis,
    drawerOverflow: d.scrollWidth - d.clientWidth,
  };
});
check("抽屉里有「成绩走势」小节", drawer.secs.includes("成绩走势"), drawer.secs.join(" | "));
check("抽屉走势图已渲染", drawer.hasCanvas && drawer.canvasW > 300, `w=${drawer.canvasW}`);
check("抽屉课程明细行 6 条", drawer.minis === 6, String(drawer.minis));
check("抽屉内无横向溢出", drawer.drawerOverflow <= 1, String(drawer.drawerOverflow));
await page.screenshot({ path: `${OUT}/trend_drawer.png` });

// 抽屉内容比一屏高，滚到走势图那里再单独截一张
await page.evaluate(() => {
  const d = document.querySelector(".el-drawer__body");
  const sec = [...d.querySelectorAll("h3.sec")].find((h) => h.textContent.includes("成绩走势"));
  if (sec) sec.scrollIntoView({ block: "start" });
});
await sleep(600);
const drawerBody = await page.$(".el-drawer__body");
if (drawerBody) await drawerBody.screenshot({ path: `${OUT}/trend_drawer_chart.png` });

await page.evaluate(() => document.querySelector(".el-drawer__close-btn")?.click());
await sleep(400);

/* ==================== 1280 宽 ==================== */
await page.setViewport({ width: 1280, height: 900 });
await sleep(700);
const mid = await page.evaluate(() => {
  const docW = document.documentElement.scrollWidth;
  const wrap = document.querySelector(".table-wrap");
  const lastCol = document.querySelector(".el-table__row td:last-child");
  return {
    overflowX: docW - document.documentElement.clientWidth,
    tableScroll: wrap ? wrap.scrollWidth - wrap.clientWidth : 0,
    lastRight: lastCol ? Math.round(lastCol.getBoundingClientRect().right) : 0,
    viewW: document.documentElement.clientWidth,
  };
});
check("1280 宽下页面无横向溢出", mid.overflowX <= 0, JSON.stringify(mid));
await page.screenshot({ path: `${OUT}/trend_counselor_1280.png` });

/* ==================== 390 手机宽 ==================== */
await page.setViewport({ width: 390, height: 844, isMobile: true });
await sleep(900);
// 切移动仿真会整页重载，重载后回到对话首页：先确认首页形态，再按键进看板
const mobMode = await page.evaluate(() => ({
  chat: !!document.querySelector(".chat-home"),
  dash: !!document.querySelector(".dash-nav"),
}));
check("手机端进页面也是整页对话（或已在看板）", mobMode.chat || mobMode.dash, JSON.stringify(mobMode));
if (mobMode.chat) {
  await page.waitForSelector(".ch-go-dash", { timeout: 15000 });
  await page.click(".ch-go-dash");
  await page.waitForSelector(".dash-nav", { timeout: 15000 });
}
await sleep(900);
const mob = await page.evaluate(() => {
  const list = [...document.querySelectorAll(".m-row")];
  const withSpark = list.filter((r) => r.querySelector("svg.spark")).length;
  return {
    rows: list.length,
    withSpark,
    overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  };
});
check("手机端列表带迷你走势", mob.withSpark > 0 && mob.withSpark === mob.rows, `${mob.withSpark}/${mob.rows}`);
check("390 宽无横向溢出", mob.overflowX <= 0, `overflow=${mob.overflowX}`);
await page.screenshot({ path: `${OUT}/trend_mobile.png`, fullPage: false });

/* ==================== 学生端手机宽 ==================== */
await loginAs("student", DEMO.demo.student, "0000");
await page.goto(`${BASE}/student`, { waitUntil: "networkidle2" });
// 对话即首页：手机上同样先进看板再看走势
await page.waitForSelector(".ch-go-dash", { timeout: 15000 });
await page.click(".ch-go-dash");
await page.waitForSelector(".gt", { timeout: 15000 });
await sleep(900);
const stuM = await page.evaluate(() => ({
  overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  canvasW: document.querySelector(".gt canvas")?.getBoundingClientRect().width || 0,
}));
check("学生端 390 宽无横向溢出", stuM.overflowX <= 0, JSON.stringify(stuM));
await page.screenshot({ path: `${OUT}/trend_student_mobile.png`, fullPage: true });

check("无 console / pageerror", errors.length === 0, errors.slice(0, 4).join(" ;; "));

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} 通过`);
await browser.close();
if (failed.length) {
  console.log("失败项：");
  failed.forEach((f) => console.log(" -", f.name, f.extra));
  process.exit(1);
}
