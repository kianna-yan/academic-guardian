import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8631";
const r = await fetch(`${BASE}/api/auth/login`, {method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({role:"student",account:"20240023",password:"0000"})});
const t = (await r.json()).token;
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args:["--no-sandbox"] });
const p = await b.newPage();
await p.setViewport({width:1440,height:900});
await p.evaluateOnNewDocument((x)=>localStorage.setItem("ag.token",x), t);
await p.goto(BASE+"/student",{waitUntil:"networkidle2"});
await new Promise(s=>setTimeout(s,2200));
const keys = ["schedule","checkin","track","records"];
for (const k of keys) {
  const el = await p.$(`[data-node="${k}"]`);
  if (!el) { console.log(k, "missing"); continue; }
  await el.click();
  await new Promise(s=>setTimeout(s,700));
  console.log(k, "->", new URL(p.url()).pathname);
  await p.goBack({waitUntil:"networkidle2"});
  await new Promise(s=>setTimeout(s,900));
}
// AI 节点
const ai = await p.$('[data-node="chat"]');
await ai.click();
await new Promise(s=>setTimeout(s,900));
const sheet = await p.$('.ai-sheet');
console.log("ai sheet open", !!sheet);
await b.close();
