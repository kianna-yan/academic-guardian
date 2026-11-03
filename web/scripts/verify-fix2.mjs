import puppeteer from "puppeteer-core";
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--disable-gpu", "--no-sandbox"] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 880 });
page.on("pageerror", (e) => console.log("PAGEERROR:", e.message));

async function login(role, account, password) {
  const r = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role, account, password }),
  });
  const j = await r.json();
  if (!j.ok) throw new Error(`login failed: ${JSON.stringify(j)}`);
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle2" });
  await page.evaluate((t) => { localStorage.clear(); localStorage.setItem("ag.token", t); }, j.token);
  const home = { student: "/student", counselor: "/counselor", admin: "/admin", parent: "/parent", teacher: "/teacher" }[role];
  await page.goto(`${BASE}${home}`, { waitUntil: "networkidle2" });
  await sleep(1800);
}

async function getNoticeTitles() {
  return await page.evaluate(() => {
    return [...document.querySelectorAll(".el-notification__title")].map((e) => e.innerText?.trim() || "").filter(Boolean);
  });
}

// === 1. 滚动 bug 验证 ===
await login("counselor", "2024014589", "1111");
await page.evaluate(() => [...document.querySelectorAll(".mod-item")].find((e) => e.innerText.includes("风险名单"))?.click());
await sleep(1500);
const scrollInfo = await page.evaluate(() => {
  const v = document.querySelector(".view");
  v.scrollTop = 100;
  return { scrollTop: v?.scrollTop, scrollHeight: v?.scrollHeight, clientHeight: v?.clientHeight, canScroll: (v?.scrollHeight || 0) > (v?.clientHeight || 0) };
});
console.log("STEP1 scroll:", JSON.stringify(scrollInfo));
await page.screenshot({ path: "shots_fix2/01-counselor-roster.png" });

// === 2. 智慧森林 ===
await page.evaluate(() => [...document.querySelectorAll(".mod-item")].find((e) => e.innerText.includes("智慧森林"))?.click());
await sleep(1400);
const forestInfo = await page.evaluate(() => ({
  cards: document.querySelectorAll(".forest-card").length,
  trees: document.querySelectorAll(".tree").length,
  hash: location.hash,
  firstTitle: document.querySelector(".forest-head h3")?.innerText || "",
  greenTrees: document.querySelectorAll(".tree.green").length,
  yellowTrees: document.querySelectorAll(".tree.yellow").length,
  redTrees: document.querySelectorAll(".tree.red").length,
}));
console.log("STEP2 forest:", JSON.stringify(forestInfo));
await page.screenshot({ path: "shots_fix2/02-counselor-forest.png" });

// === 3. 辅导员端 → 学生抽屉 → 家校沟通按钮 ===
await page.evaluate(() => [...document.querySelectorAll(".mod-item")].find((e) => e.innerText.includes("风险名单"))?.click());
await sleep(1200);
await page.evaluate(() => { const r = document.querySelector(".el-table__row") || document.querySelector(".m-row"); if (r) r.click(); });
await sleep(1500);
const drawerBtn = await page.evaluate(() => {
  const b = [...document.querySelectorAll(".drawer-exports .chip-msg")];
  return { count: b.length, text: b[0]?.innerText || "" };
});
console.log("STEP3 drawer btn:", JSON.stringify(drawerBtn));
await page.evaluate(() => document.querySelector(".drawer-exports .chip-msg")?.click());
await sleep(1800);
const msgInfo = await page.evaluate(() => ({
  path: location.pathname,
  query: location.search,
  peerText: document.querySelector(".conv-peer")?.innerText?.replace(/\s+/g, " ").slice(0, 80) || "",
  hasPhone: !!document.querySelector(".peer-contact a"),
  phone: document.querySelector(".peer-contact a")?.innerText || "",
  threadListCount: document.querySelectorAll(".thread-row").length,
  hasSearch: !!document.querySelector(".thread-search input"),
  noH2: !document.querySelector(".msg-head h2"),
}));
console.log("STEP3 msg:", JSON.stringify(msgInfo));
await page.screenshot({ path: "shots_fix2/03-counselor-msg.png" });

