import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const role = "teacher";
const r = await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role, account: "2024014501", password: "4444" }) });
const t = (await r.json()).token;
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"] });
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 980 });
await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
await p.goto(`${BASE}/${role}`, { waitUntil: "networkidle2" });
await new Promise((s) => setTimeout(s, 2500));
console.log(await p.evaluate(() => {
  const n = document.querySelector(".pt-node");
  const sh = document.querySelector(".nd-shape");
  return { styleNd: document.querySelector(".portal").getAttribute("style"), w: sh.getBoundingClientRect().width, cssNd: getComputedStyle(document.querySelector(".portal")).getPropertyValue("--nd") };
}));
await b.close();
