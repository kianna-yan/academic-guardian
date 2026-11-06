import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const r = await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role: "student", account: "20240067", password: "0000" }) });
const t = (await r.json()).token;
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"] });
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 900 });
await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
await p.goto(`${BASE}/student`, { waitUntil: "networkidle2" });
await new Promise((s) => setTimeout(s, 2600));
const out = await p.evaluate(() => {
  const all = [...document.querySelectorAll('.pt-node[data-node="chat"]')];
  return all.map((el) => {
    const poly = el.querySelector("polygon");
    const r = el.getBoundingClientRect();
    return { cls: el.className, pts: poly ? poly.getAttribute("points") : null, box: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)], vis: getComputedStyle(el).display };
  });
});
console.log(JSON.stringify(out, null, 1));
console.log("scripts:", await p.evaluate(() => [...document.querySelectorAll("script[src]")].map((s) => s.src).join(" | ")));
await b.close();
