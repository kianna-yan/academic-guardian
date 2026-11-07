import puppeteer from "puppeteer-core";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";

const r = await fetch(`${BASE}/api/auth/login`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ role: "student", account: "20240067", password: "0000" }),
});
const token = (await r.json()).token;

const b = await puppeteer.launch({
  executablePath: EXE,
  headless: true,
  args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"],
});
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), token);
await p.evaluateOnNewDocument(() => {
  window.__t0 = performance.now();
  window.__fps = 0;
  const tick = () => {
    window.__fps++;
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
});

await p.goto(`${BASE}/student`, { waitUntil: "domcontentloaded" });

const probe = () =>
  p.evaluate(() => {
    const pane = document.querySelector(".sw-pane-a");
    const m = pane ? getComputedStyle(pane).maskImage : "none";
    const f = m.match(/rgba\(0, 0, 0, 0\)\s+([\d.]+)%/g);
    const lastTransparent = f && f.length > 1 ? parseFloat(f[f.length - 1].match(/([\d.]+)%/)[1]) : null;
    return {
      t: Math.round(performance.now() - window.__t0),
      frames: window.__fps,
      veilNum: lastTransparent,
      mask: m.slice(0, 90),
      open: !!document.querySelector(".sw-open"),
    };
  });

for (let i = 0; i < 14; i++) {
  await new Promise((s) => setTimeout(s, 150));
  const info = await probe();
  console.log(JSON.stringify(info));
}
await b.close();
