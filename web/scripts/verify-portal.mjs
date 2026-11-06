import puppeteer from "puppeteer-core";
import fs from "node:fs";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8620";
const OUT = "C:/Users/lenovo/WorkBuddy/2026-11-03-16-18-31/_v8/shots_portal";
fs.mkdirSync(OUT, { recursive: true });

const ACCOUNTS = [
  { role: "student", account: "20240067", password: "0000", home: "/student", shape: "hex", nodes: 6 },
  { role: "counselor", account: "2024014589", password: "1111", home: "/counselor", shape: "hex", nodes: 6 },
  { role: "admin", account: "1234567899", password: "2222", home: "/admin", shape: "square", nodes: 8 },
  { role: "teacher", account: "2024014501", password: "4444", home: "/teacher", shape: "pent", nodes: 5 },
  { role: "parent", account: "20240067", password: "3333", home: "/parent", shape: "diamond", nodes: 4 },
];

const results = [];
function ok(name, pass, extra = "") {
  results.push({ name, pass });
  console.log(`${pass ? "PASS" : "FAIL"}  ${name}${extra ? "  " + extra : ""}`);
}

async function login(a) {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ role: a.role, account: a.account, password: a.password }),
  });
  if (!res.ok) throw new Error(`${a.role} 登录失败 ${res.status}`);
  const j = await res.json();
  return j.token;
}

const browser = await puppeteer.launch({
  executablePath: EXE,
  headless: true,
  args: ["--disable-gpu", "--no-sandbox"],
});

for (const a of ACCOUNTS) {
  const token = await login(a);
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1.5 });
  const errs = [];
  page.on("pageerror", (e) => errs.push(e.message));
  page.on("console", (m) => m.type() === "error" && errs.push(m.text()));

  await page.evaluateOnNewDocument((t) => {
    localStorage.setItem("ag.token", t);
  }, token);
  await page.goto(BASE + a.home, { waitUntil: "networkidle2", timeout: 45000 });
  await new Promise((r) => setTimeout(r, 2200));

  const info = await page.evaluate(() => {
    const p = document.querySelector(".portal");
    const nodes = document.querySelectorAll(".pt-node");
    const dock = document.querySelector(".ai-dock");
    const cards = document.querySelectorAll(".card").length;
    return {
      hasPortal: !!p,
      portalClass: p ? p.className : "",
      nodes: nodes.length,
      dock: !!dock,
      cards,
      viewScroll: (document.querySelector(".view") || {}).scrollHeight || 0,
    };
  });

  ok(`${a.role} 首屏是图形门户`, info.hasPortal);
  ok(`${a.role} 节点数 = ${a.nodes}`, info.nodes === a.nodes, `实际 ${info.nodes}`);
  ok(`${a.role} 形状 = ${a.shape}`, info.portalClass.includes(`sh-${a.shape}`), info.portalClass);
  ok(`${a.role} 底部有 AI 输入条`, info.dock);
  ok(`${a.role} 旧数据卡片仍在门户下方`, info.cards > 0, `${info.cards} 张`);

  await page.screenshot({ path: `${OUT}/${a.role}-home.png` });

  // 点第一个节点：锚点或路由
  const firstNode = await page.evaluate(() => {
    const n = document.querySelector(".pt-node");
    return { key: n?.getAttribute("data-node"), label: n?.querySelector(".nd-label")?.textContent };
  });
  const beforeUrl = page.url();
  const beforeTop = await page.evaluate(() => (document.querySelector(".view") || {}).scrollTop || 0);
  await page.click(".pt-node");
  await new Promise((r) => setTimeout(r, 1400));
  const afterUrl = page.url();
  const afterTop = await page.evaluate(() => (document.querySelector(".view") || {}).scrollTop || 0);
  ok(
    `${a.role} 点「${firstNode.label}」有响应`,
    afterUrl !== beforeUrl || afterTop > beforeTop + 20,
    `${afterTop - beforeTop}px / ${afterUrl.replace(BASE, "")}`,
  );

  // 回首页再测 AI 抽屉
  await page.goto(BASE + a.home, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1500));
  await page.click('[data-test="ai-dock"]');
  await new Promise((r) => setTimeout(r, 900));

  const sheet = await page.evaluate(() => {
    const s = document.querySelector(".ai-sheet");
    if (!s) return null;
    const r = s.getBoundingClientRect();
    const chatHome = s.querySelector(".chat-home");
    return {
      w: Math.round(r.width),
      h: Math.round(r.height),
      top: Math.round(r.top),
      hasChat: !!chatHome,
      hasComposer: !!s.querySelector("[data-test=chat-input]"),
      vh: window.innerHeight,
      vw: window.innerWidth,
    };
  });
  ok(`${a.role} 点输入条弹出对话`, !!sheet && sheet.hasChat);
  ok(
    `${a.role} 对话向上铺满界面`,
    !!sheet && sheet.h >= sheet.vh * 0.85 && sheet.top <= sheet.vh * 0.08,
    sheet ? `${sheet.w}×${sheet.h} top=${sheet.top}` : "",
  );
  ok(`${a.role} 抽屉里有输入框`, !!sheet?.hasComposer);
  await page.screenshot({ path: `${OUT}/${a.role}-sheet.png` });

  // 收起
  await page.click('[data-test="sheet-close"]');
  await new Promise((r) => setTimeout(r, 800));
  const closed = await page.evaluate(() => !document.querySelector(".ai-sheet"));
  ok(`${a.role} 收起后回到门户`, closed);

  ok(`${a.role} 无控制台报错`, errs.length === 0, errs.slice(0, 2).join(" | "));
  await page.close();
}

// 学生端手机屏
{
  const token = await login(ACCOUNTS[0]);
  const page = await browser.newPage();
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 2, isMobile: true });
  await page.evaluateOnNewDocument((t) => localStorage.setItem("ag.token", t), token);
  await page.goto(BASE + "/student", { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 2000));
  const m = await page.evaluate(() => {
    const p = document.querySelector(".portal");
    const dock = document.querySelector(".ai-dock");
    return { has: !!p, dock: !!dock, w: p ? Math.round(p.getBoundingClientRect().width) : 0 };
  });
  ok("手机端 390 宽仍有门户与 AI 条", m.has && m.dock, `宽 ${m.w}px`);
  await page.screenshot({ path: `${OUT}/mobile-home.png` });
  await page.click('[data-test="ai-dock"]');
  await new Promise((r) => setTimeout(r, 900));
  const s = await page.evaluate(() => {
    const el = document.querySelector(".ai-sheet");
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { w: Math.round(r.width), h: Math.round(r.height), vh: window.innerHeight };
  });
  ok("手机端对话铺满", !!s && s.h > s.vh * 0.9 && s.w > 380, s ? `${s.w}×${s.h}` : "");
  await page.screenshot({ path: `${OUT}/mobile-sheet.png` });
  await page.close();
}

await browser.close();
const fail = results.filter((r) => !r.pass);
console.log(`\n${results.length - fail.length}/${results.length} 通过`);
process.exit(fail.length ? 1 : 0);
