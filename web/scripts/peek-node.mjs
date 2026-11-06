import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const r = await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role: "student", account: "20240067", password: "0000" }) });
const t = (await r.json()).token;
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"] });
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 900 });
await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
await p.goto(`${BASE}/student`, { waitUntil: "networkidle2" });
await new Promise((s) => setTimeout(s, 2500));
const out = await p.evaluate(() => {
  const el = document.querySelector('.pt-node');
  const svgs = [...el.querySelectorAll("svg")].map((s) => s.outerHTML.replace(/\s+/g, " ").slice(0, 400));
  const cs = getComputedStyle(el.querySelector(".nd-shape"));
  return { html: el.outerHTML.replace(/\s+/g, " ").slice(0, 900), svgCount: svgs.length, svgs, transform: cs.transform, w: cs.width, h: cs.height };
});
console.log(JSON.stringify(out, null, 1));
await b.close();
