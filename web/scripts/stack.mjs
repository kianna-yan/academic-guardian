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
const out = await p.evaluate(() => {
  const shape = document.querySelector('.pt-node[data-node="chat"] .nd-shape');
  const r = shape.getBoundingClientRect();
  // 取图形左上"肩部"一点（外扩一圈的位置），看是谁在画
  const x = r.x + r.width * 0.18;
  const y = r.y + r.height * 0.22;
  const stack = document.elementsFromPoint(x, y).map((e) => `${e.tagName}.${e.className}`.slice(0, 60));
  const styles = [...document.styleSheets].flatMap((s) => { try { return [...s.cssRules].map((c) => c.cssText); } catch { return []; } })
    .filter((t) => /\.pt-node\.main|\.nd-shape/.test(t)).slice(0, 24);
  const cs = getComputedStyle(shape);
  return { stack, styles, filter: cs.filter, background: cs.background.slice(0, 80), boxShadow: cs.boxShadow, before: getComputedStyle(shape, "::before").cssText };
});
console.log(JSON.stringify(out, null, 1));
await b.close();
