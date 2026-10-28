import puppeteer from "puppeteer-core";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const QUESTION = "我的风险分为什么这么高？隔离测试0928";

const browser = await puppeteer.launch({ executablePath: EXE, headless: "new", args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 900 });

// 1) 学生端登录（走真实登录表单，SPA 内切换，复现泄漏场景）
await page.goto(`${BASE}/login`, { waitUntil: "networkidle2", timeout: 60000 });
await page.evaluate(() => localStorage.clear());
await page.reload({ waitUntil: "networkidle2" });
await page.type('input[placeholder*="学号"]', "20240001", { delay: 10 });
await page.type('input[type="password"]', "0000", { delay: 10 });
await page.click("form .submit");
await new Promise((r) => setTimeout(r, 3500));

// 2) 学生提问，等回答完
await page.waitForSelector(".ch-draft input", { timeout: 15000 });
await page.click(".ch-draft input", { clickCount: 3 });
await page.keyboard.type(QUESTION, { delay: 5 });
await page.keyboard.press("Enter");
await page.waitForFunction(
  () => {
    const msgs = document.querySelectorAll(".chat-stream .msg");
    const last = msgs[msgs.length - 1];
    return last && last.querySelector(".bubble")?.textContent.length > 10 && !last.querySelector(".spinner") && !last.querySelector(".typing-caret");
  },
  { timeout: 40000, polling: 300 },
);
console.log("学生端问答完成");

// 3) 不刷新页面：退出 → 切导员 tab → 登录（这就是旧版泄漏的路径）
await page.evaluate(() => {
  const btn = [...document.querySelectorAll("button")].find((b) => (b.textContent || "").trim() === "退出");
  if (btn) btn.click();
});
await page.waitForFunction(() => document.querySelector(".el-message-box__btns .el-button--primary"), { timeout: 8000 });
await page.click(".el-message-box__btns .el-button--primary"); // 确认退出
await new Promise((r) => setTimeout(r, 2000));

await page.evaluate(() => {
  const tab = [...document.querySelectorAll(".tab")].find((b) => /导员/.test(b.textContent || ""));
  if (tab) tab.click();
});
await page.type('input[placeholder*="工号"]', "2024014589", { delay: 10 });
await page.type('input[type="password"]', "1111", { delay: 10 });
await page.click("form .submit");
await new Promise((r) => setTimeout(r, 4000));

// 4) 断言
await page.waitForSelector(".chat-stream .msg", { timeout: 15000 });
const body = await page.evaluate(() => document.body.innerText);
const leaked = body.includes("隔离测试0928");
const persona = body.includes("辅导员助手");
const keys = await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith("ag.chat")));

console.log("导员端看到学生的问题:", leaked ? "泄露!!" : "没有(隔离OK)");
console.log("导员端人设问候(辅导员助手):", persona ? "是" : "否");
console.log("会话存储键(应按角色.账号分开):", keys);

await browser.close();
if (leaked || !persona) { console.error("ISOLATION FAILED"); process.exit(1); }
console.log("\nISOLATION TEST PASSED");
