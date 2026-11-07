/**
 * 检查「流星飞行阶段幕布是否纯绿」：在 .sw 出现但 .sw-open 还没加上的时刻
 * 截一帧，统计绿色覆盖率；顺带在化幕刚开始（.sw-open 后立刻）截一帧对照。
 */
import puppeteer from "puppeteer-core";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";

const r = await fetch(`${BASE}/api/auth/login`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ role: "student", account: "20240067", password: "0000" }),
});
const token = (await r.json()).token;

const b = await puppeteer.launch({
  executablePath: EXE,
  headless: true,
  args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"],
});
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 900 });
await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), token);
await p.goto(`${BASE}/student`, { waitUntil: "domcontentloaded" });

// 等 .sw 出现（幕布已盖上、星星在飞），此时不应有任何擦除
await p.waitForSelector(".sw", { timeout: 8000 });
const during = await p.evaluate(() => {
  const pane = document.querySelector(".sw-pane-a");
  const mask = pane ? getComputedStyle(pane).maskImage : "none";
  const core = document.querySelector("#swmA path:last-child");
  const w = core ? parseFloat(core.getAttribute("stroke-width")) : -1;
  return { open: document.querySelector(".sw-open") !== null, coreW: w, mask };
});
await p.screenshot({ path: "C:/tmp/pure_fly.png" });

// 等 .sw-open 出现（化幕起点），立刻读黑芯宽度
await p.waitForSelector(".sw-open", { timeout: 8000 });
const atStart = await p.evaluate(() => {
  const core = document.querySelector("#swmA path:last-child");
  const coreB = document.querySelector("#swmB path:last-child");
  return {
    wA: core ? parseFloat(core.getAttribute("stroke-width")) : -1,
    wB: coreB ? parseFloat(coreB.getAttribute("stroke-width")) : -1,
  };
});

console.log(JSON.stringify({ during, atStart }));
await b.close();
