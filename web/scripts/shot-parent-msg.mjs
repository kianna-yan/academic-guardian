import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--disable-gpu", "--no-sandbox"] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 880 });
const r = await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role: "parent", account: "20240067", password: "3333" }) });
const j = await r.json();
await page.goto(`${BASE}/login`, { waitUntil: "networkidle2" });
await page.evaluate((t) => { localStorage.clear(); localStorage.setItem("ag.token", t); }, j.token);
await page.goto(`${BASE}/parent`, { waitUntil: "networkidle2" });
await sleep(1500);
await page.evaluate(() => [...document.querySelectorAll(".mod-item")].find((e) => e.innerText.includes("家校沟通"))?.click());
await sleep(1800);
// 先发一条消息，让 thread 有内容，能看到完整对话+联系方式
await page.evaluate(() => {
  const ta = document.querySelector(".conv-input textarea");
  if (ta) { ta.value = "老师好，孩子最近状态怎么样？"; ta.dispatchEvent(new Event("input")); }
});
await sleep(200);
await page.click(".conv-input .btn.ok");
await sleep(1800);
await page.screenshot({ path: "shots_fix2/08-parent-msg-final.png" });
console.log("peer:", await page.evaluate(() => document.querySelector(".conv-peer")?.innerText?.replace(/\s+/g, " ").slice(0, 100)));
console.log("head:", await page.evaluate(() => document.querySelector(".msg-head")?.innerText?.replace(/\s+/g, " ")));
await browser.close();
