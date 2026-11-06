import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8620";
const OUT = "C:/Users/lenovo/WorkBuddy/2026-11-03-16-18-31/_v8/shots_portal";
const pages = [
  { role: "student", account: "20240067", password: "0000", paths: ["/student/schedule", "/student/checkin", "/student/track", "/student/tree"] },
  { role: "counselor", account: "2024014589", password: "1111", paths: ["/messages"] },
];
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox"] });
for (const a of pages) {
  const r = await fetch(`${BASE}/api/auth/login`, {method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({role:a.role,account:a.account,password:a.password})});
  const { token } = await r.json();
  for (const path of a.paths) {
    const p = await b.newPage();
    await p.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1.4 });
    await p.evaluateOnNewDocument((t) => localStorage.setItem("ag.token", t), token);
    await p.goto(BASE + path, { waitUntil: "networkidle2" });
    await new Promise((s) => setTimeout(s, 3000));
    const name = path.replace(/\//g, "_").replace(/^_/, "");
    await p.screenshot({ path: `${OUT}/${name}.png` });
    console.log("shot", name);
    await p.close();
  }
}
await b.close();
