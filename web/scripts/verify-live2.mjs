import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const LINK = "https://academic-guardian-56914.app.workbuddy.host/?sharecode=G4NKZPCZAO";
const BASE = LINK.split("?")[0];
const CODE = "G4NKZPCZAO";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--disable-gpu", "--no-sandbox"] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 880 });
page.on("pageerror", (e) => console.log("PAGEERROR:", e.message));

async function login(role, account, password) {
  // 线上用 sharecode 走网关，登录接口也带 sharecode
  const r = await fetch(`${BASE}/api/auth/login?sharecode=${CODE}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role, account, password }),
  });
  const j = await r.json();
  if (!j.ok) throw new Error(`login failed: ${JSON.stringify(j)}`);
  await page.goto(`${BASE}/login?sharecode=${CODE}`, { waitUntil: "networkidle2" });
  await page.evaluate((t) => { localStorage.clear(); localStorage.setItem("ag.token", t); }, j.token);
  const home = { student: "/student", counselor: "/counselor", admin: "/admin", parent: "/parent", teacher: "/teacher" }[role];
  await page.goto(`${BASE}${home}?sharecode=${CODE}`, { waitUntil: "networkidle2" });
  await sleep(2000);
}

// === 智慧森林 ===
await login("counselor", "2024014589", "1111");
await page.evaluate(() => [...document.querySelectorAll(".mod-item")].find((e) => e.innerText.includes("智慧森林"))?.click());
await sleep(1500);
const forest = await page.evaluate(() => ({
  cards: document.querySelectorAll(".forest-card").length,
  trees: document.querySelectorAll(".tree").length,
  hash: location.hash,
}));
console.log("LIVE forest:", JSON.stringify(forest));

// === 家长端家校沟通 + 辅导员电话 ===
await login("parent", "20240067", "3333");
await page.evaluate(() => [...document.querySelectorAll(".mod-item")].find((e) => e.innerText.includes("家校沟通"))?.click());
await sleep(1800);
const parentMsg = await page.evaluate(() => ({
  peer: document.querySelector(".conv-peer")?.innerText?.replace(/\s+/g, " ").slice(0, 80) || "",
  phone: document.querySelector(".peer-contact a")?.innerText || "",
  noH2: !document.querySelector(".msg-head h2"),
  pageFitsView: Math.abs((document.querySelector(".msg-page")?.getBoundingClientRect().height || 0) - (document.querySelector(".view")?.getBoundingClientRect().height || 0)) < 200,
}));
console.log("LIVE parent msg:", JSON.stringify(parentMsg));

// === 教师端班级概览 + 资源页 ===
await login("teacher", "2024014501", "4444");
await page.evaluate(() => [...document.querySelectorAll(".mod-item")].find((e) => e.innerText.includes("课堂学情"))?.click());
await sleep(1500);
const teacherInfo = await page.evaluate(() => ({
  classCards: document.querySelectorAll(".class-card").length,
  classCardTexts: [...document.querySelectorAll(".class-card b")].map((e) => e.innerText),
}));
console.log("LIVE teacher classes:", JSON.stringify(teacherInfo));

await page.evaluate(() => [...document.querySelectorAll(".mod-item")].find((e) => e.innerText.includes("历年真题"))?.click());
await sleep(1500);
const resInfo = await page.evaluate(() => ({
  path: location.pathname,
  tabs: [...document.querySelectorAll(".rt")].map((e) => e.innerText.replace(/\s+/g, " ").trim()),
  hasUpload: !!document.querySelector(".upload-card"),
  hasFileInput: !!document.querySelector('input[type="file"]'),
}));
console.log("LIVE teacher res:", JSON.stringify(resInfo));

await browser.close();
console.log("DONE");
