import puppeteer from "puppeteer-core";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";

const b = await puppeteer.launch({
  executablePath: EXE,
  headless: true,
  args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"],
});
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });

// 1) 登录页
await p.goto(`${BASE}/`, { waitUntil: "networkidle2", timeout: 60000 });
await new Promise((s) => setTimeout(s, 2000));
await p.screenshot({ path: "C:/tmp/b_login.png" });
// 登录页整页高度
const h = await p.evaluate(() => document.documentElement.scrollHeight);
console.log("login scrollHeight", h);

// 2) 拿 token，进学生端，抓开屏四帧
const r = await fetch(`${BASE}/api/auth/login`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ role: "student", account: "20240067", password: "0000" }),
});
const token = (await r.json()).token;
await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), token);
await p.goto(`${BASE}/student`, { waitUntil: "domcontentloaded" });
const frames = [180, 420, 760, 1180, 1560, 2100, 2700];
let last = 0;
for (const t of frames) {
  await new Promise((s) => setTimeout(s, t - last));
  last = t;
  await p.screenshot({ path: `C:/tmp/b_wipe_${t}.png` });
}
await new Promise((s) => setTimeout(s, 1200));
await p.screenshot({ path: "C:/tmp/b_after.png" });
console.log("ok");
await b.close();
