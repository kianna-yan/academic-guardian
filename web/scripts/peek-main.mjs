import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const ACC = { student: ["20240067","0000"], counselor: ["2024014589","1111"], admin: ["1234567899","2222"], teacher: ["2024014501","4444"], parent: ["20240067","3333"] };
const roles = ["student","counselor","admin","teacher","parent"];
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"] });
for (const role of roles) {
  const [account, password] = ACC[role];
  const r = await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role, account, password }) });
  const t = (await r.json()).token;
  const p = await b.newPage();
  await p.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });
  await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
  await p.goto(`${BASE}/${role}`, { waitUntil: "networkidle2" });
  await new Promise((s) => setTimeout(s, 2400));
  const info = await p.evaluate(() => {
    const el = document.querySelector(".pt-node.main");
    const poly = el.querySelector("polygon");
    return { key: el.dataset.node, sides: poly ? poly.getAttribute("points").trim().split(/\s+/).length : 0 };
  });
  const el = await p.$(".pt-node.main");
  await el.screenshot({ path: `C:/tmp/main_${role}.png` });
  console.log(role, JSON.stringify(info));
  await p.close();
}
await b.close();
