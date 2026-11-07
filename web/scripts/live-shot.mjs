import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "https://academic-guardian-59801.app.workbuddy.host";
const SC = "4RRGYJTS3B";
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"] });
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
await p.goto(`${BASE}/?sharecode=${SC}`, { waitUntil: "networkidle2", timeout: 60000 });
await new Promise((s) => setTimeout(s, 1200));
const t = await p.evaluate(async () => {
  const r = await fetch("/api/auth/login", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role: "student", account: "20240067", password: "0000" }) });
  return (await r.json()).token;
});
await p.evaluate((x) => localStorage.setItem("ag.token", x), t);
await p.goto(`${BASE}/student`, { waitUntil: "networkidle2", timeout: 60000 });
await new Promise((s) => setTimeout(s, 2800));
await p.evaluate(() => document.querySelectorAll(".el-notification").forEach((n) => n.remove()));
const clip = await p.evaluate(() => {
  const v = document.querySelector(".view");
  const tb = document.querySelector(".topbar");
  const chips = [...document.querySelectorAll(".chip")];
  const cb = chips.length ? Math.max(...chips.map((c) => c.getBoundingClientRect().bottom + v.scrollTop)) : 0;
  return { x: 0, y: 0, width: window.innerWidth, height: Math.ceil(Math.max(v.scrollHeight, cb) + (tb ? tb.getBoundingClientRect().height : 0) + 20) };
});
await p.screenshot({ path: "C:/tmp/live_student.png", clip });
console.log(JSON.stringify(clip));
await b.close();
