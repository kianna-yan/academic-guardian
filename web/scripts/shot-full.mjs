import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const role = process.argv[2] || "student";
const W = Number(process.argv[3] || 1440);
const acc = { student: "20240067", counselor: "2024014589", admin: "1234567899", parent: "20240067", teacher: "2024014501" }[role];
const pwd = { student: "0000", counselor: "1111", admin: "2222", parent: "3333", teacher: "4444" }[role];

const r = await fetch(`${BASE}/api/auth/login`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ role, account: acc, password: pwd }),
});
const t = (await r.json()).token;
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"] });
const p = await b.newPage();
await p.setViewport({ width: W, height: 900, deviceScaleFactor: 1 });
await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
await p.goto(`${BASE}/${role}`, { waitUntil: "networkidle2" });
await new Promise((s) => setTimeout(s, 2600));
await p.evaluate(() => document.querySelectorAll(".el-notification").forEach((n) => n.remove()));

/**
 * 首页是内部滚动容器（.view-home 自己滚），视口截图只能拿到上半截。
 * 关键是不能为了截全把视口撑高——门户的 min-height 是 100dvh - 84，
 * 视口一高，画布跟着长高、节点就被拉开，出来的就不是真实版面了。
 * 所以视口固定 1440×900（就是用户实际看到的样子），
 * 再用 clip 把整块滚动内容（含顶栏）一次性截下来。
 */
await p.setViewport({ width: W, height: 900, deviceScaleFactor: 1 });
await new Promise((s) => setTimeout(s, 700));

const clip = await p.evaluate(() => {
  const v = document.querySelector(".view");
  const tb = document.querySelector(".topbar");
  const cs = [...document.querySelectorAll(".chip")];
  const chipBottom = cs.length ? Math.max(...cs.map((c) => c.getBoundingClientRect().bottom + v.scrollTop)) : 0;
  const h = Math.ceil(Math.max(v.scrollHeight, chipBottom) + (tb ? tb.getBoundingClientRect().height : 0) + 20);
  return { x: 0, y: 0, width: window.innerWidth, height: h };
});

const info = await p.evaluate(() => {
  const v = document.querySelector(".view");
  const box = (s) => {
    const e = document.querySelector(s);
    if (!e) return null;
    const r = e.getBoundingClientRect();
    return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)];
  };
  return {
    viewScroll: v.scrollHeight,
    aiCard: box(".ai-card"),
    chips: box(".chip-row") || box(".chips"),
    lastChipBottom: Math.max(...[...document.querySelectorAll(".chip")].map((c) => c.getBoundingClientRect().bottom)),
  };
});
await p.screenshot({ path: `/tmp/full_${role}.png`, clip });
console.log(JSON.stringify({ role, height: clip.height, ...info }));
await b.close();
