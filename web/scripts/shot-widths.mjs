import puppeteer from "puppeteer-core";
import fs from "node:fs";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = process.env.AG_BASE || "http://127.0.0.1:8631";
const OUT = "C:/Users/lenovo/WorkBuddy/2026-11-03-16-18-31/_v8/shots_v4";
fs.mkdirSync(OUT, { recursive: true });
const r = await fetch(`${BASE}/api/auth/login`, {method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({role:"student",account:"20240023",password:"0000"})});
const t = (await r.json()).token;
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args:["--no-sandbox"] });
for (const w of [1280, 1024, 820]) {
  const p = await b.newPage();
  await p.setViewport({ width: w, height: 860, deviceScaleFactor: 1.4 });
  await p.evaluateOnNewDocument((x)=>localStorage.setItem("ag.token",x), t);
  await p.goto(BASE+"/student",{waitUntil:"networkidle2"});
  await new Promise(s=>setTimeout(s,2400));
  await p.screenshot({ path: `${OUT}/w${w}.png` });
  const over = await p.evaluate(() => ({ sw: document.body.scrollWidth, cw: document.documentElement.clientWidth }));
  console.log(w, JSON.stringify(over));
  await p.close();
}
await b.close();
