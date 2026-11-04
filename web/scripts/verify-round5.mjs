/**
 * 第五轮验收：
 * 1 教务端删掉「全校看板」整块；
 * 2 图表 tooltip 不再钻到棕色侧栏底下；
 * 3 待办勾掉即消失 + 切页自动刷新；
 * 4 登录页：忘记密码 / 端口示例 / 家长端真实学号；
 * 5 AI 顾问挪到侧栏最上面。
 */
import puppeteer from "puppeteer-core";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const OUT = "shots_round5";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({
  executablePath: EXE,
  headless: true,
  args: ["--disable-gpu", "--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1320, height: 900 });
page.on("pageerror", (e) => console.log("PAGEERROR:", e.message));

const HOME = { student: "/student", counselor: "/counselor", admin: "/admin", parent: "/parent", teacher: "/teacher" };

async function login(role, account, password) {
  const r = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role, account, password }),
  });
  const j = await r.json();
  if (!j.ok) throw new Error(`login failed ${role}: ${JSON.stringify(j)}`);
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle2" });
  await page.evaluate((t) => {
    localStorage.clear();
    localStorage.setItem("ag.token", t);
  }, j.token);
  await page.goto(`${BASE}${HOME[role]}`, { waitUntil: "networkidle2" });
  await sleep(2200);
}

const ok = (label, cond, extra = "") =>
  console.log(`${cond ? "PASS" : "FAIL"} · ${label}${extra ? " —— " + extra : ""}`);

/* ========== 4. 登录页 ========== */
console.log("\n===== 4. 登录页 =====");
await page.goto(`${BASE}/login`, { waitUntil: "networkidle2" });
await sleep(1200);
const loginInfo = await page.evaluate(() => {
  const text = document.body.innerText;
  const rows = [...document.querySelectorAll(".hint-row")].map((r) => ({
    name: r.querySelector(".hr-name")?.textContent?.trim() || "",
    acc: r.querySelector(".hr-acc")?.textContent?.trim() || "",
  }));
  return {
    hasForgot: !!document.querySelector(".forgot"),
    forgotText: document.querySelector(".forgot")?.textContent?.trim() || "",
    hintTitle: document.querySelector(".hint-head b")?.textContent?.trim() || "",
    cols: [...document.querySelectorAll(".hint-cols span")].map((s) => s.textContent.trim()),
    rows,
    bodyHasInitial: text.includes("初始密码"),
  };
});
ok("有「忘记密码」入口", loginInfo.hasForgot, loginInfo.forgotText);
ok("标题改成「端口示例」", loginInfo.hintTitle === "端口示例", loginInfo.hintTitle);
const parentRow = loginInfo.rows.find((r) => r.name === "家长端");
ok("家长端账号是真实学号", /^\d{6,}$/.test(parentRow?.acc || ""), parentRow?.acc);
ok("表头不再写「初始密码」", !loginInfo.cols.includes("初始密码"), loginInfo.cols.join("|"));
await page.screenshot({ path: `${OUT}/1-login.png` });

// 点「忘记密码」弹说明
await page.click(".forgot");
await sleep(600);
const alertText = await page.evaluate(() => document.querySelector(".el-message-box__message")?.innerText || "");
ok("忘记密码弹窗有处置路径", alertText.includes("辅导员") && alertText.includes("教务"), alertText.split("\n")[0]);
await page.screenshot({ path: `${OUT}/2-forgot.png` });
await page.evaluate(() => document.querySelector(".el-message-box__btns .el-button")?.click());
await sleep(400);

/* ========== 1. 教务端：全校看板整块不在 ========== */
console.log("\n===== 1. 教务端 =====");
await login("admin", "1234567899", "2222");
// 教务端默认落在整页对话上，先点侧栏「全校概览」切到看板
await page.evaluate(() => {
  const el = [...document.querySelectorAll(".mod-item")].find((e) => e.innerText.includes("全校概览"));
  el?.click();
});
await sleep(2000);
const admin = await page.evaluate(() => {
  const bands = [...document.querySelectorAll(".region-band, .band-head, .rb-title")].map((e) =>
    e.innerText.replace(/\s+/g, " ").trim(),
  );
  const text = document.body.innerText;
  return {
    text,
    hasBoardTitle: text.includes("01 全校看板") || text.includes("全校看板"),
    hasDailyCard: text.includes("每日预警日报") && !!document.querySelector(".report-strip"),
    statCount: document.querySelectorAll(".stats .stat").length,
    boardAnchor: !!document.querySelector("#board"),
    hasDonut: !!document.querySelector(".donut"),
    hasClassCompare: !!document.querySelector(".class-compare, canvas"),
    bands,
  };
});
ok("「全校看板」标题已删", !admin.hasBoardTitle);
ok("每日日报卡已删", !admin.hasDailyCard);
ok("四张统计卡已删", admin.statCount === 0, `剩 ${admin.statCount} 张`);
ok("#board 锚点保留（侧栏全校概览可跳）", admin.boardAnchor);
ok("分布图/班级对比还在", admin.hasDonut && admin.hasClassCompare);
await page.screenshot({ path: `${OUT}/3-admin.png` });

