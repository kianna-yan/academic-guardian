import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const r = await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role: "student", account: "20240067", password: "0000" }) });
const token = (await r.json()).token;
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"] });
const p = await b.newPage();
await p.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), token);
await p.goto(`${BASE}/student`, { waitUntil: "domcontentloaded" });
const info = await p.evaluate(async (ms) => {
  const t0 = performance.now();
  while (!document.querySelector(".sw-open")) {
    if (performance.now() - t0 > 8000) break;
    await new Promise((s) => requestAnimationFrame(s));
  }
  await new Promise((s) => setTimeout(s, ms));
  return true;
}, 820);
await p.screenshot({ path: "C:/tmp/mm_mobile.png" });
console.log("ok");
await b.close();