// === 4. 家长端家校沟通 ===
await login("parent", "20240067", "3333");
await page.evaluate(() => [...document.querySelectorAll(".mod-item")].find((e) => e.innerText.includes("家校沟通"))?.click());
await sleep(1800);
const parentMsg = await page.evaluate(() => {
  const pg = document.querySelector(".msg-page");
  const view = document.querySelector(".view");
  return {
    peer: document.querySelector(".conv-peer")?.innerText?.replace(/\s+/g, " ").slice(0, 80) || "",
    phone: document.querySelector(".peer-contact a")?.innerText || "",
    hasPhone: !!document.querySelector(".peer-contact a"),
    noH2: !document.querySelector(".msg-head h2"),
    pageHeight: pg?.getBoundingClientRect().height || 0,
    viewHeight: view?.getBoundingClientRect().height || 0,
    pageFitsView: Math.abs((pg?.getBoundingClientRect().height || 0) - (view?.getBoundingClientRect().height || 0)) < 200,
  };
});
console.log("STEP4 parent msg:", JSON.stringify(parentMsg));
await page.screenshot({ path: "shots_fix2/04-parent-msg.png" });

// === 5. 通知去重 ===
await page.evaluate(() => {
  const ta = document.querySelector(".conv-input textarea");
  if (ta) { ta.value = "测试家校消息去重"; ta.dispatchEvent(new Event("input")); }
});
await sleep(200);
await page.click(".conv-input .btn.ok");
await sleep(1500);
await login("counselor", "2024014589", "1111");
await sleep(3800);
const titles = await getNoticeTitles();
console.log("STEP5 notif titles:", JSON.stringify(titles));
await page.screenshot({ path: "shots_fix2/05-counselor-notif.png" });

// === 6. 教师端班级概览 + 资源页 ===
await login("teacher", "2024014501", "4444");
await page.evaluate(() => [...document.querySelectorAll(".mod-item")].find((e) => e.innerText.includes("课堂学情"))?.click());
await sleep(1500);
const teacherInfo = await page.evaluate(() => ({
  classCards: document.querySelectorAll(".class-card").length,
  classCardTexts: [...document.querySelectorAll(".class-card b")].map((e) => e.innerText),
  classFilterOptions: document.querySelectorAll(".filters select option").length,
}));
console.log("STEP6 teacher classes:", JSON.stringify(teacherInfo));
await page.screenshot({ path: "shots_fix2/06-teacher-classes.png" });

await page.evaluate(() => [...document.querySelectorAll(".mod-item")].find((e) => e.innerText.includes("历年真题"))?.click());
await sleep(1500);
const resInfo = await page.evaluate(() => ({
  path: location.pathname,
  tabs: [...document.querySelectorAll(".rt")].map((e) => e.innerText.replace(/\s+/g, " ").trim()),
  hasUpload: !!document.querySelector(".upload-card"),
  hasFileInput: !!document.querySelector('input[type="file"]'),
  uploadFields: document.querySelectorAll(".up-input").length,
}));
console.log("STEP6 teacher res:", JSON.stringify(resInfo));
await page.screenshot({ path: "shots_fix2/07-teacher-resources.png" });

// === 6b. 教师上传接口测试 ===
const tok = await page.evaluate(() => localStorage.getItem("ag.token"));
const fd = new FormData();
fd.append("file", new Blob(["test exam content"], { type: "text/plain" }), "2023-final-exam.txt");
fd.append("kind", "exam");
fd.append("course", "测试课程");
fd.append("class_name", "测试班");
fd.append("note", "自动化测试");
const r = await fetch(`${BASE}/api/teacher/resources?ag_token=${encodeURIComponent(tok)}`, { method: "POST", body: fd });
const j = await r.json();
console.log("STEP6b upload:", JSON.stringify({ status: r.status, ok: j.ok, filename: j.item?.filename }));

await browser.close();
console.log("DONE");
