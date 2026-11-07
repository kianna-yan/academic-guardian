import puppeteer from "puppeteer-core";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";

const b = await puppeteer.launch({
  executablePath: EXE,
  headless: true,
  args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"],
});

// ---- 桌面：登录流程 ----
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 900 });
await p.goto(`${BASE}/`, { waitUntil: "networkidle2" });
await new Promise((s) => setTimeout(s, 1800));

// 点「端口示例」里辅导员那一行，检查是否自动填入
const rows = await p.$$(".hint-row");
await rows[1].click();
await new Promise((s) => setTimeout(s, 300));
const filled = await p.evaluate(() => {
  const acc = document.querySelector(".field input");
  const pwd = document.querySelector(".pwd input");
  const active = document.querySelector(".tab.active")?.textContent?.trim();
  return { acc: acc?.value, pwd: pwd?.value, active };
});
console.log("fill:", JSON.stringify(filled));

// 换成学生端再登录
await rows[0].click();
await new Promise((s) => setTimeout(s, 300));
await p.click(".submit");
await new Promise((s) => setTimeout(s, 900));
const wipeOn = await p.evaluate(() => !!document.querySelector(".sw"));
await p.screenshot({ path: "C:/tmp/b_after_login_wipe.png" });
await new Promise((s) => setTimeout(s, 2600));
const url = p.url();
const homeOk = await p.evaluate(() => ({
  nodes: document.querySelectorAll(".pt-node").length,
  veil: !!document.querySelector(".sw"),
  mainHome: document.querySelector(".main")?.classList.contains("main-home"),
}));
console.log("after login:", url, "wipePlaying:", wipeOn, JSON.stringify(homeOk));

// 点一个节点进内页：不应播开屏
await p.goto(`${BASE}/student`, { waitUntil: "networkidle2" });
await new Promise((s) => setTimeout(s, 2800));
const node = await p.$('.pt-node[data-node="resources"]');
if (node) await node.click();
await new Promise((s) => setTimeout(s, 400));
const innerWipe = await p.evaluate(() => ({ veil: !!document.querySelector(".sw"), url: location.pathname }));
console.log("inner page:", JSON.stringify(innerWipe));

// ---- 手机：登录页 ----
const m = await b.newPage();
await m.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
await m.evaluateOnNewDocument(() => localStorage.removeItem("ag.token"));
await m.goto(`${BASE}/`, { waitUntil: "networkidle2" });
await new Promise((s) => setTimeout(s, 1600));
await m.screenshot({ path: "C:/tmp/b_login_mobile.png" });
const mInfo = await m.evaluate(() => {
  const card = document.querySelector(".login-card").getBoundingClientRect();
  return { cardW: Math.round(card.width), scrollW: document.documentElement.scrollWidth, vw: window.innerWidth };
});
console.log("mobile:", JSON.stringify(mInfo));
await b.close();
