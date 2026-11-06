import puppeteer from "puppeteer-core";
import fs from "node:fs";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8620";
const OUT = "C:/Users/lenovo/WorkBuddy/2026-11-03-16-18-31/_v8/shots_portal2";
fs.mkdirSync(OUT, { recursive: true });

async function token(role, account, password) {
  const r = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ role, account, password }),
  });
  return (await r.json()).token;
}

const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox"] });

const jobs = [
  ["student", "20240023", "0000", "/student/overview", "s_overview"],
  ["student", "20240023", "0000", "/student/grade", "s_grade"],
  ["student", "20240023", "0000", "/student/records", "s_records"],
  ["admin", "1234567899", "2222", "/admin/board", "admin_board"],
  ["counselor", "2024014589", "1111", "/counselor/forest", "co_forest"],
  ["parent", "20240067", "3333", "/parent/overview", "pa_overview"],
];

for (const [role, acc, pwd, path, name] of jobs) {
  const t = await token(role, acc, pwd);
  const p = await b.newPage();
  await p.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1.4 });
  await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
  await p.goto(BASE + path, { waitUntil: "networkidle2" });
  await new Promise((s) => setTimeout(s, 2600));
  await p.screenshot({ path: `${OUT}/${name}.png` });
  console.log("shot", name);
  await p.close();
}

await b.close();
