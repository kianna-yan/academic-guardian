// 真浏览器快速探测线上状态（走 WorkBuddy 客户端网络层，与右侧面板同路径）
import puppeteer from "puppeteer-core";
import { existsSync } from "node:fs";

const EXES = [
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
];
const EXE = EXES.find((p) => existsSync(p));
const URL = "https://academic-guardian.app.workbuddy.host/api/health?sharecode=XNKLXQ7EPB";

const browser = await puppeteer.launch({
  executablePath: EXE,
  headless: true,
  args: ["--disable-gpu", "--no-sandbox", "--font-render-hinting=none"],
});
try {
  const page = await browser.newPage();
  const resp = await page.goto(URL, { waitUntil: "domcontentloaded", timeout: 20000 }).catch((e) => null);
  if (resp) {
    console.log("HTTP:", resp.status());
    const body = await page.evaluate(() => document.body.innerText.slice(0, 120));
    console.log("body:", body.replace(/\n/g, " "));
  } else {
    console.log("导航失败（域名解析或连接失败）");
  }
} finally {
  await browser.close();
}