/* ========== 2. 图表 tooltip 不钻到侧栏下面 ========== */
console.log("\n===== 2. 图表 tooltip =====");
const donutBox = await page.evaluate(() => {
  const el = document.querySelector(".donut-chart");
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return { x: r.x, y: r.y, w: r.width, h: r.height };
});
if (donutBox) {
  await page.mouse.move(donutBox.x + donutBox.w * 0.12, donutBox.y + donutBox.h * 0.5);
  await sleep(700);
  const tip = await page.evaluate(() => {
    const t = [...document.querySelectorAll("div")].find(
      (d) => d.style && d.style.position === "absolute" && /人（[\d.]+%）/.test(d.innerText || "") && d.offsetParent,
    );
    if (!t) return null;
    const r = t.getBoundingClientRect();
    const sidebar = document.querySelector(".sidebar").getBoundingClientRect();
    return { left: r.left, right: r.right, sidebarRight: sidebar.right, text: t.innerText.replace(/\s+/g, " ") };
  });
  if (tip) {
    ok("tooltip 完整落在侧栏右侧", tip.left >= tip.sidebarRight - 1, `left=${Math.round(tip.left)} 侧栏右缘=${Math.round(tip.sidebarRight)} · ${tip.text}`);
  } else {
    console.log("SKIP · 没抓到 tooltip（鼠标位置可能没压到扇区）");
  }
  await page.screenshot({ path: `${OUT}/4-tooltip.png` });
}

/* ========== 5. 侧栏 AI 顾问在最上面 ========== */
console.log("\n===== 5. 学生端侧栏顺序 =====");
await login("student", "20240023", "0000");
const side = await page.evaluate(() => {
  const groups = [...document.querySelectorAll(".mod-group")].map((g) => ({
    label: g.querySelector(".mod-label span")?.textContent?.trim() || "",
    first: g.querySelector(".mod-item")?.innerText.replace(/\s+/g, " ").trim() || "",
  }));
  return groups;
});
ok("第一个分区是 AI 顾问", side[0]?.label === "AI 顾问", JSON.stringify(side.map((s) => s.label)));
ok("第一个菜单项是学业对话", (side[0]?.first || "").includes("学业对话"), side[0]?.first);
const sideTop = await page.evaluate(() => {
  const g = document.querySelector(".mod-group");
  const nav = document.querySelector(".mod-nav");
  return { gTop: Math.round(g.getBoundingClientRect().top), navTop: Math.round(nav.getBoundingClientRect().top) };
});
ok("AI 顾问贴着导航顶部", Math.abs(sideTop.gTop - sideTop.navTop) < 2, JSON.stringify(sideTop));
await page.screenshot({ path: `${OUT}/5-sidebar.png` });

/* ========== 3. 待办勾掉即消失 ========== */
console.log("\n===== 3. 待办 =====");
await page.evaluate(() => document.querySelector(".bell")?.click());
await sleep(800);
await page.evaluate(() => {
  const t = [...document.querySelectorAll(".panel .tab")].find((e) => e.innerText.includes("待办"));
  t?.click();
});
await sleep(500);
const before = await page.evaluate(() => document.querySelectorAll(".panel .item.todo").length);
const badgeBefore = await page.evaluate(() => [...document.querySelectorAll(".panel .tab")].find((e) => e.innerText.includes("待办"))?.innerText || "");
await page.screenshot({ path: `${OUT}/6-todo-before.png` });
if (before > 0) {
  const title = await page.evaluate(() => document.querySelector(".panel .item.todo b")?.innerText || "");
  await page.evaluate(() => document.querySelector(".panel .item.todo input")?.click());
  await sleep(1200);
  const after = await page.evaluate(() => document.querySelectorAll(".panel .item.todo").length);
  const stillThere = await page.evaluate(
    (t) => [...document.querySelectorAll(".panel .item.todo b")].some((b) => b.innerText === t),
    title,
  );
  ok("勾掉后从列表消失", after === before - 1 && !stillThere, `${before} → ${after} · 勾掉的是「${title}」`);
  await page.screenshot({ path: `${OUT}/7-todo-after.png` });
} else {
  console.log("SKIP · 该账号没有待办");
}

/* ========== 3b. 切页自动刷新 ========== */
console.log("\n===== 3b. 切页刷新 =====");
const calls = [];
page.on("request", (req) => {
  if (req.url().includes("/api/notifications")) calls.push(req.url());
});
await page.evaluate(() => {
  const el = [...document.querySelectorAll(".mod-item")].find((e) => e.innerText.includes("学习轨迹"));
  el?.click();
});
await sleep(1500);
ok("进入新页面会重新拉消息", calls.length >= 1, `命中 ${calls.length} 次 /api/notifications`);

await browser.close();
console.log("\n完成，截图在 web/" + OUT + "/");
