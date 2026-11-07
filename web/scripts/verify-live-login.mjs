import puppeteer from "puppeteer-core";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "https://academic-guardian-59801.app.workbuddy.host";
const SC = "4RRGYJTS3B";

const b = await puppeteer.launch({
  executablePath: EXE,
  headless: true,
  args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"],
});
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 900 });
await p.goto(`${BASE}/?sharecode=${SC}`, { waitUntil: "networkidle2", timeout: 90000 });
await new Promise((s) => setTimeout(s, 2200));
await p.screenshot({ path: "C:/tmp/live_login_new.png" });

const loginInfo = await p.evaluate(() => ({
  hasStage: !!document.querySelector(".login-stage"),
  stars: document.querySelectorAll(".login-sky .st").length,
  card: !!document.querySelector(".login-card"),
  bg: getComputedStyle(document.querySelector(".login-bg")).backgroundImage.slice(0, 60),
}));
console.log("login:", JSON.stringify(loginInfo));

// 点学生端示例行 → 提交 → 抓开屏
const rows = await p.$$(".hint-row");
await rows[0].click();
await new Promise((s) => setTimeout(s, 250));
await p.click(".submit");
await new Promise((s) => setTimeout(s, 800));
const wipe = await p.evaluate(() => ({
  veiled: !!document.querySelector(".sw"),
  star: !!document.querySelector(".sw-star"),
}));
await p.screenshot({ path: "C:/tmp/live_wipe.png" });
await new Promise((s) => setTimeout(s, 2600));
const after = await p.evaluate(() => ({
  url: location.pathname,
  nodes: document.querySelectorAll(".pt-node").length,
  veil: !!document.querySelector(".sw"),
}));
console.log("wipe:", JSON.stringify(wipe), "after:", JSON.stringify(after));
await p.screenshot({ path: "C:/tmp/live_home.png" });
await b.close();
