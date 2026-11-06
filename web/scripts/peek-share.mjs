import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const URL = process.argv[2];
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox"] });
const p = await b.newPage();
await p.setViewport({ width: 430, height: 932, deviceScaleFactor: 2 });
p.on("console", (m) => { if (m.type() === "error") console.log("CERR", m.text().slice(0, 120)); });
await p.goto(URL, { waitUntil: "networkidle2", timeout: 60000 });
await new Promise((s) => setTimeout(s, 5000));
const info = await p.evaluate(() => ({
  title: document.title,
  text: document.body.innerText.slice(0, 3000),
  imgs: [...document.querySelectorAll("img")].map((i) => ({ src: i.src, w: i.naturalWidth, h: i.naturalHeight })),
  len: document.body.innerText.length,
}));
console.log("TITLE:", info.title, "| textLen:", info.len);
console.log("--- TEXT ---");
console.log(info.text);
console.log("--- IMGS ---");
for (const i of info.imgs) console.log(i.w + "x" + i.h, i.src.slice(0, 200));
await p.screenshot({ path: "C:/Users/lenovo/WorkBuddy/2026-11-03-16-18-31/_v8/share_shot.png", fullPage: true });
await b.close();
