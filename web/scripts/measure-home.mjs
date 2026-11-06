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
await p.setViewport({ width: Number(process.argv[3] || 1440), height: Number(process.argv[4] || 900), deviceScaleFactor: 1 });
// 关掉两条横幅的干扰：直接移除
await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
await p.goto(`${BASE}/${role}`, { waitUntil: "networkidle2" });
await new Promise((s) => setTimeout(s, 2600));
const info = await p.evaluate(() => {
  const box = (s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }; };
  const labels = [...document.querySelectorAll(".nd-label")].map((e) => ({ t: e.textContent, ow: e.scrollWidth, cw: e.clientWidth, oh: e.scrollHeight, ch: e.clientHeight, fs: getComputedStyle(e).fontSize }));
  return {
    topbar: box(".topbar"), portal: box(".portal"), body: box(".pt-body"), side: box(".pt-side"), canvas: box(".pt-canvas"), focus: box(".pt-focus"), ai: box(".pt-ai"), aiCard: box(".ai-card"),
    overflow: labels.filter((l) => l.ow > l.cw + 1 || l.oh > l.ch + 1),
    labels: labels.length,
  };
});
console.log(JSON.stringify(info, null, 1));
await p.screenshot({ path: `/tmp/shot2_${role}.png`, fullPage: true });
await b.close();
