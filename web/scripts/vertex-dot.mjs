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
await p.mouse.move(3, 3);
await new Promise((s) => setTimeout(s, 2600));
const dots = await p.evaluate(() => {
  const poly = document.querySelector('.pt-node[data-node="chat"] polygon');
  const ctm = poly.getScreenCTM();
  const pts = [...poly.points].map((pt) => {
    const x = ctm.a * pt.x + ctm.c * pt.y + ctm.e;
    const y = ctm.b * pt.x + ctm.d * pt.y + ctm.f;
    const d = document.createElement("div");
    Object.assign(d.style, { position: "fixed", left: x - 3 + "px", top: y - 3 + "px", width: "6px", height: "6px", borderRadius: "50%", background: "#ff0044", zIndex: 99999, pointerEvents: "none" });
    document.body.appendChild(d);
    return [Math.round(x), Math.round(y)];
  });
  const bb = poly.getBoundingClientRect();
  return { pts, bb: [Math.round(bb.x), Math.round(bb.y), Math.round(bb.width), Math.round(bb.height)], attr: poly.getAttribute("points") };
});
console.log(JSON.stringify(dots));
const box = await p.evaluate(() => {
  const s = document.querySelector('.pt-node[data-node="chat"] .nd-shape').getBoundingClientRect();
  return { x: s.x - 18, y: s.y - 18, width: s.width + 36, height: s.height + 36 };
});
await p.screenshot({ path: "C:/tmp/vertex.png", clip: box });
await b.close();
