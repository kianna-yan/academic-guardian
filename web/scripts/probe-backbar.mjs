import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8620";
async function token(role, account, password) {
  const r = await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role, account, password }) });
  return (await r.json()).token;
}
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox"] });
const cases = [
  ["student", "20240023", "0000", "/student/schedule"],
  ["student", "20240023", "0000", "/student/tree"],
  ["student", "20240023", "0000", "/student/resources"],
  ["parent", "20240067", "3333", "/messages"],
  ["teacher", "2024014501", "4444", "/teacher/resources"],
  ["admin", "1234567899", "2222", "/admin/curriculum"],
];
for (const [role, acc, pwd, path] of cases) {
  const t = await token(role, acc, pwd);
  const p = await b.newPage();
  await p.setViewport({ width: 1440, height: 900 });
  await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
  await p.goto(BASE + path, { waitUntil: "networkidle2" });
  await new Promise((s) => setTimeout(s, 2000));
  const r = await p.evaluate(() => ({
    back: !!document.querySelector('[data-test="back-home"]'),
    ai: !!document.querySelector('[data-test="back-ai"]'),
    title: document.querySelector(".back-title")?.textContent?.trim(),
    sb: !!document.querySelector(".sidebar"),
    txt: document.querySelector(".view")?.innerText?.slice(0, 30).replace(/\s+/g, " "),
  }));
  console.log(path.padEnd(24), JSON.stringify(r));
  await p.close();
}
await b.close();
