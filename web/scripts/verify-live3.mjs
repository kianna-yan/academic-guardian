import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const LINK = "https://academic-guardian-56914.app.workbuddy.host/?sharecode=G4NKZPCZAO";
const BASE = LINK.split("?")[0];
const CODE = "G4NKZPCZAO";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--disable-gpu", "--no-sandbox"] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 880 });
page.on("pageerror", (e) => console.log("PAGEERROR:", e.message));

async function login(role, account, password) {
  const r = await fetch(`${BASE}/api/auth/login?sharecode=${CODE}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role, account, password }),
  });
  const j = await r.json();
  if (!j.ok) throw new Error(`login failed: ${JSON.stringify(j)}`);
  await page.goto(`${BASE}/login?sharecode=${CODE}`, { waitUntil: "networkidle2" });
  await page.evaluate((t) => { localStorage.clear(); localStorage.setItem("ag.token", t); }, j.token);
  const home = { student: "/student", counselor: "/counselor", parent: "/parent", teacher: "/teacher" }[role];
  await page.goto(`${BASE}${home}?sharecode=${CODE}`, { waitUntil: "networkidle2" });
  await sleep(2000);
}

// 1. 学生端子页滚动
await login("student", "20240067", "0000");
await page.goto(`${BASE}/student/tree?sharecode=${CODE}`, { waitUntil: "networkidle2" });
await sleep(2000);
const treeScroll = await page.evaluate(() => {
  const v = document.querySelector(".view");
  const cs = v ? getComputedStyle(v) : null;
  return { overflowY: cs?.overflowY, locked: cs?.overflowY === "hidden", scrollHeight: v?.scrollHeight, clientHeight: v?.clientHeight };
});
console.log("LIVE1 student/tree:", JSON.stringify(treeScroll));

// 2. 辅导员端家校沟通风险列表
await login("counselor", "2024014589", "1111");
await page.goto(`${BASE}/messages?sharecode=${CODE}`, { waitUntil: "networkidle2" });
await sleep(2000);
const msgInfo = await page.evaluate(() => ({
  rows: document.querySelectorAll(".thread-row").length,
  firstClass: document.querySelector(".thread-row")?.className || "",
  firstText: document.querySelector(".thread-row")?.innerText?.replace(/\s+/g, " ").slice(0, 50) || "",
  listHead: document.querySelector(".thread-list-head span")?.innerText || "",
  searchPh: document.querySelector(".thread-search input")?.placeholder || "",
}));
console.log("LIVE2 counselor msg:", JSON.stringify(msgInfo));

// 搜索测试
await page.evaluate(() => { const i = document.querySelector(".thread-search input"); if (i) { i.value = "计科2401"; i.dispatchEvent(new Event("input")); } });
await sleep(600);
const searchInfo = await page.evaluate(() => ({ rows: document.querySelectorAll(".thread-row").length, classes: [...new Set([...document.querySelectorAll(".thread-cls")].map(e => e.innerText))] }));
console.log("LIVE2b search:", JSON.stringify(searchInfo));

// 3. 智慧森林点树
await login("counselor", "2024014589", "1111");
await page.evaluate(() => [...document.querySelectorAll(".mod-item")].find((e) => e.innerText.includes("智慧森林"))?.click());
await sleep(1500);
await page.evaluate(() => document.querySelector(".tree")?.click());
await sleep(1500);
const drawerInfo = await page.evaluate(() => ({
  visible: !!document.querySelector(".el-drawer") && document.querySelector(".el-drawer")?.style.display !== "none",
  text: (document.querySelector(".el-drawer")?.innerText || "").slice(0, 100),
}));
console.log("LIVE3 forest drawer:", JSON.stringify(drawerInfo));

await browser.close();
console.log("DONE");
