import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const r = await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role: "student", account: "20240067", password: "0000" }) });
const t = (await r.json()).token;
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"] });
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 900 });
await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
await p.goto(`${BASE}/student`, { waitUntil: "networkidle2" });
await new Promise((s) => setTimeout(s, 2500));

// 1. 消息卡滚动
const list = await p.evaluate(() => {
  const l = document.querySelector(".fx-list");
  return { rows: document.querySelectorAll(".fx-row").length, sh: l.scrollHeight, ch: l.clientHeight };
});
// 2. 点第一条 → 打开对话并带上问题
await p.click(".fx-row");
await new Promise((s) => setTimeout(s, 1200));
const sheet = await p.evaluate(() => !!document.querySelector(".ai-sheet"));
const composer = await p.evaluate(() => (document.querySelector(".ai-sheet textarea, .ai-sheet input") || {}).value || "");
await p.keyboard.press("Escape");
await new Promise((s) => setTimeout(s, 600));
// 3. 快捷问题
const chip = await p.$(".chip");
await chip.click();
await new Promise((s) => setTimeout(s, 1200));
const sheet2 = await p.evaluate(() => !!document.querySelector(".ai-sheet"));
const composer2 = await p.evaluate(() => (document.querySelector(".ai-sheet textarea, .ai-sheet input") || {}).value || "");
await p.keyboard.press("Escape");
await new Promise((s) => setTimeout(s, 600));
// 4. 节点跳转
const before = p.url();
const node = await p.$('[data-node="schedule"]');
await node.click();
await new Promise((s) => setTimeout(s, 900));
const after = p.url();
console.log(JSON.stringify({ list, sheet, composer, sheet2, composer2, nav: [before, after] }, null, 1));
await b.close();
