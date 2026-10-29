import puppeteer from "puppeteer-core";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const NEW = "https://academic-guardian-19259.app.workbuddy.host";
const OUT = "C:/Users/Saber/WorkBuddy/2026-10-18-16-07-32/agents_run";

const browser = await puppeteer.launch({ executablePath: EXE, headless: "new", args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 900 });

// 登录页
await page.goto(`${NEW}/login?sharecode=MIIDH5PSIP`, { waitUntil: "networkidle2", timeout: 60000 });
await new Promise((r) => setTimeout(r, 1200));
await page.screenshot({ path: `${OUT}/new_login.png` });

// 学生端登录
await page.evaluate(() => localStorage.clear());
await page.reload({ waitUntil: "networkidle2" });
await page.type('input[placeholder*="学号"]', "20240001", { delay: 5 });
await page.type('input[type="password"]', "0000", { delay: 5 });
await page.click("form .submit");
await new Promise((r) => setTimeout(r, 3500));
await page.screenshot({ path: `${OUT}/new_student_home.png`, fullPage: false });

// 问一个问题看流式交互
await page.waitForSelector(".ch-draft input", { timeout: 15000 });
await page.click(".ch-draft input", { clickCount: 3 });
await page.keyboard.type("这学期还来得及补回来吗？", { delay: 5 });
await page.keyboard.press("Enter");
await new Promise((r) => setTimeout(r, 4000));
await page.screenshot({ path: `${OUT}/new_student_chat.png`, fullPage: false });

console.log("截图完成");
await browser.close();
