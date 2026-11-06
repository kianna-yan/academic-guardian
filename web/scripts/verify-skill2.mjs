/**
 * 「文书辅助 / 家校沟通」+「技能文案与端口一致」验收（本地 8620）
 *
 * 背景：上一版技能的预填提示只有学生口吻一句，导员端点了「PPT 生成」拿到
 * 「给我一个这学期的补救计划」，意图认不出来，最后落到兜底话术。
 * 这里把「提示语是否按端给」和「回答是否按端组织」都写成断言。
 *
 * 断言：
 *  学生端  1 菜单 4 项（不含文书/家校）
 *          2 PPT 预填是学生口径
 *          3 回答是学生口径（「这份PPT讲的是你」）+ 文件卡 .pptx
 *  导员端  4 菜单 6 项，含文书辅助、家校沟通
 *          5 PPT 预填是导员口径（本班），回答是全校口径（原缺陷回归）
 *          6 文书辅助二级 6 项
 *          7 选「休学申请」→ 预填带书名号、标签提示只起草不提交
 *          8 回答含签批链与「只起草，不代提交」，文件卡 .docx
 *          9 家校沟通二级 4 类家长
 *         10 选「焦虑型家长」→ 家长开口 + 潜台词 + 无文件卡
 *         11 回一句话 → 家长第 2 轮
 *         12 说「复盘」→ 出复盘
 *         13 页面无 JS 报错
 */
import puppeteer from "puppeteer-core";
import fs from "node:fs";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8620";
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

async function login(role, account, password) {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role, account, password }),
  });
  return (await res.json()).token;
}

async function open(role, path, token) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1366, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle2" });
  await page.evaluate((t) => {
    localStorage.clear();
    localStorage.setItem("ag.token", t);
  }, token);
  await page.goto(`${BASE}/${path}`, { waitUntil: "networkidle2" });
  await sleep(2600);
  // 新版首屏是图形门户，AI 收在底部那条输入条里：先点开抽屉，技能菜单才在 DOM 里
  const dock = await page.$('[data-test="ai-dock"]');
  if (dock) {
    await dock.click();
    await sleep(1000);
  }
  return { page, errors };
}

/** 打开 + 菜单 → Skill 二级菜单 */
async function openSkillMenu(page) {
  await page.waitForFunction(() => !document.querySelector(".ch-plus")?.disabled, { timeout: 60000 });
  await sleep(300);
  await page.click(".ch-plus");
  await sleep(350);
  await page.evaluate(() => {
    [...document.querySelectorAll(".ch-menu > button")].find((b) => b.innerText.includes("Skill")).click();
  });
  await sleep(450);
}

const answers = (page) => page.evaluate(() => document.querySelectorAll(".msg:not(.user)").length);

/** 等这一轮答完（新气泡出现 + 流式结束），再取最后一条回答的全文 */
async function lastReply(page, before) {
  await page.waitForFunction((n) => document.querySelectorAll(".msg:not(.user)").length > n,
    { timeout: 90000 }, before);
  await page.waitForFunction(() => !document.querySelector(".ch-plus")?.disabled, { timeout: 90000 });
  await sleep(400);
  return page.evaluate(() => {
    const nodes = [...document.querySelectorAll(".msg:not(.user)")];
    return (nodes[nodes.length - 1]?.innerText || "").replace(/\s+/g, " ").trim();
  });
}

/** 最后一张文件卡（一个会话里可能生成过好几份） */
const lastCard = (page) =>
  page.evaluate(() => {
    const els = [...document.querySelectorAll(".ch-filecard")];
    const el = els[els.length - 1];
    return el
      ? { cls: el.className, name: el.querySelector(".fc-body b")?.textContent?.trim() || "" }
      : { cls: "", name: "" };
  });

