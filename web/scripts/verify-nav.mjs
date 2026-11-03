/**
 * 侧栏与对话模式互跳的完整回归：五个端各自「对话 → 看板 → 对话」走一遍。
 * 用法：node scripts/verify-nav.mjs   （需要本机 Edge，服务跑在 8600）
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
await page.setViewport({ width: 1440, height: 900 });
page.on("pageerror", (e) => console.log("PAGEERROR:", e.message));

const CASES = [
  { role: "student", row: 0, nav: "成绩走势", expect: "#grade" },
  { role: "counselor", row: 1, nav: "风险名单", expect: "#roster" },
  { role: "admin", row: 2, nav: "规则配置", expect: "#rules" },
  { role: "parent", row: 3, nav: "状态解读", expect: "#overview" },
  { role: "teacher", row: 4, nav: "课堂学情", expect: "#classroom" },
];

async function state() {
  return page.evaluate(() => ({
    path: location.pathname,
    hash: location.hash,
    chat: !!document.querySelector(".chat-home"),
    dash: !!document.querySelector(".dash-nav"),
    chips: [...document.querySelectorAll(".ch-suggest .chip")].map((e) => e.innerText),
    greet: (document.querySelector(".chat-stream .bubble")?.innerText || "").slice(0, 24),
    navActive: document.querySelector(".mod-item.active")?.innerText.replace(/\s+/g, " ").trim() || "",
    topRole: document.querySelector(".who-text span")?.innerText.replace(/\s+/g, " ").trim() || "",
  }));
}

for (const c of CASES) {
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle2" });
  await page.evaluate(() => localStorage.clear());
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle2" });
  await sleep(600);
  const rows = await page.$$(".hint-row");
  await rows[c.row].click();
  await sleep(200);
  await page.click(".submit");
  await page.waitForFunction(() => !location.pathname.includes("login"), { timeout: 20000 });
  await sleep(2200);
  const a = await state();

  await page.evaluate(
    (label) => [...document.querySelectorAll(".mod-item")].find((e) => e.innerText.includes(label))?.click(),
    c.nav,
  );
  await sleep(1200);
  const b = await state();

  await page.evaluate(
    () => [...document.querySelectorAll(".mod-item")].find((e) => e.classList.contains("mod-item") && e.querySelector(".mi-tag"))?.click(),
  );
  await sleep(1000);
  const d = await state();

  console.log(
    `${c.role.padEnd(9)} 进入=${a.path} chat=${a.chat} | 点「${c.nav}」→ hash=${b.hash} dash=${b.dash} chat=${b.chat} 高亮=${b.navActive} | 点对话→ chat=${d.chat} 高亮=${d.navActive}`,
  );
  console.log(`          chips=${JSON.stringify(a.chips)} greet="${a.greet}" topRole="${a.topRole}"`);
  if (b.hash !== c.expect) console.log(`          !! 期望锚点 ${c.expect}，实际 ${b.hash}`);
  await page.screenshot({ path: `${OUT}/nav-${c.role}.png` });
}

await browser.close();
