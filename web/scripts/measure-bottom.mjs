import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const role = process.argv[2] || "student";
const acc = { student: "20240067", counselor: "2024014589", admin: "1234567899", parent: "20240067", teacher: "2024014501" }[role];
const pwd = { student: "0000", counselor: "1111", admin: "2222", parent: "3333", teacher: "4444" }[role];
const r = await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role, account: acc, password: pwd }) });
const t = (await r.json()).token;
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"] });
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
await p.goto(`${BASE}/${role}`, { waitUntil: "networkidle2" });
await new Promise((s) => setTimeout(s, 2600));
const info = await p.evaluate(() => {
  const v = document.querySelector(".view");
  const out = {};
  const sel = [".topbar", ".view", ".portal", ".pt-canvas", ".pt-focus", ".ai-card", ".chip-row", ".chip", ".fx-card"];
  for (const s of sel) { const e = document.querySelector(s); if (e) { const r = e.getBoundingClientRect(); out[s] = { top: Math.round(r.top), bottom: Math.round(r.bottom), h: Math.round(r.height) }; } }
  out.viewScroll = v.scrollHeight; out.viewClient = v.clientHeight; out.docH = document.documentElement.scrollHeight;
  out.chipCount = document.querySelectorAll(".chip").length;
  out.lastChip = (() => { const cs = [...document.querySelectorAll(".chip")]; return cs.length ? Math.round(Math.max(...cs.map(c => c.getBoundingClientRect().bottom))) : null; })();
  return out;
});
console.log(JSON.stringify(info, null, 1));
await b.close();
