import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const r = await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role: "student", account: "20240067", password: "0000" }) });
const t = (await r.json()).token;
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"] });
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });
await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
await p.goto(`${BASE}/student`, { waitUntil: "networkidle2" });
await new Promise((s) => setTimeout(s, 2600));
const shot = async (name) => {
  const box = await p.evaluate(() => {
    const s = document.querySelector('.pt-node[data-node="chat"] .nd-shape').getBoundingClientRect();
    return { x: s.x - 10, y: s.y - 10, width: s.width + 20, height: s.height + 20 };
  });
  await p.screenshot({ path: `C:/tmp/${name}.png`, clip: box });
};
await shot("join_round");
await p.evaluate(() => document.querySelectorAll(".pt-node.main polygon").forEach((x) => (x.style.strokeLinejoin = "miter")));
await new Promise((s) => setTimeout(s, 300));
await shot("join_miter");
// 量一下顶部平边宽度比例
const ratio = await p.evaluate(() => {
  const el = document.querySelector('.pt-node[data-node="chat"] .nd-shape');
  const r = el.getBoundingClientRect();
  return { w: Math.round(r.width), h: Math.round(r.height) };
});
console.log(JSON.stringify(ratio));
await b.close();
