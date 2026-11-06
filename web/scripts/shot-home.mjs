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
await p.setViewport({ width: Number(process.argv[3]||1440), height: Number(process.argv[4]||980), deviceScaleFactor: 1 });
await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
await p.goto(`${BASE}/${role}`, { waitUntil: "networkidle2" });
await new Promise((s) => setTimeout(s, 2600));
// 截图里不要弹窗遮挡
await p.evaluate(() => document.querySelectorAll(".el-notification").forEach((n) => n.remove()));
await p.screenshot({ path: `/tmp/shot_${role}.png` });
const info = await p.evaluate(() => {
  const q = (s) => document.querySelector(s);
  const box = (s) => { const e = q(s); if (!e) return null; const r = e.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]; };
  return {
    node0: box('[data-node="chat"]'),
    focus: box(".pt-focus"),
    list: box(".fx-list"),
    rows: document.querySelectorAll(".fx-row").length,
    aiCard: box(".ai-card"),
    chips: document.querySelectorAll(".chip").length,
    scrollH: document.querySelector(".view")?.scrollHeight,
    clientH: document.querySelector(".view")?.clientHeight,
  };
});
console.log(JSON.stringify(info));
await b.close();
