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
// 把该节点 svg 里的 polygon 轮廓用亮红描出来，并标出顶点
await p.evaluate(() => {
  const poly = document.querySelector('.pt-node[data-node="chat"] polygon');
  const rect = poly.getBoundingClientRect();
  const clone = poly.cloneNode(true);
  clone.setAttribute("fill", "none");
  clone.setAttribute("stroke", "#ff0044");
  clone.setAttribute("stroke-width", "2");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 100 100");
  svg.setAttribute("preserveAspectRatio", "none");
  Object.assign(svg.style, { position: "fixed", left: rect.x + "px", top: rect.y + "px", width: rect.width + "px", height: rect.height + "px", zIndex: 9999, pointerEvents: "none" });
  svg.appendChild(clone);
  document.body.appendChild(svg);
});
await new Promise((s) => setTimeout(s, 300));
const box = await p.evaluate(() => {
  const s = document.querySelector('.pt-node[data-node="chat"] .nd-shape').getBoundingClientRect();
  return { x: s.x - 16, y: s.y - 16, width: s.width + 32, height: s.height + 32 };
});
await p.screenshot({ path: "C:/tmp/overlay.png", clip: box });
await b.close();
