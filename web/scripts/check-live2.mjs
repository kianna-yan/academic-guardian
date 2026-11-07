import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const URL0 = "https://academic-guardian-59801.app.workbuddy.host/?sharecode=4RRGYJTS3B";
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"] });
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 900 });
await p.goto(URL0, { waitUntil: "networkidle2", timeout: 60000 });
await new Promise((s) => setTimeout(s, 2500));
const out = await p.evaluate(async () => {
  const r = await fetch("/api/auth/login", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role: "student", account: "20240067", password: "0000" }) });
  const j = await r.json().catch(() => null);
  return { status: r.status, hasToken: !!(j && j.token), title: document.title, body: document.body.innerText.slice(0, 80) };
});
console.log(JSON.stringify(out));
await p.screenshot({ path: "C:/tmp/live_login.png" });
await b.close();
