import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8621";
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox"] });
const p = await b.newPage();
await p.setViewport({ width: 390, height: 844 });
await p.goto(BASE + "/", { waitUntil: "networkidle2" });
await p.evaluate(async () => {
  const r = await fetch("/api/auth/login", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role: "student", account: "20240023", password: "0000" }) });
  const j = await r.json(); localStorage.setItem("ag.token", j.token);
});
await p.goto(BASE + "/student", { waitUntil: "networkidle2" });
await new Promise((s) => setTimeout(s, 2200));
const out = await p.evaluate(() => {
  const res = [];
  let el = document.querySelector(".portal");
  while (el && res.length < 5) {
    const c = getComputedStyle(el);
    res.push({
      cls: el.className.toString().slice(0, 40),
      display: c.display, flex: c.flex, height: c.height, alignSelf: c.alignSelf,
      overflow: c.overflow, box: Math.round(el.getBoundingClientRect().height),
    });
    el = el.parentElement;
  }
  return res;
});
console.log(JSON.stringify(out, null, 1));
await b.close();
