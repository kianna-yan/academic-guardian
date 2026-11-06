import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const r = await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role: "student", account: "20240067", password: "0000" }) });
const t = (await r.json()).token;
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"] });
const p = await b.newPage();
await p.setViewport({ width: 390, height: 844 });
await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
await p.goto(`${BASE}/student`, { waitUntil: "networkidle2" });
await new Promise((s) => setTimeout(s, 2500));
console.log(await p.evaluate(() => {
  const f = document.querySelector(".pt-field"), c = document.querySelector(".pt-canvas"), n = document.querySelector(".pt-node");
  const cs = (e) => { const s = getComputedStyle(e); return { pos: s.position, w: Math.round(e.getBoundingClientRect().width), h: Math.round(e.getBoundingClientRect().height), y: Math.round(e.getBoundingClientRect().y), disp: s.display }; };
  const c2 = getComputedStyle(c);
  return { field: cs(f), canvas: cs(c), node: cs(n), body: cs(document.querySelector(".pt-body")), canvasCss: { h: c2.height, minH: c2.minHeight, ov: c2.overflow, rows: getComputedStyle(document.querySelector(".pt-body")).gridTemplateRows } };
}));
await b.close();
