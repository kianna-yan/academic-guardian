// 本轮四项改动的回归验证（本地 8620）：全部走真实点击（门户节点 / 返回门户），
// 不用 pushState 伪造导航——那会破坏 vue-router 的 history.state，导致后续 push 报错。
import puppeteer from "puppeteer-core";
import fs from "node:fs";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8620";
const OUT = "shots_r6";
fs.mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let pass = 0;
let fail = 0;
const ok = (name, cond, extra = "") => {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${extra ? "  · " + extra : ""}`);
  cond ? pass++ : fail++;
};

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
  args: ["--disable-gpu", "--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*", "--font-render-hinting=none"],
});

async function newPage(tk) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push("console: " + m.text().slice(0, 200));
  });
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
  await page.evaluate((t) => localStorage.setItem("ag.token", t), tk);
  await page.reload({ waitUntil: "domcontentloaded" });
  await sleep(1500);
  await page.evaluate(() => {
    document.querySelectorAll(".v11-veil,.star-wipe,.pre-veil").forEach((n) => n.remove());
    document.documentElement.classList.remove("v11-veil");
  });
  return { page, errors };
}

async function enterPort(page) {
  const clicked = await page.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((n) => n.textContent.trim() === "继续进入");
    if (!b) return false;
    b.click();
    return true;
  });
  if (clicked) await sleep(2800);
  return clicked;
}

/** 点门户画布上的节点进板块；若当前在内页，先点"返回门户" */
async function openNode(page, key) {
  const onPortal = await page.evaluate(() => !!document.querySelector(".pt-node"));
  if (!onPortal) {
    await page.evaluate(() => document.querySelector('[data-test="back-home"]')?.click());
    await sleep(2800);
  }
  const hit = await page.evaluate((k) => {
    const n = document.querySelector(`.pt-node[data-node="${k}"]`);
    if (!n) return false;
    n.click();
    return true;
  }, key);
  await sleep(3000); // 开屏动画
  return hit;
}

/* ---------------- 学生端：消息弹窗 / 编号 / 异议跳转 ---------------- */
{
  const tk = await token("student", "20240221", "0000");
  const { page, errors } = await newPage(tk);
  const landed = await enterPort(page);
  console.log("学生端进入门户:", landed, page.url());

  await sleep(2500);
  const stackOnHome = await page.evaluate(() => {
    const el = document.querySelector(".ntf-stack");
    return el ? { n: el.querySelectorAll(".ntf").length, display: getComputedStyle(el).display } : null;
  });
  console.log("门户首屏消息卡片:", JSON.stringify(stackOnHome));
  ok("第4项 · 门户首屏仍有消息弹窗", !!stackOnHome && stackOnHome.n > 0, JSON.stringify(stackOnHome));
  await page.screenshot({ path: `${OUT}/1-student-home.png` });

  // 进板块 → 消息卡片必须消失
  const toOverview = await openNode(page, "overview");
  await sleep(1200);
  const stackOnSection = await page.evaluate(() => !!document.querySelector(".ntf-stack"));
  ok("第4项 · 板块页不再显示消息弹窗", toOverview && !stackOnSection, page.url());

  const bands = await page.evaluate(() =>
    [...document.querySelectorAll(".region-band")].map(
      (b) => `${b.querySelector(".rb-no").textContent.trim()} ${b.querySelector(".rb-text b").textContent.trim()}`,
    ),
  );
  console.log("学情总览板块编号:", bands);
  ok("第2项 · 编号 01 / 02", bands[0]?.startsWith("01") && bands[1]?.startsWith("02"), bands.join(" | "));
  await page.screenshot({ path: `${OUT}/2-student-overview.png`, fullPage: true });

  // 异议 → 跳转复核与异议
  await openNode(page, "records");
  await sleep(1200);
  const before = page.url();
  const hit = await page.evaluate(() => {
    const b = document.querySelector(".appeal-btn");
    if (!b) return false;
    b.scrollIntoView({ block: "center" });
    b.click();
    return true;
  });
  await sleep(2200);
  const after = page.url();
  const hasForm = await page.evaluate(() => !!document.querySelector(".appeal-form"));
  const target = await page.evaluate(
    () => document.querySelector(".appeal-target")?.textContent.replace(/\s+/g, " ").trim() || "",
  );
  ok("第3项 · 点异议跳到复核与异议", hit && after.includes("/student/appeal"), `${before} → ${after}`);
  ok("第3项 · 表单已带记录并展开", hasForm, target);
  await page.screenshot({ path: `${OUT}/3-student-appeal.png` });

  // 回门户 → 消息弹窗应重新报到
  await page.evaluate(() => document.querySelector('[data-test="back-home"]')?.click());
  await sleep(4200);
  const stackBack = await page.evaluate(() => {
    const el = document.querySelector(".ntf-stack");
    return el ? el.querySelectorAll(".ntf").length : 0;
  });
  ok("第4项 · 回到门户后消息弹窗重新出现", stackBack > 0, `${stackBack} 条 · ${page.url()}`);
  await page.screenshot({ path: `${OUT}/6-back-home.png` });

  ok("学生端无 JS 报错", errors.length === 0, errors.slice(0, 2).join(" / "));
  await page.close();
}

/* ---------------- 辅导员端：告知函在最上层 ---------------- */
{
  const tk = await token("counselor", "2024014589", "1111");
  const { page, errors } = await newPage(tk);
  await enterPort(page);
  await openNode(page, "roster");
  await sleep(1500);

  await page.evaluate(() => {
    document.querySelector(".el-table__body tr")?.click();
  });
  await sleep(2200);
  await page.screenshot({ path: `${OUT}/4-drawer.png` });

  const gen = await page.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((n) => n.textContent.includes("生成告知函"));
    if (!b) return false;
    b.click();
    return true;
  });
  console.log("点生成告知函:", gen);
  await sleep(3200);

  const geo = await page.evaluate(() => {
    const overlay = document.querySelector(".el-overlay.letter-modal");
    const dlg = document.querySelector(".el-overlay.letter-modal .el-dialog");
    const drawer = document.querySelector(".el-drawer");
    if (!overlay || !dlg) return null;
    const r = dlg.getBoundingClientRect();
    const probe = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
    return {
      overlayZ: getComputedStyle(overlay).zIndex,
      drawerZ: drawer ? getComputedStyle(drawer.parentElement || drawer).zIndex : "none",
      topEl: probe?.closest(".letter-modal") ? "letter" : probe?.className || "?",
      w: Math.round(r.width),
      h: Math.round(r.height),
    };
  });
  console.log("告知函层级:", JSON.stringify(geo));
  ok("第1项 · 告知函在抽屉之上（命中元素是文书）", geo?.topEl === "letter", String(geo?.topEl));
  ok("第1项 · 告知函遮罩 z-index ≥ 3200", Number(geo?.overlayZ) >= 3200, String(geo?.overlayZ));
  await page.screenshot({ path: `${OUT}/5-letter-dialog.png` });
  ok("辅导员端无 JS 报错", errors.length === 0, errors.slice(0, 2).join(" / "));
  await page.close();
}

await browser.close();
console.log(`\n结果：PASS ${pass} · FAIL ${fail}`);
process.exit(fail ? 1 : 0);
