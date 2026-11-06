import puppeteer from "puppeteer-core";
import fs from "node:fs";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8620";
const OUT = "C:/Users/lenovo/WorkBuddy/2026-11-03-16-18-31/_v8/shots_portal";
fs.mkdirSync(OUT, { recursive: true });

async function token(role, account, password) {
  const r = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ role, account, password }),
  });
  return (await r.json()).token;
}

const ACC = {
  student: ["20240023", "0000", "/student"],
  counselor: ["2024014589", "1111", "/counselor"],
  admin: ["1234567899", "2222", "/admin"],
  teacher: ["2024014501", "4444", "/teacher"],
  parent: ["20240067", "3333", "/parent"],
};

const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox"] });

for (const [role, [acc, pwd, path]] of Object.entries(ACC)) {
  const t = await token(role, acc, pwd);
  if (!t) { console.log("SKIP", role); continue; }
  const p = await b.newPage();
  await p.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1.5 });
  await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
  await p.goto(BASE + path, { waitUntil: "networkidle2" });
  await new Promise((s) => setTimeout(s, 2600));
  await p.screenshot({ path: `${OUT}/${role}_portal.png` });
  console.log("shot", role);
  await p.close();
}

// 学生端：展开 AI 抽屉
{
  const t = await token("student", "20240023", "0000");
  const p = await b.newPage();
  await p.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1.5 });
  await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
  await p.goto(BASE + "/student", { waitUntil: "networkidle2" });
  await new Promise((s) => setTimeout(s, 2600));
  await p.click('[data-test="ai-dock"]');
  await new Promise((s) => setTimeout(s, 900));
  await p.screenshot({ path: `${OUT}/student_ai_sheet.png` });
  console.log("shot student_ai_sheet");
  await p.close();
}

await b.close();
