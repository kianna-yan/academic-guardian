import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = process.env.AG_BASE || "https://academic-guardian-56914.app.workbuddy.host";
const SC = process.env.AG_SC ?? "G4NKZPCZAO";
const OUT = "C:/Users/lenovo/WorkBuddy/2026-11-03-16-18-31/_v8/shots_v3";
import fs from "node:fs";
fs.mkdirSync(OUT, { recursive: true });

const ACC = {
  student: ["20240023", "0000", "/student"],
  counselor: ["2024014589", "1111", "/counselor"],
  admin: ["1234567899", "2222", "/admin"],
  teacher: ["2024014501", "4444", "/teacher"],
  parent: ["20240067", "3333", "/parent"],
};

const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox"] });
for (const [role, [acc, pwd, path]] of Object.entries(ACC)) {
  const p = await b.newPage();
  await p.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  const errs = [];
  p.on("pageerror", (e) => errs.push(e.message.slice(0, 100)));
  await p.goto(`${BASE}/?sharecode=${SC}`, { waitUntil: "networkidle2", timeout: 60000 });
  const r = await p.evaluate(async ([a, p2, ro]) => {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ role: ro, account: a, password: p2 }),
    });
    const j = await res.json();
    if (j.token) localStorage.setItem("ag.token", j.token);
    return j.ok ? "ok" : JSON.stringify(j).slice(0, 120);
  }, [acc, pwd, role]);
  await p.goto(`${BASE}${path}?sharecode=${SC}`, { waitUntil: "networkidle2", timeout: 60000 });
  await new Promise((s) => setTimeout(s, 3000));
  // 关掉右上角通知，免得挡住画面
  await p.evaluate(() => document.querySelectorAll(".el-notification__closeBtn").forEach((x) => x.click()));
  await new Promise((s) => setTimeout(s, 400));
  const st = await p.evaluate(() => ({
    url: location.pathname,
    nodes: document.querySelectorAll(".pt-node").length,
    shape: document.querySelector(".nd-shape polygon") ? "poly" : "circle",
    cards: document.querySelectorAll(".card").length,
  }));
  console.log(role.padEnd(10), r, JSON.stringify(st), errs.length ? "ERR:" + errs[0] : "");
  await p.screenshot({ path: `${OUT}/${role}.png` });
  await p.close();
}
await b.close();
