/** 线上验收：直接打分享链接，确认发布出去的版本是修复后的。 */
import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const LINK = process.env.LINK;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--disable-gpu", "--no-sandbox"] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 900 });
page.on("pageerror", (e) => console.log("PAGEERROR:", e.message));
await page.goto(LINK, { waitUntil: "networkidle2", timeout: 60000 });
await sleep(1500);
await page.evaluate(() => localStorage.clear());
await page.reload({ waitUntil: "networkidle2" });
await sleep(1500);
console.log("LOGIN:", JSON.stringify(await page.evaluate(() => ({
  path: location.pathname,
  tabs: document.querySelectorAll(".tab").length,
  tabRows: new Set([...document.querySelectorAll(".tab")].map((e) => Math.round(e.getBoundingClientRect().top))).size,
  rows: [...document.querySelectorAll(".hint-row")].map((e) => e.innerText.replace(/\s+/g, " ").trim()),
}))));
await page.screenshot({ path: "shots_fix/live-01-login.png" });
const rows = await page.$$(".hint-row");
await rows[1].click();
await sleep(200);
await page.click(".submit");
await page.waitForFunction(() => !location.pathname.includes("login"), { timeout: 30000 });
await sleep(2500);
console.log("COUNSELOR:", JSON.stringify(await page.evaluate(() => ({
  path: location.pathname,
  greet: (document.querySelector(".chat-stream .bubble")?.innerText || "").slice(0, 20),
  chips: [...document.querySelectorAll(".ch-suggest .chip")].map((e) => e.innerText),
  nav: [...document.querySelectorAll(".mod-item")].map((e) => e.innerText.replace(/\s+/g, " ").trim()),
})), null, 1));
await page.screenshot({ path: "shots_fix/live-02-counselor.png" });
await page.evaluate(() => [...document.querySelectorAll(".mod-item")].find((e) => e.innerText.includes("风险名单"))?.click());
await sleep(1300);
console.log("NAV:", JSON.stringify(await page.evaluate(() => ({ hash: location.hash, dash: !!document.querySelector(".dash-nav") }))));
await page.screenshot({ path: "shots_fix/live-03-roster.png" });
await browser.close();
