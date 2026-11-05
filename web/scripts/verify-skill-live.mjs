/** 线上验收：+ 菜单的「上传文档 / Skill」是否真的能用（打分享链接，不走本地）。 */
import puppeteer from "puppeteer-core";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const LINK = process.env.LINK || "https://academic-guardian-56914.app.workbuddy.host/?sharecode=G4NKZPCZAO";
const DOCX = "C:/tmp/skilltest/word.docx";
const PDF = "C:/tmp/skilltest/report2.pdf";

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

await page.goto(LINK, { waitUntil: "networkidle2", timeout: 60000 });
await page.evaluate(() => localStorage.clear());
await page.reload({ waitUntil: "networkidle2" });
await sleep(1800);

const picked = await page.evaluate(() => {
  const r = [...document.querySelectorAll(".hint-row")].find((e) => e.innerText.includes("学生"));
  if (!r) return false;
  r.click();
  return true;
});
ok("线上登录页可选学生账号", picked);
await sleep(300);
await page.click(".submit");
await page.waitForFunction(() => !location.pathname.includes("login"), { timeout: 30000 });
await sleep(2800);

await page.click(".ch-plus");
await sleep(500);
const items = await page.$$eval(".ch-menu > button", (els) =>
  els.map((e) => e.innerText.replace(/\s+/g, " ").trim()),
);
ok("线上菜单 4 项", items.length === 4, items.join(" / "));
await page.screenshot({ path: "shots_skill/live-1-menu.png" });

await page.evaluate(() => {
  [...document.querySelectorAll(".ch-menu > button")].find((b) => b.innerText.includes("Skill")).click();
});
await sleep(600);
const subs = await page.$$eval(".ch-sub .sub-item", (els) => els.map((e) => e.dataset.skill));
ok("线上二级菜单 4 个技能", subs.length === 4, subs.join(","));
await page.screenshot({ path: "shots_skill/live-2-skill.png" });

await page.click('.ch-sub .sub-item[data-skill="ppt"]');
await sleep(400);
await page.click('[data-test="chat-send"]');
await page.waitForSelector(".ch-filecard", { timeout: 20000 });
await page.waitForFunction(() => document.querySelector(".ch-filecard.ok, .ch-filecard.fail"), {
  timeout: 90000,
});
const card = await page.$eval(".ch-filecard", (el) => ({
  cls: el.className,
  name: el.querySelector(".fc-body b")?.textContent?.trim() || "",
  href: el.querySelector(".fc-dl")?.getAttribute("href") || "",
}));
ok("线上 PPT 生成成功", card.cls.includes("ok"), card.name);
ok("文件名以 .pptx 结尾", card.name.endsWith(".pptx"));
ok("可下载（blob 链接）", card.href.startsWith("blob:"));
await page.screenshot({ path: "shots_skill/live-3-card.png" });

/* 上传文档：docx */
async function upload(path, tag) {
  const input = await page.$('input[accept*=".pdf"]');
  await input.uploadFile(path);
  await sleep(1200);
  const row = await page.$eval(".ch-attach-item", (el) => ({
    name: el.querySelector(".nm")?.textContent?.trim() || "",
    size: el.querySelector(".sz")?.textContent?.trim() || "",
  })).catch(() => null);
  ok(`线上上传 ${tag}`, !!row && /\d+\s*字/.test(row.size), row ? `${row.name} · ${row.size}` : "没读到");
  // 清掉，别影响下一次
  await page.evaluate(() => document.querySelector(".ch-attach-x")?.click());
  await sleep(300);
}
await upload(DOCX, "Word");
await upload(PDF, "PDF");
await page.screenshot({ path: "shots_skill/live-4-doc.png" });

ok("线上页面无 JS 报错", errors.length === 0, errors.slice(0, 2).join(" | "));
console.log(`\n结果：${pass} 通过 / ${fail} 失败`);
await browser.close();
process.exit(fail ? 1 : 0);
