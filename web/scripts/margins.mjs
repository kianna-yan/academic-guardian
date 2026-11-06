import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const ACC = { student: ["20240067","0000"], counselor: ["2024014589","1111"], admin: ["1234567899","2222"], parent: ["20240067","3333"], teacher: ["2024014501","4444"] };
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"] });
for (const role of ["student","counselor","admin","parent","teacher"]) {
  const [account, password] = ACC[role];
  const r = await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role, account, password }) });
  const t = (await r.json()).token;
  const p = await b.newPage();
  await p.setViewport({ width: 1440, height: 900 });
  await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
  await p.goto(`${BASE}/${role}`, { waitUntil: "networkidle2" });
  await new Promise((s) => setTimeout(s, 2200));
  const o = await p.evaluate(() => {
    const c = document.querySelector(".pt-canvas").getBoundingClientRect();
    return [...document.querySelectorAll(".pt-node")].map((el) => {
      const sh = el.querySelector(".nd-shape").getBoundingClientRect();
      return { k: el.dataset.node, right: Math.round(c.right - (sh.x + sh.width)), left: Math.round(sh.x - c.left), bottom: Math.round(c.bottom - (sh.y + sh.height)) };
    });
  });
  console.log(role, JSON.stringify(o));
  await p.close();
}
await b.close();
