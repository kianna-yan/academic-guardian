/** 线上验收：文书辅助 / 家校沟通 / 技能文案与端口一致（打分享链接）。 */
import puppeteer from "puppeteer-core";
import fs from "node:fs";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const LINK = process.env.LINK || "https://academic-guardian-56914.app.workbuddy.host/?sharecode=G4NKZPCZAO";
const OUT = "shots_skill2";
fs.mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let pass = 0;
let fail = 0;
const ok = (n, c, x = "") => {
  console.log(`${c ? "PASS" : "FAIL"}  ${n}${x ? "  · " + x : ""}`);
  c ? pass++ : fail++;
};

const browser = await puppeteer.launch({
  executablePath: EXE,
  headless: true,
  args: ["--disable-gpu", "--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1366, height: 900 });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));

const answers = () => page.evaluate(() => document.querySelectorAll(".msg:not(.user)").length);
async function lastReply(before) {
  await page.waitForFunction((n) => document.querySelectorAll(".msg:not(.user)").length > n,
    { timeout: 120000 }, before);
  await page.waitForFunction(() => !document.querySelector(".ch-plus")?.disabled, { timeout: 120000 });
  await sleep(500);
  return page.evaluate(() => {
    const nodes = [...document.querySelectorAll(".msg:not(.user)")];
    return (nodes[nodes.length - 1]?.innerText || "").replace(/\s+/g, " ").trim();
  });
}
const lastCard = () =>
  page.evaluate(() => {
    const els = [...document.querySelectorAll(".ch-filecard")];
    const el = els[els.length - 1];
    return el
      ? { cls: el.className, name: el.querySelector(".fc-body b")?.textContent?.trim() || "" }
      : { cls: "", name: "" };
  });

await page.goto(LINK, { waitUntil: "networkidle2", timeout: 60000 });
await page.evaluate(() => localStorage.clear());
await page.reload({ waitUntil: "networkidle2" });
await sleep(1800);

const picked = await page.evaluate(() => {
  const r = [...document.querySelectorAll(".hint-row")].find((e) => e.innerText.includes("辅导员"));
  if (!r) return false;
  r.click();
  return true;
});
ok("线上可选辅导员账号", picked);
await sleep(300);
await page.click(".submit");
await page.waitForFunction(() => !location.pathname.includes("login"), { timeout: 30000 });
await sleep(3000);

await page.click(".ch-plus");
await sleep(500);
await page.evaluate(() => {
  [...document.querySelectorAll(".ch-menu > button")].find((b) => b.innerText.includes("Skill")).click();
});
await sleep(700);
const skills = await page.$$eval(".ch-sub .sub-item", (els) =>
  els.map((e) => ({ key: e.dataset.skill, text: e.innerText.replace(/\s+/g, " ") })),
);
ok("线上导员端 6 个技能", skills.length === 6, skills.map((s) => s.key).join(","));
ok("线上有文书辅助与家校沟通",
  skills.some((s) => s.text.includes("文书辅助")) && skills.some((s) => s.text.includes("家校沟通")));
await page.screenshot({ path: `${OUT}/live-1-menu.png` });

/* 原缺陷回归：提示语与回答都要是导员口径 */
await page.click('.ch-sub .sub-item[data-skill="ppt"]');
await sleep(400);
const draft = await page.$eval('[data-test="chat-input"]', (e) => e.value);
ok("线上 PPT 提示是导员口吻", draft.includes("本班"), draft);
const n1 = await answers();
await page.click('[data-test="chat-send"]');
await page.waitForFunction(
  () => [...document.querySelectorAll(".ch-filecard")].some((e) => e.className.includes("ok")),
  { timeout: 120000 },
);
const r1 = await lastReply(n1);
ok("线上回答是全校口径", r1.includes("全校口径"), r1.slice(0, 40));
const c1 = await lastCard();
ok("线上 PPT 文件卡 ok", c1.cls.includes("ok") && c1.name.endsWith(".pptx"), c1.name);

/* 文书辅助 */
await page.waitForFunction(() => !document.querySelector(".ch-plus")?.disabled, { timeout: 60000 });
await page.click(".ch-plus");
await sleep(400);
await page.evaluate(() => {
  [...document.querySelectorAll(".ch-menu > button")].find((b) => b.innerText.includes("Skill")).click();
});
await sleep(600);
await page.click('.ch-sub .sub-item[data-skill="doc"]');
await sleep(600);
const docs = await page.$$eval(".ch-sub .sub-item", (els) => els.map((e) => e.dataset.sub));
ok("线上文书六类", docs.length === 6, docs.join(","));
await page.screenshot({ path: `${OUT}/live-2-doc.png` });
await page.click('.ch-sub .sub-item[data-sub="review"]');
await sleep(400);
const n2 = await answers();
await page.click('[data-test="chat-send"]');
await page.waitForFunction(
  () => [...document.querySelectorAll(".ch-filecard")].some((e) => e.className.includes("ok")),
  { timeout: 120000 },
);
const r2 = await lastReply(n2);
ok("线上文书回答有签批链", r2.includes("签批链"), r2.slice(0, 40));
ok("线上文书回答写明不代提交", r2.includes("不代提交"));
const c2 = await lastCard();
ok("线上文书文件卡 .docx", c2.cls.includes("ok") && c2.name.endsWith(".docx"), c2.name);
await page.screenshot({ path: `${OUT}/live-3-docdone.png` });

/* 家校沟通 */
await page.waitForFunction(() => !document.querySelector(".ch-plus")?.disabled, { timeout: 60000 });
await page.click(".ch-plus");
await sleep(400);
await page.evaluate(() => {
  [...document.querySelectorAll(".ch-menu > button")].find((b) => b.innerText.includes("Skill")).click();
});
await sleep(600);
await page.click('.ch-sub .sub-item[data-skill="family"]');
await sleep(600);
const ps = await page.$$eval(".ch-sub .sub-item", (els) => els.map((e) => e.dataset.sub));
ok("线上四类家长", ps.length === 4, ps.join(","));
await page.click('.ch-sub .sub-item[data-sub="cooperative"]');
await sleep(400);
const n3 = await answers();
await page.click('[data-test="chat-send"]');
const r3 = await lastReply(n3);
ok("线上家长先开口", r3.includes("配合型家长"), r3.slice(0, 40));
ok("线上给潜台词", r3.includes("潜台词"));
await page.screenshot({ path: `${OUT}/live-4-family.png` });

await page.evaluate(() => {
  const el = document.querySelector('[data-test="chat-input"]');
  el.value = "";
  el.dispatchEvent(new Event("input", { bubbles: true }));
});
await page.type('[data-test="chat-input"]', "复盘");
const n4 = await answers();
await page.click('[data-test="chat-send"]');
const r4 = await lastReply(n4);
ok("线上能复盘", r4.includes("复盘") && r4.includes("事实底子"), r4.slice(0, 30));

ok("线上无 JS 报错", errors.length === 0, errors.slice(0, 2).join(" | "));
console.log(`\n结果：${pass} 通过 / ${fail} 失败`);
await browser.close();
process.exit(fail ? 1 : 0);
