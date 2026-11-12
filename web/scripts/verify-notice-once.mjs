// 消息弹窗纪律：一个端只播一次，叉掉后回门户不重播，刷新也不重播
import puppeteer from "puppeteer-core";
import fs from "node:fs";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8620";
const OUT = "shots_notice";
fs.mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let pass = 0;
const ok = (name, cond, extra = "") => {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${extra ? "  · " + extra : ""}`);
  if (cond) pass++;
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

const countNtf = (page) =>
  page.evaluate(() => {
    const el = document.querySelector(".ntf-stack");
    return el ? el.querySelectorAll(".ntf").length : 0;
  });

const tk = await token("student", "20240221", "0000");
const browser = await puppeteer.launch({
  executablePath: EXE,
  headless: true,
  args: ["--disable-gpu", "--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 900 });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));

await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
await page.evaluate((t) => {
  localStorage.setItem("ag.token", t);
  sessionStorage.clear();
}, tk);
await page.reload({ waitUntil: "domcontentloaded" });
await sleep(1800);
await page.evaluate(() => {
  document.querySelectorAll(".v11-veil,.star-wipe,.pre-veil").forEach((n) => n.remove());
  document.documentElement.classList.remove("v11-veil");
});
await page.evaluate(() => {
  [...document.querySelectorAll("button")].find((n) => n.textContent.trim() === "继续进入")?.click();
});
await sleep(3500);

/* 1. 首次进门：应有 3 条 */
const first = await countNtf(page);
ok("① 首次进场弹出消息", first > 0, `${first} 条`);
await page.screenshot({ path: `${OUT}/1-first.png` });

/* 2. 全部叉掉 */
await page.evaluate(() => {
  [...document.querySelectorAll(".ntf-x")].forEach((b) => b.click());
});
await sleep(600);
const afterClose = await countNtf(page);
ok("② 叉掉后清空", afterClose === 0, `${afterClose} 条`);

/* 3. 进板块再回门户：不应重播（本轮核心） */
await page.evaluate(() => document.querySelector('.pt-node[data-node="overview"]')?.click());
await sleep(3200);
const onSection = await countNtf(page);
ok("③ 板块页本来就不显示", onSection === 0, `${onSection} 条`);

await page.evaluate(() => document.querySelector('[data-test="back-home"]')?.click());
await sleep(3200);
const backHome = await countNtf(page);
ok("④ 返回门户不重播", backHome === 0, `${backHome} 条`);
await page.screenshot({ path: `${OUT}/2-back-home.png` });

/* 4. 再进再回，多轮也不重播 */
for (let i = 0; i < 2; i++) {
  await page.evaluate(() => document.querySelector('.pt-node[data-node="resources"]')?.click());
  await sleep(2600);
  await page.evaluate(() => document.querySelector('[data-test="back-home"]')?.click());
  await sleep(2600);
}
const afterLoops = await countNtf(page);
ok("⑤ 反复进出仍不重播", afterLoops === 0, `${afterLoops} 条`);

/* 5. 刷新页面：同一标签页也不重播 */
await page.reload({ waitUntil: "domcontentloaded" });
await sleep(2000);
await page.evaluate(() => {
  document.querySelectorAll(".v11-veil,.star-wipe,.pre-veil").forEach((n) => n.remove());
  document.documentElement.classList.remove("v11-veil");
  [...document.querySelectorAll("button")].find((n) => n.textContent.trim() === "继续进入")?.click();
});
await sleep(3200);
const afterReload = await countNtf(page);
ok("⑥ 刷新页面不重播", afterReload === 0, `${afterReload} 条`);
await page.screenshot({ path: `${OUT}/3-reload.png` });

/* 6. 模拟重新登录（清掉本会话记号）：应重新报到 */
await page.evaluate(() => {
  Object.keys(sessionStorage)
    .filter((k) => k.startsWith("ag.notice."))
    .forEach((k) => sessionStorage.removeItem(k));
});
await page.reload({ waitUntil: "domcontentloaded" });
await sleep(1800);
await page.evaluate(() => {
  document.querySelectorAll(".v11-veil,.star-wipe,.pre-veil").forEach((n) => n.remove());
  document.documentElement.classList.remove("v11-veil");
  [...document.querySelectorAll("button")].find((n) => n.textContent.trim() === "继续进入")?.click();
});
await sleep(3200);
const reLogin = await countNtf(page);
ok("⑦ 重新登录会重新报到", reLogin > 0, `${reLogin} 条`);

ok("无 JS 报错", errors.length === 0, errors.slice(0, 2).join(" / "));
await browser.close();
console.log(`\n共 ${pass} 项通过`);
