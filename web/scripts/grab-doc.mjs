import puppeteer from "puppeteer-core";
import fs from "node:fs";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const [url, out] = process.argv.slice(2);
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox"] });
const p = await b.newPage();
await p.setViewport({ width: 1600, height: 1000, deviceScaleFactor: 2 });
p.on("response", async (r) => {
  const ct = r.headers()["content-type"] || "";
  if (ct.startsWith("image/")) console.log("IMG", ct, r.url().slice(0, 220));
});
await p.goto(url, { waitUntil: "networkidle2", timeout: 60000 });
await new Promise((s) => setTimeout(s, 6000));
const info = await p.evaluate(() => ({ t: document.title, txt: document.body.innerText.slice(0, 300) }));
console.log("TITLE:", info.t);
console.log("TEXT:", info.txt.replace(/\n/g, " | "));
await p.screenshot({ path: out, fullPage: false });
await b.close();
