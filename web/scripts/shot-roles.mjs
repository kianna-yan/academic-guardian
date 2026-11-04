import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await puppeteer.launch({ executablePath: EXE, headless: true,
  args: ["--disable-gpu", "--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"] });
const page = await browser.newPage();
await page.setViewport({ width: 1084, height: 700 });
async function login(role, acc, pwd, path) {
  const r = await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role, account: acc, password: pwd }) });
  const j = await r.json();
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle2" });
  await page.evaluate((t) => { localStorage.clear(); localStorage.setItem("ag.token", t); }, j.token);
  await page.goto(`${BASE}${path}`, { waitUntil: "networkidle2" });
  await sleep(2200);
}
await login("counselor", "2024014589", "1111", "/counselor#forest");
await page.screenshot({ path: "shots_round5/9-counselor-forest.png" });
await login("parent", "20240063", "3333", "/parent#overview");
await page.screenshot({ path: "shots_round5/10-parent.png" });
await browser.close();
console.log("done");
