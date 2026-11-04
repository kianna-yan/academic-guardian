import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await puppeteer.launch({ executablePath: EXE, headless: true,
  args: ["--disable-gpu", "--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"] });
const page = await browser.newPage();
await page.setViewport({ width: 1084, height: 620 });
const r = await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ role: "admin", account: "1234567899", password: "2222" }) });
const j = await r.json();
await page.goto(`${BASE}/login`, { waitUntil: "networkidle2" });
await page.evaluate((t) => { localStorage.clear(); localStorage.setItem("ag.token", t); }, j.token);
await page.goto(`${BASE}/admin`, { waitUntil: "networkidle2" });
await sleep(1800);
await page.evaluate(() => [...document.querySelectorAll(".mod-item")].find((e) => e.innerText.includes("全校概览"))?.click());
await sleep(2200);
const box = await page.evaluate(() => { const el = document.querySelector(".donut-chart"); const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
await page.mouse.move(box.x + 6, box.y + box.h * 0.45);
await sleep(800);
await page.screenshot({ path: "shots_round5/8-narrow-tooltip.png" });
console.log(JSON.stringify(box));
await browser.close();
