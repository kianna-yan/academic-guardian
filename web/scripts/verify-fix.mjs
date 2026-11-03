/**
 * 本轮四个问题的验收脚本：登录页排版、对话区文案与端口一致、侧栏在对话模式下可跳转、各端 AI 顾问入口。
 * 用法：node scripts/verify-fix.mjs   （需要本机 Edge，服务跑在 8600）
 */
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = process.env.BASE_URL || "http://127.0.0.1:8600";
const OUT = process.env.OUT_DIR || "shots_fix";

mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({
  executablePath: EXE,
  headless: true,
  args: ["--disable-gpu", "--no-sandbox", "--font-render-hinting=none"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
page.on("pageerror", (e) => console.log("PAGEERROR:", e.message));

const LOGIN = {
  student: { row: 0 },
  counselor: { row: 1 },
  admin: { row: 2 },
  parent: { row: 3 },
  teacher: { row: 4 },
};

async function shot(name) {
  await page.screenshot({ path: `${OUT}/${name}.png` });
  console.log("shot:", name);
}

async function login(role) {
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle2" });
  await page.evaluate(() => localStorage.clear());
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle2" });
  await sleep(600);
  const rows = await page.$$(".hint-row");
  await rows[LOGIN[role].row].click();
  await sleep(250);
  await page.click(".submit");
  await page.waitForFunction(() => !location.pathname.includes("login"), { timeout: 15000 });
  await sleep(2500);
  console.log("after login:", role, await page.evaluate(() => location.pathname));
}

async function logout() {
  await page.evaluate(() => localStorage.clear());
}

function readChat() {
  return page.evaluate(() => {
    const greet = document.querySelector(".chat-stream .bubble")?.innerText || "";
    const chips = [...document.querySelectorAll(".ch-suggest .chip")].map((e) => e.innerText);
    const title = document.querySelector(".ch-title strong")?.innerText || "";
    const nav = [...document.querySelectorAll(".mod-item")].map((e) => e.innerText.replace(/\s+/g, " ").trim());
    return { greet: greet.slice(0, 40), chips, title, nav };
  });
}

// ---------- 1) 登录页 ----------
await page.goto(`${BASE}/login`, { waitUntil: "networkidle2" });
await page.evaluate(() => localStorage.clear());
await page.goto(`${BASE}/login`, { waitUntil: "networkidle2" });
await sleep(800);
await shot("01-login");
const loginInfo = await page.evaluate(() => ({
  tabs: [...document.querySelectorAll(".tab")].map((e) => e.innerText.replace(/\s+/g, "")),
  rows: [...document.querySelectorAll(".hint-row")].map((e) => e.innerText.replace(/\s+/g, " ").trim()),
  tabRows: new Set([...document.querySelectorAll(".tab")].map((e) => Math.round(e.getBoundingClientRect().top))).size,
}));
console.log("LOGIN:", JSON.stringify(loginInfo, null, 1));

// ---------- 2) 辅导员端 ----------
await login("counselor");
console.log("COUNSELOR:", JSON.stringify(await readChat(), null, 1));
await shot("02-counselor-chat");

// 对话模式下点侧栏「风险名单」：应切到看板并滚到锚点
const roster = await page.evaluateHandle(() =>
  [...document.querySelectorAll(".mod-item")].find((e) => e.innerText.includes("风险名单")),
);
await roster.asElement().click();
await sleep(1200);
const afterRoster = await page.evaluate(() => ({
  hash: location.hash,
  dash: !!document.querySelector(".dash-nav"),
  chat: !!document.querySelector(".chat-home"),
}));
console.log("COUNSELOR nav 风险名单:", JSON.stringify(afterRoster));
await shot("03-counselor-roster");

// 再点「辅导员对话」回对话
await page.evaluate(() =>
  [...document.querySelectorAll(".mod-item")].find((e) => e.innerText.includes("辅导员对话"))?.click(),
);
await sleep(900);
console.log("COUNSELOR back to chat:", JSON.stringify(await page.evaluate(() => ({ chat: !!document.querySelector(".chat-home") }))));

// ---------- 3) 家长端 ----------
await logout();
await login("parent");
console.log("PARENT:", JSON.stringify(await readChat(), null, 1));
await shot("04-parent-chat");

// ---------- 4) 教务端 ----------
await logout();
await login("admin");
console.log("ADMIN:", JSON.stringify(await readChat(), null, 1));
await shot("05-admin-chat");

const rules = await page.evaluateHandle(() =>
  [...document.querySelectorAll(".mod-item")].find((e) => e.innerText.includes("规则配置")),
);
await rules.asElement().click();
await sleep(1200);
console.log(
  "ADMIN nav 规则配置:",
  JSON.stringify(
    await page.evaluate(() => ({ hash: location.hash, dash: !!document.querySelector(".dash-nav"), chat: !!document.querySelector(".chat-home") })),
  ),
);
await shot("06-admin-rules");

// ---------- 5) 教师端 ----------
await logout();
await login("teacher");
console.log("TEACHER:", JSON.stringify(await readChat(), null, 1));
await shot("07-teacher-chat");

// ---------- 6) 学生端（回归） ----------
await logout();
await login("student");
console.log("STUDENT:", JSON.stringify(await readChat(), null, 1));
await shot("08-student-chat");

await browser.close();
