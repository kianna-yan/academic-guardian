import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const URL = process.argv[2];
const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox"] });
const p = await b.newPage();
await p.setViewport({ width: 430, height: 932 });
p.on("request", (r) => { const u = r.url(); if (!u.includes("/p/63zY")) console.log("REQ", r.method(), u.slice(0, 180)); });
p.on("response", async (r) => {
  const u = r.url();
  const ct = r.headers()["content-type"] || "";
  if (ct.includes("json")) {
    try { const t = await r.text(); console.log("JSON", u.slice(0, 120), "=>", t.slice(0, 500)); } catch (e) {}
  }
});
await p.goto(URL, { waitUntil: "networkidle2", timeout: 60000 });
await new Promise((s) => setTimeout(s, 6000));
const html = await p.content();
console.log("--- HTML 长度:", html.length);
console.log(html.slice(0, 1500));
await b.close();