/* ------------------------------------------------------------------ 学生端 */
{
  const token = await login("student", "20240023", "0000");
  const { page, errors } = await open("student", "student", token);

  await openSkillMenu(page);
  const studentSkills = await page.$$eval(".ch-sub .sub-item", (els) => els.map((e) => e.dataset.skill));
  ok("学生端菜单 4 项", studentSkills.length === 4, studentSkills.join(","));
  ok("学生端看不到文书辅助", !studentSkills.includes("doc"));
  ok("学生端看不到家校沟通", !studentSkills.includes("family"));

  await page.click('.ch-sub .sub-item[data-skill="ppt"]');
  await sleep(350);
  const draft = await page.$eval('[data-test="chat-input"]', (e) => e.value);
  ok("学生端 PPT 提示是学生口吻", draft.includes("这学期") && !draft.includes("本班"), draft);

  const n1 = await answers(page);
  await page.click('[data-test="chat-send"]');
  await page.waitForFunction(
    () => document.querySelector(".ch-filecard.ok, .ch-filecard.fail"),
    { timeout: 60000 },
  );
  const reply = await lastReply(page, n1);
  ok("学生端回答是「你」的口径", reply.includes("讲的是你这学期"), reply.slice(0, 60));
  const card = await lastCard(page);
  ok("学生端文件卡是 .pptx", card.cls.includes("ok") && card.name.endsWith(".pptx"), card.name);
  await page.screenshot({ path: `${OUT}/1-student.png` });
  ok("学生端无 JS 报错", errors.length === 0, errors.slice(0, 2).join(" | "));
  await page.close();
}

