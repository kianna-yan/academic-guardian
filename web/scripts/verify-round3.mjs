/**
 * 第三轮优化验收：教师端资源合并、班级切换图表联动、课表状态刷新与日期显示、森林美化。
 * 本地跑：node scripts/verify-round3.mjs
 */
import puppeteer from "puppeteer-core";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({
  executablePath: EXE,
  headless: true,
  args: ["--disable-gpu", "--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1320, height: 900 });
page.on("pageerror", (e) => console.log("PAGEERROR:", e.message));

const HOME = {
  student: "/student",
  counselor: "/counselor",
  admin: "/admin",
  parent: "/parent",
  teacher: "/teacher",
};

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
  await sleep(2000);
}

async function clickNav(keyword) {
  await page.evaluate((kw) => {
    const el = [...document.querySelectorAll(".mod-item")].find((e) =>
      e.innerText.includes(kw),
    );
    el?.click();
  }, keyword);
  await sleep(1300);
}

/* ========== 1. 教师端：教学资源只剩一项 ========== */
console.log("\n===== 1. 教师端教学资源菜单 =====");
await login("teacher", "2024014501", "4444");
const navRes = await page.evaluate(() => {
  const items = [...document.querySelectorAll(".mod-item")].map((e) =>
    e.innerText.replace(/\s+/g, " ").trim(),
  );
  return {
    items,
    hasExam: items.some((t) => t.includes("历年真题")),
    hasTutorial: items.some((t) => t.includes("网课")),
    resourceCount: items.filter((t) => t.includes("真题") || t.includes("网课")).length,
  };
});
console.log("侧栏项:", JSON.stringify(navRes.items, null, 0));
console.log("资源相关项数量:", navRes.resourceCount, "(应为 1)");

/* ========== 2. 教师端：点班级后图表与统计联动 ========== */
console.log("\n===== 2. 班级切换联动 =====");
await clickNav("课堂学情");
await sleep(1200);

async function readChartState() {
  return await page.evaluate(() => {
    // StatGrid：.stats .stat > b(值) + span(标签)
    const statVals = [...document.querySelectorAll(".stats .stat b")].map((e) =>
      e.innerText.trim(),
    );
    const statLabels = [...document.querySelectorAll(".stats .stat span")].map((e) =>
      e.innerText.trim(),
    );
    // 分档图上的数值文本
    const bandText = [...document.querySelectorAll(".band, .score-band, .sb-row")].map((e) =>
      e.innerText.replace(/\s+/g, " ").trim(),
    );
    // 底部汇总行
    const foots = [...document.querySelectorAll(".band-foot")].map((e) =>
      e.innerText.replace(/\s+/g, " ").trim(),
    );
    const canvases = document.querySelectorAll("canvas").length;
    return { statVals, statLabels, bandText, foots, canvases };
  });
}

const before = await readChartState();
console.log("全部班级 → 统计:", JSON.stringify(before.statVals));
console.log("全部班级 → 底部:", JSON.stringify(before.foots.slice(0, 2)));

// 点第二个班级卡片（第一个是「全部班级」）
const clickedClass = await page.evaluate(() => {
  const cards = [...document.querySelectorAll(".class-card")];
  if (cards.length < 2) return null;
  cards[1].click();
  return cards[1].innerText.replace(/\s+/g, " ").trim();
});
await sleep(1500);
const after = await readChartState();
console.log("点的班级:", clickedClass);
console.log("该班 → 统计:", JSON.stringify(after.statVals));
console.log("该班 → 底部:", JSON.stringify(after.foots.slice(0, 2)));

const scopeBar = await page.evaluate(() => {
  const el = document.querySelector(".scope-bar");
  return el ? el.innerText.replace(/\s+/g, " ").trim() : null;
});
console.log("范围提示条:", scopeBar);

const statsChanged = JSON.stringify(before.statVals) !== JSON.stringify(after.statVals);
const footChanged = JSON.stringify(before.foots) !== JSON.stringify(after.foots);
console.log("✓ 统计是否变化:", statsChanged);
console.log("✓ 图表底部汇总是否变化:", footChanged);

// 切回全部班级
await page.evaluate(() => document.querySelectorAll(".class-card")[0]?.click());
await sleep(1000);
const back = await readChartState();
console.log("✓ 切回全部后统计恢复:", JSON.stringify(back.statVals) === JSON.stringify(before.statVals));

/* ========== 3. 课表：今天标签不遮挡 + 改状态即时刷新 ========== */
console.log("\n===== 3. 课表 =====");
await login("student", "20240067", "0000");
await clickNav("我的课表");
await sleep(1500);

const headInfo = await page.evaluate(() => {
  const days = [...document.querySelectorAll(".gh.day")];
  return days.map((d) => {
    const sub = d.querySelector(".day-sub");
    const em = d.querySelector("em");
    const tag = d.querySelector(".today-tag");
    const dRect = d.getBoundingClientRect();
    const emRect = em?.getBoundingClientRect();
    const tagRect = tag?.getBoundingClientRect();
    // 日期与「今天」标签是否重叠
    let overlap = false;
    if (emRect && tagRect) {
      overlap = !(
        emRect.right <= tagRect.left ||
        tagRect.right <= emRect.left ||
        emRect.bottom <= tagRect.top ||
        tagRect.bottom <= emRect.top
      );
    }
    // 标签是否超出表头容器
    const overflow = tagRect
      ? tagRect.top < dRect.top - 1 || tagRect.bottom > dRect.bottom + 1
      : false;
    return {
      label: d.querySelector("b")?.innerText,
      date: em?.innerText,
      hasSub: !!sub,
      hasToday: !!tag,
      overlap,
      overflow,
      dayH: Math.round(dRect.height),
    };
  });
});
console.log("表头各列:", JSON.stringify(headInfo, null, 1));

const todayCol = headInfo.find((h) => h.hasToday);
console.log("✓ 今天列日期完整:", todayCol?.date, "| 与标签重叠:", todayCol?.overlap, "| 溢出:", todayCol?.overflow);

// 找一节「待记录」的课，记录后看网格状态是否立刻变
const beforeLesson = await page.evaluate(() => {
  const btns = [...document.querySelectorAll(".lesson")];
  const target = btns.find((b) => b.innerText.includes("待记"));
  if (!target) return null;
  const info = {
    text: target.innerText.replace(/\s+/g, " ").trim(),
    stateClass: target.className,
  };
  target.click();
  return info;
});
console.log("点了这节课:", JSON.stringify(beforeLesson));

if (beforeLesson) {
  await sleep(900);
  // 弹窗里选「听懂」并保存
  const saved = await page.evaluate(() => {
    const dlg = document.querySelector(".el-dialog, .dialog, .checkin-dialog");
    if (!dlg) return { ok: false, reason: "no dialog" };
    const btns = [...dlg.querySelectorAll("button")];
    const full = btns.find((b) => b.innerText.trim() === "听懂" || b.innerText.includes("听懂"));
    full?.click();
    return { ok: !!full, clicked: full?.innerText?.trim() || "" };
  });
  console.log("弹窗状态选择:", JSON.stringify(saved));
  await sleep(400);
  const submit = await page.evaluate(() => {
    // 弹窗底部主按钮：文字为「记下这节课」或「更新这条记录」
    const btn = document.querySelector(".checkin-dialog .btn.primary, .el-dialog .btn.primary");
    if (!btn) return null;
    btn.click();
    return btn.innerText.trim();
  });
  console.log("点保存:", submit);
  await sleep(1600);
  const afterLesson = await page.evaluate(() => {
    const btns = [...document.querySelectorAll(".lesson")];
    return btns
      .filter((b) => !b.className.includes("future"))
      .map((b) => ({
        text: b.innerText.replace(/\s+/g, " ").trim().slice(0, 40),
        cls: b.className,
      }))
      .slice(0, 12);
  });
  console.log("保存后网格前几节:", JSON.stringify(afterLesson, null, 1));
  const anyRecorded = afterLesson.some((l) => l.cls.includes("full") || l.text.includes("听懂"));
  console.log("✓ 网格出现「听懂」状态:", anyRecorded);
}

/* ========== 4. 智慧森林：树渲染 ========== */
console.log("\n===== 4. 智慧森林 =====");
await login("counselor", "2024014589", "1111");
await clickNav("智慧森林");
await sleep(1500);

const forestInfo = await page.evaluate(() => {
  const cards = document.querySelectorAll(".forest-card");
  const trees = [...document.querySelectorAll(".tree")];
  const svgs = document.querySelectorAll(".tree-svg");
  const first = trees[0];
  const svg = first?.querySelector("svg");
  return {
    cards: cards.length,
    trees: trees.length,
    svgs: svgs.length,
    green: trees.filter((t) => t.classList.contains("green")).length,
    yellow: trees.filter((t) => t.classList.contains("yellow")).length,
    red: trees.filter((t) => t.classList.contains("red")).length,
    firstTreeChildren: svg ? svg.children.length : 0,
    firstViewBox: svg?.getAttribute("viewBox"),
    hasShadow: svg ? !!svg.querySelector("ellipse") : false,
    firstTreeText: first?.innerText.replace(/\s+/g, " ").trim().slice(0, 30),
  };
});
console.log("森林:", JSON.stringify(forestInfo, null, 1));
await page.screenshot({ path: "shots_round3/forest.png", fullPage: false });

/* ========== 截图存档 ========== */
await login("teacher", "2024014501", "4444");
await clickNav("课堂学情");
await sleep(1200);
await page.evaluate(() => document.querySelectorAll(".class-card")[2]?.click());
await sleep(1400);
await page.screenshot({ path: "shots_round3/teacher-class.png" });

await clickNav("历年真题");
await sleep(1400);
await page.screenshot({ path: "shots_round3/teacher-resources.png" });

await login("student", "20240067", "0000");
await clickNav("我的课表");
await sleep(1500);
await page.screenshot({ path: "shots_round3/schedule.png" });

await browser.close();
console.log("\nDONE");
