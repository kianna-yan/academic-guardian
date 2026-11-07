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
await p.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), token);

// 每个偏移都重新加载一次，等 .sw-open 出现（= 化幕开始）再等 offset 截图，
// 并顺手读出当帧遮罩进度，保证帧和进度对得上
const OFFSETS = [0, 130, 280, 430, 600, 800, 1000, 1160];
for (const off of OFFSETS) {
  await p.goto(`${BASE}/student`, { waitUntil: "domcontentloaded" });
  const info = await p.evaluate(async (ms) => {
    const t0 = performance.now();
    while (!document.querySelector(".sw-open")) {
      if (performance.now() - t0 > 8000) break;
      await new Promise((s) => requestAnimationFrame(s));
    }
    await new Promise((s) => setTimeout(s, ms));
    const core = document.querySelector("#swmA path:last-child");
    const coreB = document.querySelector("#swmB path:last-child");
    const wA = core ? parseFloat(core.getAttribute("stroke-width")) : -1;
    const wB = coreB ? parseFloat(coreB.getAttribute("stroke-width")) : -1;
    return { eraseA: Math.round(wA / 2), eraseB: Math.round(wB / 2) };
  }, off);
  await p.screenshot({ path: `C:/tmp/mm_${off}.png` });
  console.log(off, JSON.stringify(info));
}
await b.close();
console.log("ok");