/* ------------------------------------------------------------------ 导员端 */
{
  const token = await login("counselor", "2024014589", "1111");
  const { page, errors } = await open("counselor", "counselor", token);

  await openSkillMenu(page);
  const skills = await page.$$eval(".ch-sub .sub-item", (els) =>
    els.map((e) => ({ key: e.dataset.skill, text: e.innerText.replace(/\s+/g, " ") })),
  );
  ok("导员端菜单 6 项", skills.length === 6, skills.map((s) => s.key).join(","));
  ok("有「文书辅助」", skills.some((s) => s.text.includes("文书辅助")));
  ok("有「家校沟通」", skills.some((s) => s.text.includes("家校沟通")));
  await page.screenshot({ path: `${OUT}/2-counselor-menu.png` });

  /* 原缺陷回归：导员端的 PPT 提示语与回答都必须是导员口径 */
  await page.click('.ch-sub .sub-item[data-skill="ppt"]');
  await sleep(350);
  const cDraft = await page.$eval('[data-test="chat-input"]', (e) => e.value);
  ok("导员端 PPT 提示不再是学生口吻", cDraft.includes("本班") && !cDraft.includes("我该"), cDraft);
  const n2 = await answers(page);
  await page.click('[data-test="chat-send"]');
  await page.waitForFunction(
    () => document.querySelector(".ch-filecard.ok, .ch-filecard.fail"),
    { timeout: 60000 },
  );
  const cReply = await lastReply(page, n2);
  ok("导员端回答是全校口径", cReply.includes("全校口径") && !cReply.includes("讲的是你这学期"),
    cReply.slice(0, 60));
  ok("回答里没有兜底话术", !cReply.includes("规则引擎没认出来") && !cReply.includes("这次我没听懂"));
  await page.screenshot({ path: `${OUT}/3-counselor-ppt.png` });

  /* 文书辅助 */
  await openSkillMenu(page);
  await page.click('.ch-sub .sub-item[data-skill="doc"]');
  await sleep(400);
  const docs = await page.$$eval(".ch-sub .sub-item", (els) => els.map((e) => e.dataset.sub));
  ok("文书辅助二级 6 类", docs.length === 6, docs.join(","));
  ok("含休学/调课/免修/复核/通知/纪要",
    ["suspend", "adjust", "exempt", "review", "notice", "minutes"].every((k) => docs.includes(k)));
  ok("二级菜单有「只起草」提示", !!(await page.$(".ch-sub .sub-note")));
  await page.screenshot({ path: `${OUT}/4-doc-menu.png` });

  await page.click('.ch-sub .sub-item[data-sub="suspend"]');
  await sleep(350);
  const dDraft = await page.$eval('[data-test="chat-input"]', (e) => e.value);
  ok("文书预填带书名号", dDraft.includes("《休学申请》"), dDraft);
  const tag = await page.$eval(".ch-skilltag", (el) => el.innerText.replace(/\s+/g, " "));
  ok("技能标签提示不代提交", tag.includes("只起草") && tag.includes("休学申请"), tag);

  const n3 = await answers(page);
  // 导员没有固定学生：把名字打在问题里，回答与文件必须都落到同一个人
  await page.evaluate(() => {
    const el = document.querySelector('[data-test="chat-input"]');
    el.value = "";
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await page.type('[data-test="chat-input"]', "帮我起草一份《休学申请》，给沈一鸣");
  await page.click('[data-test="chat-send"]');
  await page.waitForFunction(
    () => [...document.querySelectorAll(".ch-filecard")].some((e) => e.className.includes("ok")),
    { timeout: 60000 },
  );
  const docReply = await lastReply(page, n3);
  ok("回答写明签批链", docReply.includes("签批链"), docReply.slice(0, 60));
  ok("回答写明不代提交", docReply.includes("不代提交"));
  const docCard = await lastCard(page);
  ok("文书文件卡是 .docx", docCard.cls.includes("ok") && docCard.name.endsWith(".docx"), docCard.name);
  ok("文件名带文书类型与学生", docCard.name.includes("休学申请") && docCard.name.includes("沈一鸣"),
    docCard.name);
  ok("回答也落到同一个学生", docReply.includes("沈一鸣"));
  await page.screenshot({ path: `${OUT}/5-doc-done.png` });

  /* 家校沟通 */
  await openSkillMenu(page);
  await page.click('.ch-sub .sub-item[data-skill="family"]');
  await sleep(400);
  const parents = await page.$$eval(".ch-sub .sub-item", (els) => els.map((e) => e.dataset.sub));
  ok("家校沟通二级 4 类家长", parents.length === 4, parents.join(","));

  const cardsBefore = await page.$$eval(".ch-filecard", (els) => els.length);
  await page.click('.ch-sub .sub-item[data-sub="anxious"]');
  await sleep(350);
  const fDraft = await page.$eval('[data-test="chat-input"]', (e) => e.value);
  ok("演练预填说明是哪类家长", fDraft.includes("焦虑型家长"), fDraft);
  const n4 = await answers(page);
  await page.click('[data-test="chat-send"]');
  const open1 = await lastReply(page, n4);
  ok("家长先开口", open1.includes("家长（焦虑型家长）"), open1.slice(0, 30));
  ok("给出潜台词", open1.includes("潜台词"));
  const cardsAfter = await page.$$eval(".ch-filecard", (els) => els.length);
  ok("演练不产文件卡", cardsBefore === cardsAfter, `${cardsBefore}→${cardsAfter}`);
  const chips = await page.$$eval(".ch-suggest .chip", (els) => els.map((e) => e.innerText.trim()));
  ok("给了下一句建议", chips.length >= 2, chips.join(" | "));
  await page.screenshot({ path: `${OUT}/6-family-start.png` });

  const n5 = await answers(page);
  await page.type('[data-test="chat-input"]', "我理解您现在的着急，先说事实：他期中 52 分，缺勤 26 次，作业交了 32/36 次。");
  await page.click('[data-test="chat-send"]');
  const turn2 = await lastReply(page, n5);
  ok("第 2 轮家长接住了", turn2.includes("第 2 轮"), turn2.slice(0, 30));
  await page.screenshot({ path: `${OUT}/7-family-turn2.png` });

  await page.evaluate(() => {
    const el = document.querySelector('[data-test="chat-input"]');
    el.value = "";
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  const n6 = await answers(page);
  await page.type('[data-test="chat-input"]', "复盘");
  await page.click('[data-test="chat-send"]');
  const rev = await lastReply(page, n6);
  ok("能出复盘", rev.includes("复盘") && rev.includes("事实底子"), rev.slice(0, 40));
  await page.screenshot({ path: `${OUT}/8-family-review.png` });

  ok("导员端无 JS 报错", errors.length === 0, errors.slice(0, 2).join(" | "));
  await page.close();
}

console.log(`\n结果：${pass} 通过 / ${fail} 失败`);
await browser.close();
process.exit(fail ? 1 : 0);
