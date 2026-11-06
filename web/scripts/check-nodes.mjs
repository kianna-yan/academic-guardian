import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const ACC = {
  student: ["20240067", "0000"],
  counselor: ["2024014589", "1111"],
  admin: ["1234567899", "2222"],
  parent: ["20240067", "3333"],
  teacher: ["2024014501", "4444"],
};
const role = process.argv[2] || "student";
const W = Number(process.argv[3] || 1440);
const H = Number(process.argv[4] || 900);
const [account, password] = ACC[role];
const r = await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role, account, password }) });
const t = (await r.json()).token;
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"] });
const p = await b.newPage();
await p.setViewport({ width: W, height: H });
await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
await p.goto(`${BASE}/${role}`, { waitUntil: "networkidle2" });
await new Promise((s) => setTimeout(s, 2600));
const out = await p.evaluate(() => {
  const nodes = [...document.querySelectorAll(".pt-node")].map((el) => {
    const sh = el.querySelector(".nd-shape").getBoundingClientRect();
    const lb = el.querySelector(".nd-label").getBoundingClientRect();
    const txt = el.querySelector(".nd-txt").getBoundingClientRect();
    const en = el.querySelector(".nd-en").getBoundingClientRect();
    return {
      key: el.dataset.node,
      label: el.querySelector(".nd-label").textContent.trim(),
      shape: [Math.round(sh.x), Math.round(sh.y), Math.round(sh.width), Math.round(sh.height)],
      textOverflow: txt.width > sh.width * 0.82 || en.width > sh.width * 0.8,
      labelW: Math.round(lb.width),
      textW: Math.round(txt.width),
    };
  });
  const overlaps = [];
  for (let i = 0; i < nodes.length; i++)
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i].shape, c = nodes[j].shape;
      const dx = Math.abs(a[0] + a[2] / 2 - (c[0] + c[2] / 2));
      const dy = Math.abs(a[1] + a[3] / 2 - (c[1] + c[3] / 2));
      if (dx < (a[2] + c[2]) / 2 + 2 && dy < (a[3] + c[3]) / 2 + 2 - 12) overlaps.push([nodes[i].label, nodes[j].label, Math.round(dx), Math.round(dy)]);
    }
  return { count: nodes.length, size: nodes[0]?.shape[2], overlaps, overflow: nodes.filter((n) => n.textOverflow).map((n) => n.label), nodes };
});
console.log(JSON.stringify(out, null, 1));
await b.close();
