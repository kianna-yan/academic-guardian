import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--disable-gpu", "--no-sandbox"] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 880 });
page.on("pageerror", (e) => console.log("PAGEERROR:", e.message));

async function login(role, account, password) {
  const r = await fetch(`${BASE}/api/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role, account, password }),
  });
  const j = await r.json();
  if (!j.ok) throw new Error(`login failed: ${JSON.stringify(j)}`);
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle2" });
  await page.evaluate((t) => { localStorage.clear(); localStorage.setItem("ag.token", t); }, j.token);
  const home = { student: "/student", counselor: "/counselor", parent: "/parent", teacher: "/teacher" }[role];
  await page.goto(`${BASE}${home}`, { waitUntil: "networkidle2" });
  await sleep(1800);
}

// === 1. 学生端"我的成长"子页滚动 ===
// 进 /student 默认是 chat 模式，跳 /student/tree 应该能滚动（.view 不再被 view-chat 锁）
await login("student", "20240067", "0000");
await page.goto(`${BASE}/student/tree`, { waitUntil: "networkidle2" });
await sleep(2000);
const treeScroll = await page.evaluate(() => {
  const v = document.querySelector(".view");
  if (!v) return { ok: false, reason: "no .view" };
  // 检查 .view 是否被 view-chat 锁住（overflow:hidden）
  const cs = getComputedStyle(v);
  const locked = cs.overflowY === "hidden";
  v.scrollTop = 60;
  return { ok: !locked && v.scrollTop === 60, locked, overflowY: cs.overflowY, scrollTop: v.scrollTop, scrollHeight: v.scrollHeight, clientHeight: v.clientHeight };
});
console.log("STEP1 student/tree scroll:", JSON.stringify(treeScroll));
await page.screenshot({ path: "shots_fix3/01-student-tree.png" });

// 再测 /student/simulate
await page.goto(`${BASE}/student/simulate`, { waitUntil: "networkidle2" });
await sleep(1800);
const simScroll = await page.evaluate(() => {
  const v = document.querySelector(".view");
  if (!v) return { ok: false };
  const cs = getComputedStyle(v);
  v.scrollTop = 50;
  return { ok: cs.overflowY !== "hidden" && v.scrollTop === 50, overflowY: cs.overflowY, scrollTop: v.scrollTop, scrollHeight: v.scrollHeight };
});
console.log("STEP1b student/simulate scroll:", JSON.stringify(simScroll));
await page.screenshot({ path: "shots_fix3/02-student-simulate.png" });

// === 2 + 3. 辅导员端家校沟通：风险学生列表 + 搜索 + 布局 ===
await login("counselor", "2024014589", "1111");
await page.goto(`${BASE}/messages`, { waitUntil: "networkidle2" });
await sleep(2000);
const msgInfo = await page.evaluate(() => {
  const rows = document.querySelectorAll(".thread-row");
  const firstRow = rows[0];
  const firstClass = firstRow?.className || "";
  const firstText = firstRow?.innerText?.replace(/\s+/g, " ").slice(0, 60) || "";
  const search = document.querySelector(".thread-search input");
  const listHead = document.querySelector(".thread-list-head span")?.innerText || "";
  const listCount = document.querySelector(".thread-list-head em")?.innerText || "";
  const bubbles = document.querySelectorAll(".bubble");
  const bubbleMaxWidth = bubbles[0] ? getComputedStyle(bubbles[0]).maxWidth : "none";
  const threadListWidth = document.querySelector(".thread-list")?.getBoundingClientRect().width || 0;
  return {
    threadRows: rows.length,
    firstRowClass: firstClass,
    firstRowText: firstText,
    hasSearch: !!search,
    searchPlaceholder: search?.placeholder || "",
    listHead, listCount,
    bubbleMaxWidth,
    threadListWidth,
  };
});
console.log("STEP2 counselor msg list:", JSON.stringify(msgInfo));
await page.screenshot({ path: "shots_fix3/03-counselor-msg-list.png" });

// 测搜索：输入"戴"应过滤出戴永康
await page.evaluate(() => {
  const inp = document.querySelector(".thread-search input");
  if (inp) { inp.value = "戴"; inp.dispatchEvent(new Event("input")); }
});
await sleep(600);
const searchResult = await page.evaluate(() => ({
  rows: document.querySelectorAll(".thread-row").length,
  firstName: document.querySelector(".thread-row b")?.innerText || "",
}));
console.log("STEP2b search 戴:", JSON.stringify(searchResult));

// 测搜索班级：输入"计科2401"
await page.evaluate(() => {
  const inp = document.querySelector(".thread-search input");
  if (inp) { inp.value = "计科2401"; inp.dispatchEvent(new Event("input")); }
});
await sleep(600);
const searchClass = await page.evaluate(() => ({
  rows: document.querySelectorAll(".thread-row").length,
  classes: [...new Set([...document.querySelectorAll(".thread-cls")].map(e => e.innerText))],
}));
console.log("STEP2c search 计科2401:", JSON.stringify(searchClass));

// 清空搜索，点第一行红色学生看对话区
await page.evaluate(() => {
  const inp = document.querySelector(".thread-search input");
  if (inp) { inp.value = ""; inp.dispatchEvent(new Event("input")); }
});
await sleep(400);
await page.evaluate(() => document.querySelector(".thread-row")?.click());
await sleep(800);
const peerInfo = await page.evaluate(() => ({
  peer: document.querySelector(".conv-peer")?.innerText?.replace(/\s+/g, " ").slice(0, 80) || "",
  phone: document.querySelector(".peer-contact a")?.innerText || "",
  hint: document.querySelector(".conv-hint")?.innerText || "",
}));
console.log("STEP2d select first:", JSON.stringify(peerInfo));
await page.screenshot({ path: "shots_fix3/04-counselor-msg-selected.png" });

// === 4. 智慧森林点树弹出学生详情 ===
await login("counselor", "2024014589", "1111");
await page.evaluate(() => [...document.querySelectorAll(".mod-item")].find((e) => e.innerText.includes("智慧森林"))?.click());
await sleep(1500);
const forestInfo = await page.evaluate(() => ({
  trees: document.querySelectorAll(".tree").length,
  isButton: document.querySelector(".tree")?.tagName === "BUTTON",
}));
console.log("STEP4 forest:", JSON.stringify(forestInfo));
// 点第一棵树（应该是红色排第一）
await page.evaluate(() => document.querySelector(".tree")?.click());
await sleep(1500);
const drawerInfo = await page.evaluate(() => ({
  drawerVisible: !!document.querySelector(".drawer") || document.querySelector(".el-drawer")?.style.display !== "none",
  drawerTitle: document.querySelector(".drawer-head b, .el-drawer__title")?.innerText || "",
  hasRiskRing: !!document.querySelector(".risk-ring, .RiskRing"),
  hasFactors: !!document.querySelector(".factor-bars, .FactorBars"),
  drawerText: (document.querySelector(".drawer, .el-drawer")?.innerText || "").slice(0, 120),
}));
console.log("STEP4 drawer:", JSON.stringify(drawerInfo));
await page.screenshot({ path: "shots_fix3/05-forest-drawer.png" });

await browser.close();
console.log("DONE");
