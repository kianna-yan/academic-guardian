import puppeteer from "puppeteer-core";
import fs from "node:fs";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = process.env.AG_BASE || "https://academic-guardian-56914.app.workbuddy.host";
const SC = process.env.AG_SC ?? "G4NKZPCZAO";
const OUT = "C:/Users/lenovo/WorkBuddy/2026-11-03-16-18-31/_v8/shots_v3";
fs.mkdirSync(OUT, { recursive: true });
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox"] });

async function login(p, role, acc, pwd) {
  await p.goto(`${BASE}/?sharecode=${SC}`, { waitUntil: "networkidle2", timeout: 60000 });
  await p.evaluate(async ([a, p2, ro]) => {
    const r = await fetch("/api/auth/login", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role: ro, account: a, password: p2 }) });
    const j = await r.json();
    if (j.token) localStorage.setItem("ag.token", j.token);
  }, [acc, pwd, role]);
}

/* ① 手机端 */
{
  const p = await b.newPage();
  await p.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
  await login(p, "student", "20240023", "0000");
  await p.goto(`${BASE}/student?sharecode=${SC}`, { waitUntil: "networkidle2", timeout: 60000 });
  await new Promise((s) => setTimeout(s, 2500));
  await p.evaluate(() => document.querySelectorAll(".el-notification__closeBtn").forEach((x) => x.click()));
  await new Promise((s) => setTimeout(s, 400));
  const r = await p.evaluate(() => ({
    nodes: document.querySelectorAll(".pt-node").length,
    overflowX: document.documentElement.scrollWidth > window.innerWidth + 2,
    dockTop: Math.round(document.querySelector('[data-test="ai-dock"]').getBoundingClientRect().top),
  }));
  console.log("mobile 390", JSON.stringify(r));
  await p.screenshot({ path: `${OUT}/mobile.png` });
  await p.close();
}

/* ② 点节点是否真跳转 */
{
  const cases = [
    ["student", "schedule", "/student/schedule", "20240023", "0000"],
    ["counselor", "roster", "/counselor/roster", "2024014589", "1111"],
    ["admin", "rules", "/admin/rules", "1234567899", "2222"],
    ["teacher", "resources", "/teacher/resources", "2024014501", "4444"],
    ["parent", "overview", "/parent/overview", "20240067", "3333"],
  ];
  for (const [role, key, want, acc, pwd] of cases) {
    const p = await b.newPage();
    await p.setViewport({ width: 1440, height: 900 });
    await login(p, role, acc, pwd);
    await p.goto(`${BASE}${want.split("/").slice(0, 2).join("/")}?sharecode=${SC}`, { waitUntil: "networkidle2", timeout: 60000 });
    await new Promise((s) => setTimeout(s, 2200));
    const before = await p.evaluate(() => location.pathname);
    await p.evaluate((k) => document.querySelector(`[data-node="${k}"]`)?.click(), key);
    await new Promise((s) => setTimeout(s, 1200));
    const after = await p.evaluate(() => location.pathname);
    console.log(role.padEnd(10), "click", key.padEnd(9), before, "→", after, after === want ? "PASS" : "FAIL");
    await p.close();
  }
}

/* ③ AI 条展开/收起 */
{
  const p = await b.newPage();
  await p.setViewport({ width: 1440, height: 900 });
  await login(p, "student", "20240023", "0000");
  await p.goto(`${BASE}/student?sharecode=${SC}`, { waitUntil: "networkidle2", timeout: 60000 });
  await new Promise((s) => setTimeout(s, 2200));
  await p.click('[data-test="ai-dock"]');
  await new Promise((s) => setTimeout(s, 1400));
  const open = await p.evaluate(() => {
    const el = document.querySelector(".ai-sheet");
    return el ? Math.round(el.getBoundingClientRect().width) : 0;
  });
  await p.evaluate(() => document.querySelector('[data-test="sheet-close"]')?.click());
  await new Promise((s) => setTimeout(s, 900));
  const closed = await p.evaluate(() => ({ sheet: !!document.querySelector(".ai-sheet"), nodes: document.querySelectorAll(".pt-node").length }));
  console.log("ai-sheet width", open, "| closed", JSON.stringify(closed));
  await p.close();
}
await b.close();
