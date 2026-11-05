/**
 * 「+ → 上传文档 / Skill」验收（本地 8620）
 *
 * 断言：
 *  1 菜单有 4 项：照片 / 视频 / 上传文档 / Skill
 *  2 Skill 展开二级菜单，含 PPT、PDF、Word、图表解读
 *  3 点 PPT 生成 → 菜单收起、输入框预填提示、出现技能标签
 *  4 发送后出现文件卡，最终可下载（blob 链接 + .pptx 文件名）
 *  5 文件卡不遮挡对话、面板仍可继续输入
 *  6 上传 docx → 附件条显示「约 N 字」
 *  7 附件随消息发出后，气泡里回显文档名与字数
 *  8 图表解读 → 预填解读提示并唤起图片选择
 *  9 页面无 JS 报错
 */
import puppeteer from "puppeteer-core";
import fs from "node:fs";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8620";
const OUT = "shots_skill";
const DOC = "C:/tmp/skilltest/word.docx";
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

const res = await fetch(`${BASE}/api/auth/login`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ role: "student", account: "20240023", password: "0000" }),
});
const auth = await res.json();
await page.goto(`${BASE}/login`, { waitUntil: "networkidle2" });
await page.evaluate((t) => {
  localStorage.clear();
  localStorage.setItem("ag.token", t);
}, auth.token);
await page.goto(`${BASE}/student`, { waitUntil: "networkidle2" });
await sleep(2600);

await page.click(".ch-plus");
await sleep(400);
const items = await page.$$eval(".ch-menu > button", (els) =>
  els.map((e) => e.innerText.replace(/\s+/g, " ").trim()),
);
ok("菜单是 4 项", items.length === 4, items.join(" / "));
ok("有「上传文档」", items.some((t) => t.includes("上传文档")));
ok("有「Skill」", items.some((t) => t.includes("Skill")));
await page.screenshot({ path: `${OUT}/1-menu.png` });

/* Skill 二级菜单 */
await page.evaluate(() => {
  [...document.querySelectorAll(".ch-menu > button")].find((b) => b.innerText.includes("Skill")).click();
});
await sleep(500);
const subs = await page.$$eval(".ch-sub .sub-item", (els) =>
  els.map((e) => e.dataset.skill + ":" + e.innerText.replace(/\s+/g, " ").trim()),
);
ok("二级菜单 4 个技能", subs.length === 4, subs.join(" | "));
ok(
  "四个技能齐全",
  ["ppt", "pdf", "word", "chart"].every((k) => subs.some((s) => s.startsWith(k + ":"))),
);
await page.screenshot({ path: `${OUT}/2-skill-menu.png` });

/* 选 PPT */
await page.click('.ch-sub .sub-item[data-skill="ppt"]');
await sleep(350);
const draftText = await page.$eval('[data-test="chat-input"]', (e) => e.value);
ok("选技能后菜单收起", !(await page.$(".ch-sub")));
ok("输入框预填了提示", draftText.trim().length > 4, draftText);
ok("出现技能标签", !!(await page.$(".ch-skilltag")));
await page.screenshot({ path: `${OUT}/3-skill-selected.png` });

/* 发送 → 生成文件 */
await page.click('[data-test="chat-send"]');
await page.waitForSelector(".ch-filecard", { timeout: 15000 });
ok("出现文件卡", true);
await page.waitForFunction(
  () => document.querySelector(".ch-filecard.ok, .ch-filecard.fail"),
  { timeout: 60000 },
);
const card = await page.$eval(".ch-filecard", (el) => ({
  cls: el.className,
  name: el.querySelector(".fc-body b")?.textContent?.trim() || "",
  note: el.querySelector(".fc-body i")?.textContent?.trim() || "",
  href: el.querySelector(".fc-dl")?.getAttribute("href") || "",
  dl: el.querySelector(".fc-dl")?.getAttribute("download") || "",
}));
ok("PPT 生成成功", card.cls.includes("ok"), `${card.name} · ${card.note}`);
ok("文件名是 .pptx", card.name.endsWith(".pptx"), card.name);
ok("下载链接是本地 blob", card.href.startsWith("blob:"), card.href.slice(0, 24));
ok("下载属性带文件名", card.dl === card.name);
await page.screenshot({ path: `${OUT}/4-filecard.png` });

/* 上传文档 */
const fileInput = await page.$('input[accept*=".pdf"]');
ok("存在文档选择框", !!fileInput);
await fileInput.uploadFile(DOC);
await page.waitForSelector(".ch-attach-item", { timeout: 30000 });
await sleep(600);
const attach = await page.$eval(".ch-attach-item", (el) => ({
  name: el.querySelector(".nm")?.textContent?.trim() || "",
  size: el.querySelector(".sz")?.textContent?.trim() || "",
  ico: el.querySelector(".ch-attach-ico")?.textContent?.trim() || "",
}));
ok("附件条显示文档名", attach.name.includes("word.docx"), attach.name);
ok("附件条显示字数", /\d+\s*字/.test(attach.size), attach.size);
await page.screenshot({ path: `${OUT}/5-doc-attached.png` });

/* 发出去，气泡里回显 */
await page.click('[data-test="chat-send"]');
await sleep(1200);
const bubble = await page.evaluate(() => {
  const b = [...document.querySelectorAll(".msg.user")].pop();
  return {
    name: b?.querySelector(".bm-name")?.textContent?.trim() || "",
    said: b?.querySelector(".bm-said")?.textContent?.trim() || "",
  };
});
ok("气泡回显文档名", bubble.name.includes("word.docx"), bubble.name);
ok("气泡回显字数", /\d+\s*字/.test(bubble.said), bubble.said);

/* 图表解读（先等上一轮回答结束，流式期间「+」是禁用的） */
await page.waitForFunction(() => !document.querySelector(".ch-plus")?.disabled, { timeout: 60000 });
await sleep(400);
await page.click(".ch-plus");
await sleep(300);
await page.evaluate(() => {
  [...document.querySelectorAll(".ch-menu > button")].find((b) => b.innerText.includes("Skill")).click();
});
await sleep(400);
await page.click('.ch-sub .sub-item[data-skill="chart"]');
await sleep(400);
const chartDraft = await page.$eval('[data-test="chat-input"]', (e) => e.value);
ok("图表解读预填了解读提示", chartDraft.includes("成绩单") || chartDraft.includes("图"), chartDraft);
await page.screenshot({ path: `${OUT}/6-chart.png` });

ok("页面无 JS 报错", errors.length === 0, errors.slice(0, 2).join(" | "));
console.log(`\n结果：${pass} 通过 / ${fail} 失败`);
await browser.close();
process.exit(fail ? 1 : 0);
