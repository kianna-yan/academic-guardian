import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8621";
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox"] });
const p = await b.newPage();
await p.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
await p.goto(BASE + "/", { waitUntil: "networkidle2" });
await p.evaluate(async () => {
  const r = await fetch("/api/auth/login", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role: "student", account: "20240023", password: "0000" }) });
  const j = await r.json(); localStorage.setItem("ag.token", j.token);
});
await p.goto(BASE + "/student", { waitUntil: "networkidle2" });
await new Promise((s) => setTimeout(s, 2500));
await p.evaluate(() => document.querySelectorAll(".el-notification__closeBtn").forEach((x) => x.click()));
await new Promise((s) => setTimeout(s, 400));
await p.screenshot({ path: "C:/Users/lenovo/WorkBuddy/2026-11-03-16-18-31/_v8/shots_v3/mobile.png" });
// 底部
await p.evaluate(() => document.querySelector(".view").scrollTo(0, 9999));
await new Promise((s) => setTimeout(s, 600));
await p.screenshot({ path: "C:/Users/lenovo/WorkBuddy/2026-11-03-16-18-31/_v8/shots_v3/mobile_bottom.png" });
console.log("ok", await p.evaluate(() => ({ scroll: document.querySelector(".view").scrollHeight, h: document.querySelector(".view").clientHeight })));
await b.close();
