import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "https://academic-guardian-56914.app.workbuddy.host";
const CODE = "G4NKZPCZAO";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--disable-gpu", "--no-sandbox"] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 880 });
page.on("pageerror", (e) => console.log("PAGEERROR:", e.message));
page.on("console", (m) => { if (m.type() === "error") console.log("CONSOLE:", m.text().slice(0, 150)); });

// 登录学生
const r = await fetch(`${BASE}/api/auth/login?sharecode=${CODE}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role: "student", account: "20240067", password: "0000" }) });
const j = await r.json();
console.log("login:", j.ok);
await page.goto(`${BASE}/login?sharecode=${CODE}`, { waitUntil: "networkidle2" });
await page.evaluate((t) => { localStorage.clear(); localStorage.setItem("ag.token", t); }, j.token);

// 先进 /student 看看 chat 模式
await page.goto(`${BASE}/student?sharecode=${CODE}`, { waitUntil: "networkidle2" });
await sleep(2500);
const studentHome = await page.evaluate(() => ({
  viewClass: document.querySelector(".view")?.className || "",
  path: location.pathname,
}));
console.log("student home:", JSON.stringify(studentHome));

// 跳 /student/tree
await page.goto(`${BASE}/student/tree?sharecode=${CODE}`, { waitUntil: "networkidle2" });
await sleep(3000);
const treeInfo = await page.evaluate(() => {
  const v = document.querySelector(".view");
  return {
    viewClass: v?.className || "",
    overflowY: v ? getComputedStyle(v).overflowY : "",
    path: location.pathname,
    hasContent: !!document.querySelector(".tree-view, .wisdom-tree, svg"),
    scrollHeight: v?.scrollHeight,
    clientHeight: v?.clientHeight,
  };
});
console.log("student/tree:", JSON.stringify(treeInfo));

// 辅导员 messages
const r2 = await fetch(`${BASE}/api/auth/login?sharecode=${CODE}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role: "counselor", account: "2024014589", password: "1111" }) });
const j2 = await r2.json();
await page.evaluate((t) => { localStorage.setItem("ag.token", t); }, j2.token);
await page.goto(`${BASE}/messages?sharecode=${CODE}`, { waitUntil: "networkidle2" });
await sleep(4000);
const msgInfo = await page.evaluate(() => ({
  viewClass: document.querySelector(".view")?.className || "",
  rows: document.querySelectorAll(".thread-row").length,
  listHead: document.querySelector(".thread-list-head span")?.innerText || "",
  bodyText: document.body.innerText.slice(0, 200),
}));
console.log("counselor msg:", JSON.stringify(msgInfo));

await browser.close();
console.log("DONE");
