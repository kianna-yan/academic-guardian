import puppeteer from "puppeteer-core";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "https://academic-guardian.app.workbuddy.host";
const SHARECODE = "XNKLXQ7EPB";

const browser = await puppeteer.launch({ executablePath: EXE, headless: "new", args: ["--no-sandbox"] });
const page = await browser.newPage();
const bad = [];
page.on("response", (r) => {
  if (r.status() >= 400) bad.push(`[${step}] ${r.status()} ${r.request().method()} ${r.url()}`);
});
page.on("requestfailed", (r) => bad.push(`[${step}] FAILED ${r.method()} ${r.url()} ${r.failure()?.errorText}`));

let step = "首页";
await page.goto(`${BASE}/?sharecode=${SHARECODE}`, { waitUntil: "networkidle2", timeout: 60000 });
await new Promise((r) => setTimeout(r, 1500));

step = "登录";
await page.type('input[placeholder*="学号"], input[placeholder*="账号"]', "20240001", { delay: 20 }).catch(() => {});
await page.type('input[type="password"]', "0000", { delay: 20 });
await page.keyboard.press("Enter");
await new Promise((r) => setTimeout(r, 3500));

step = "对话页";
await page.type("textarea, .chat-input input, [contenteditable]", "我的学业情况怎么样", { delay: 20 }).catch(() => {});
await page.keyboard.press("Enter");
await new Promise((r) => setTimeout(r, 6000));

step = "看板";
await page.evaluate(() => {
  const btn = [...document.querySelectorAll("button, a, div[role=button]")].find((b) => /看板|学情|成绩/.test(b.textContent || ""));
  if (btn) btn.click();
}).catch(() => {});
await new Promise((r) => setTimeout(r, 4000));

step = "导出";
await page.evaluate(() => {
  const btn = [...document.querySelectorAll("button, a")].find((b) => /导出|下载/.test(b.textContent || ""));
  if (btn) btn.click();
}).catch(() => {});
await new Promise((r) => setTimeout(r, 5000));

console.log("=== 全链路 ≥400/失败请求 ===");
if (bad.length === 0) console.log("(无)");
for (const b of bad) console.log(" ", b);
await browser.close();
