import puppeteer from "puppeteer-core";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const role = process.argv[2] || "student";

const ACC = {
  student: ["20240067", "0000"],
  counselor: ["2024014589", "1111"],
  admin: ["1234567899", "2222"],
  teacher: ["2024014501", "4444"],
  parent: ["20240067", "3333"],
};

const r = await fetch(`${BASE}/api/auth/login`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ role, account: ACC[role][0], password: ACC[role][1] }),
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
// 统计化幕期间的真实帧率
await p.evaluateOnNewDocument(() => {
  window.__fps = { t: [], start: 0 };
});

await p.goto(`${BASE}/${role}`, { waitUntil: "domcontentloaded" });

// 化幕起点 = 320 + 1000 + 120 = 1440ms
const frames = [1400, 1520, 1650, 1800, 1950, 2100, 2280, 2450, 2600, 2800];
let last = 0;
for (const t of frames) {
  await new Promise((s) => setTimeout(s, t - last));
  last = t;
  await p.screenshot({ path: `C:/tmp/melt_${t}.png` });
}
await new Promise((s) => setTimeout(s, 900));
await p.screenshot({ path: "C:/tmp/melt_after.png" });
console.log("frames ok");
await b.close();
