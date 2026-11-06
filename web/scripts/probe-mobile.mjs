import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = process.env.AG_BASE || "http://127.0.0.1:8621";
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox"] });
const p = await b.newPage();
await p.setViewport({ width: 390, height: 844 });
await p.goto(BASE + "/", { waitUntil: "networkidle2" });
await p.evaluate(async () => {
  const r = await fetch("/api/auth/login", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role: "student", account: "20240023", password: "0000" }) });
  const j = await r.json(); localStorage.setItem("ag.token", j.token);
});
await p.goto(BASE + "/student", { waitUntil: "networkidle2" });
await new Promise((s) => setTimeout(s, 2500));
const r = await p.evaluate(() => {
  const pt = document.querySelector(".portal");
  const f = document.querySelector(".pt-field");
  const d = document.querySelector(".pt-dock");
  const cs = getComputedStyle(pt), cf = getComputedStyle(f), cd = getComputedStyle(d);
  return {
    portal: { h: Math.round(pt.getBoundingClientRect().height), pos: cs.position, height: cs.height, padB: cs.paddingBottom },
    field: { pos: cf.position, display: cf.display, h: Math.round(f.getBoundingClientRect().height), top: Math.round(f.getBoundingClientRect().top) },
    dock: { pos: cd.position, bottom: cd.bottom, top: Math.round(d.getBoundingClientRect().top), h: Math.round(d.getBoundingClientRect().height) },
    portalBottom: Math.round(pt.getBoundingClientRect().bottom),
    viewH: window.innerHeight,
  };
});
console.log(JSON.stringify(r, null, 1));
await b.close();
