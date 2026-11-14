// 语音条「问 AI ↔ 家校沟通」外观对拍：录一段真的语音发出去，再把两边的语音条裁出来并排放。
import puppeteer from "puppeteer-core";
import fs from "node:fs";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8622";
const OUT = "shots_voice";
fs.mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function token(role, account, password) {
  const r = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ role, account, password }),
  });
  const j = await r.json();
  if (!j.token) throw new Error("登录失败 " + JSON.stringify(j));
  return j.token;
}

const browser = await puppeteer.launch({
  executablePath: EXE,
  headless: true,
  args: [
    "--disable-gpu",
    "--no-sandbox",
    "--proxy-server=direct://",
    "--proxy-bypass-list=*",
    "--use-fake-device-for-media-stream",
    "--use-fake-ui-for-media-stream",
    "--autoplay-policy=no-user-gesture-required",
  ],
});

async function newPage(tk, w = 1440, h = 900) {
  const page = await browser.newPage();
  await page.setViewport({ width: w, height: h, deviceScaleFactor: 2 });
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
  await page.evaluate((t) => localStorage.setItem("ag.token", t), tk);
  await page.reload({ waitUntil: "domcontentloaded" });
  await sleep(1600);
  await page.evaluate(() => {
    document.querySelectorAll(".v11-veil,.star-wipe,.pre-veil").forEach((n) => n.remove());
    document.documentElement.classList.remove("v11-veil");
  });
  const cont = await page.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((n) => n.textContent.trim() === "继续进入");
    if (!b) return false;
    b.click();
    return true;
  });
  if (cont) await sleep(2600);
  return page;
}

/** 按住麦克风 1.4 秒再松开 */
async function record(page, micSel) {
  const box = await page.$eval(micSel, (el) => {
    const r = el.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
  });
  await page.mouse.move(box.x, box.y);
  await page.mouse.down();
  await sleep(1400);
  await page.mouse.up();
  await sleep(2600);
}

/* ---------- 问 AI ---------- */
const tk = await token("student", "20240221", "0000");
const page = await newPage(tk);
const hit = await page.evaluate(() => {
  const n = document.querySelector('.pt-node[data-node="chat"]');
  if (!n) return false;
  n.click();
  return true;
});
console.log("进入学业对话:", hit);
await sleep(3200);
await record(page, ".ch-mic");
const sendable = await page.evaluate(() => {
  const b = document.querySelector('[data-test="chat-send"]');
  return b ? !b.disabled : false;
});
if (sendable) await page.evaluate(() => document.querySelector('[data-test="chat-send"]')?.click());
await sleep(2600);

const ai = await page.evaluate(() => {
  const b = [...document.querySelectorAll(".chat-stream .msg.user .bubble")].filter((n) =>
    n.querySelector(".voice-clip"),
  ).pop();
  if (!b) return null;
  const clip = b.querySelector(".voice-clip");
  const cs = getComputedStyle(b);
  const cs2 = getComputedStyle(clip);
  const r = b.getBoundingClientRect();
  const r2 = clip.getBoundingClientRect();
  return {
    bubbleBg: cs.backgroundColor,
    bubbleBorder: `${cs.borderTopWidth} ${cs.borderTopColor}`,
    bubbleRadius: cs.borderTopLeftRadius,
    bubblePad: cs.padding,
    bubbleRect: [Math.round(r.width), Math.round(r.height)],
    clipBg: cs2.backgroundColor,
    clipBorder: `${cs2.borderTopWidth} ${cs2.borderTopColor}`,
    clipRadius: cs2.borderTopLeftRadius,
    clipRect: [Math.round(r2.width), Math.round(r2.height)],
    hasTranscript: !!b.querySelector(".bm-said-out"),
    classes: b.className,
  };
});
console.log("问AI 语音气泡:", JSON.stringify(ai, null, 1));
await page.screenshot({ path: `${OUT}/ai-page.png` });
const el = await page.$(".chat-stream .msg.user .bubble:has(.voice-clip)");
if (el) await el.screenshot({ path: `${OUT}/ai-clip.png` });
await page.close();

/* ---------- 家校沟通（家长端，给对方发一条语音） ---------- */
const tk2 = await token("parent", "20240067", "3333");
const page2 = await newPage(tk2);
const intoMsg = await page2.evaluate(() => {
  const n = document.querySelector('.pt-node[data-node="messages"]');
  if (!n) return false;
  n.click();
  return true;
});
console.log("进入家校沟通:", intoMsg, page2.url());
await sleep(3000);
const conv = await page2.evaluate(() => {
  const it = document.querySelector(".thread-row");
  if (!it) return false;
  it.click();
  return true;
});
await sleep(2000);
await record(page2, '[data-test="msg-voice"]');
// 把转写出来的文字清空，只留语音，跟「问 AI」那边保持同一种情形
await page2.evaluate(() => {
  const ta = document.querySelector(".ci-row textarea");
  if (!ta) return;
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set;
  setter.call(ta, "");
  ta.dispatchEvent(new Event("input", { bubbles: true }));
});
await sleep(400);
const send2 = await page2.evaluate(() => {
  const b = [...document.querySelectorAll("button")].find((n) => n.textContent.trim() === "发送");
  if (!b || b.disabled) return false;
  b.click();
  return true;
});
console.log("家校沟通已发送:", send2);
await sleep(2600);

const msg = await page2.evaluate(() => {
  const b = [...document.querySelectorAll(".bubble")].filter((n) => n.querySelector(".voice-clip")).pop();
  if (!b) return null;
  const clip = b.querySelector(".voice-clip");
  const cs = getComputedStyle(b);
  const cs2 = getComputedStyle(clip);
  const r = b.getBoundingClientRect();
  const r2 = clip.getBoundingClientRect();
  return {
    bubbleBg: cs.backgroundColor,
    bubbleBorder: `${cs.borderTopWidth} ${cs.borderTopColor}`,
    bubbleRadius: cs.borderTopLeftRadius,
    bubblePad: cs.padding,
    bubbleRect: [Math.round(r.width), Math.round(r.height)],
    clipBg: cs2.backgroundColor,
    clipBorder: `${cs2.borderTopWidth} ${cs2.borderTopColor}`,
    clipRadius: cs2.borderTopLeftRadius,
    clipRect: [Math.round(r2.width), Math.round(r2.height)],
    classes: b.className,
  };
});
console.log("家校沟通 语音气泡:", JSON.stringify(msg, null, 1));
await page2.screenshot({ path: `${OUT}/msg-page.png` });
await browser.close();
