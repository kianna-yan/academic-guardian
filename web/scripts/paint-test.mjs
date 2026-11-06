import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const r = await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role: "student", account: "20240067", password: "0000" }) });
const t = (await r.json()).token;
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"] });
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });
await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
await p.goto(`${BASE}/student`, { waitUntil: "networkidle2" });
await new Promise((s) => setTimeout(s, 2600));
const st = await p.evaluate(() => {
  const el = document.querySelector('.pt-node[data-node="chat"]');
  const poly = el.querySelector("polygon");
  const cs = getComputedStyle(poly);
  const before = getComputedStyle(el.querySelector(".nd-shape"), "::before");
  return { stroke: cs.strokeWidth, fill: cs.fill, join: cs.strokeLinejoin, beforeContent: before.content, beforeClip: before.clipPath };
});
console.log(JSON.stringify(st));
await p.evaluate(() => {
  const poly = document.querySelector('.pt-node[data-node="chat"] polygon');
  poly.style.fill = "#ff0000";
  poly.style.stroke = "#0000ff";
  poly.style.strokeWidth = "0.6";
});
await new Promise((s) => setTimeout(s, 400));
const el = await p.$('.pt-node[data-node="chat"]');
await el.screenshot({ path: "C:/tmp/paint_test.png" });
await b.close();
