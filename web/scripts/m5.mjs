import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const role = process.argv[2] || "student";
const ACC = { student: ["20240067","0000"], counselor: ["2024014589","1111"], admin: ["1234567899","2222"], parent: ["20240067","3333"], teacher: ["2024014501","4444"] };
const [account, password] = ACC[role];
const r = await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role, account, password }) });
const t = (await r.json()).token;
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"] });
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 900 });
await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
await p.goto(`${BASE}/${role}`, { waitUntil: "networkidle2" });
await new Promise((s) => setTimeout(s, 2500));
console.log(await p.evaluate(() => {
  const g = (s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return { x: Math.round(r.x), w: Math.round(r.width), h: Math.round(r.height), y: Math.round(r.y) }; };
  return {
    portalClass: document.querySelector(".portal").className,
    body: g(".pt-body"),
    canvas: g(".pt-canvas"),
    field: g(".pt-field"),
    ai: g(".pt-ai"),
    bodyMinH: getComputedStyle(document.querySelector(".pt-body")).minHeight,
    scroll: document.querySelector(".view").scrollHeight,
  };
}));
await b.close();
