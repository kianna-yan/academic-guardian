/**
 * 交互验收脚本：用真实浏览器点开抽屉、文书弹窗与流式对话，逐帧截图。
 * 用法：node scripts/verify-ui.mjs   （需要本机已装 Edge，且服务跑在 8600）
 */
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = process.env.BASE_URL || "http://127.0.0.1:8600";
const OUT = process.env.OUT_DIR || "shots";

mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({
  executablePath: EXE,
  headless: true,
  args: ["--disable-gpu", "--no-sandbox", "--font-render-hinting=none"],
});

const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 940 });

const errors = [];
let stepLabel = "boot";
page.on("console", (m) => {
  if (m.type() === "error") errors.push(`[${stepLabel}] console: ${m.text()}`);
});
page.on("pageerror", (e) => {
  const stack = (e.stack || "").split("\n").slice(0, 6).join(" | ");
  errors.push(`[${stepLabel}] pageerror: ${e.message} :: ${stack}`);
});
/** 标记当前步骤，便于把报错归因到具体交互 */
function step(name) {
  // DEBUG_STEPS=1 时逐步打印这期间新增的报错，便于定位是哪一步触发的
  if (process.env.DEBUG_STEPS) {
    const fresh = errors.filter((e) => e.startsWith(`[${stepLabel}]`));
    if (fresh.length) console.log(`\n[step ${stepLabel}]\n  ` + fresh.join("\n  "));
    for (const e of fresh) errors.splice(errors.indexOf(e), 1);
  }
  stepLabel = name;
}

async function shot(name) {
  await page.screenshot({ path: `${OUT}/${name}.png` });
  console.log("shot:", name);
}

/* ---------- 登录：四个端各自独立账号 ---------- */
const STAFF = {
  counselor: { account: "2024014589", password: "1111" },
  admin: { account: "1234567899", password: "2222" },
};

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

// 学号从 meta 取，避免把演示学号写死在脚本里
await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
const DEMO = await page.evaluate(async () => (await fetch("/api/meta")).json());
const STUDENT = { account: DEMO.demo.student, password: "0000" };
await loginAs("counselor", STAFF.counselor.account, STAFF.counselor.password);

/* ---------- 辅导员端：名单 → 抽屉 → 谈话要点 ---------- */
step("counselor");
await page.goto(`${BASE}/counselor`, { waitUntil: "networkidle2" });
// 对话即首页：先进整页对话，再按键去预警名单看板
await page.waitForSelector(".chat-home", { timeout: 15000 });
await sleep(600);
await shot("ui_counselor_chat");
await page.click(".ch-go-dash");
await page.waitForSelector(".el-table__row", { timeout: 15000 });
await sleep(400);
await shot("ui_counselor");

step("drawer-open");
await page.click(".el-table__row");
await page.waitForFunction(() => {
  const d = document.querySelector(".el-drawer");
  return d && d.getBoundingClientRect().width > 0;
});
await sleep(700);
await shot("ui_drawer");

step("brief-dialog");
const briefClicked = await page.evaluate(() => {
  const btn = [...document.querySelectorAll(".drawer-foot .btn")][0];
  if (!btn) return false;
  btn.click();
  return true;
});
if (briefClicked) {
  await page.waitForFunction(() => {
    const d = document.querySelector(".el-dialog");
    return d && d.getBoundingClientRect().width > 0;
  });
  await sleep(700);
  await shot("ui_letter");
  await page.evaluate(() => document.querySelector(".el-dialog__headerbtn")?.click());
  await sleep(300);
}
step("drawer-close");
await page.evaluate(() => document.querySelector(".el-drawer__close-btn")?.click());
await sleep(400);

/* ---------- 学生端：整页对话流式输出 ---------- */
step("student-login");
await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
await loginAs("student", STUDENT.account, STUDENT.password);
await page.goto(`${BASE}/student`, { waitUntil: "networkidle2" });
await page.waitForSelector(".ch-draft input");
step("chat-stream");
await page.type(".ch-draft input", "我的风险分为什么这么高");
await page.click(".ch-draft button");
await page.waitForSelector(".trace-step");
await sleep(150);
const len1 = await page.evaluate(
  () => document.querySelector(".chat-stream .msg:last-child .bubble")?.innerText.length ?? 0,
);
await shot("ui_chat_streaming");
await sleep(450);
const len2 = await page.evaluate(
  () => document.querySelector(".chat-stream .msg:last-child .bubble")?.innerText.length ?? 0,
);
await page.waitForSelector(".trace-total", { timeout: 20000 });
await sleep(400);
await shot("ui_chat_done");
console.log(`stream growth: ${len1} -> ${len2} chars`);

// 引用与轨迹是否都渲染出来
const chatInfo = await page.evaluate(() => {
  const last = [...document.querySelectorAll(".chat-stream .msg")].pop();
  return {
    text: last?.querySelector(".bubble")?.innerText?.slice(0, 80) ?? "",
    steps: [...last.querySelectorAll(".trace-step")].map((e) => e.textContent.trim()),
    cites: [...last.querySelectorAll(".cite")].length,
    total: last?.querySelector(".trace-total")?.textContent?.trim() ?? "",
  };
});
console.log("chat:", JSON.stringify(chatInfo, null, 0));

/* ---------- 手机视口 ---------- */
step("mobile");
await page.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
for (const role of ["student", "counselor", "admin"]) {
  step("mobile-" + role);
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
  if (role === "student") await loginAs("student", STUDENT.account, STUDENT.password);
  else await loginAs(role, STAFF[role].account, STAFF[role].password);
  await page.goto(`${BASE}/${role}`, { waitUntil: "networkidle2" });
  await sleep(700);
  // 手机上进页面也是整页对话，再点按键看手机版看板
  await shot(`ui_m_${role}_chat`);
  const hasDash = await page.$(".ch-go-dash");
  if (hasDash) {
    await hasDash.click();
    await sleep(900);
    await shot(`ui_m_${role}`);
  }
}
const overflow = await page.evaluate(() => ({
  scrollW: document.documentElement.scrollWidth,
  clientW: document.documentElement.clientWidth,
}));
console.log("mobile overflow:", JSON.stringify(overflow));

console.log(errors.length ? `ERRORS:\n${errors.join("\n")}` : "no console errors");
await browser.close();
