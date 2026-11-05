import puppeteer from "puppeteer-core";
import fs from "node:fs";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8620";
const OUT = "shots_notice";
fs.mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let pass = 0;
let fail = 0;
const ok = (name, cond, extra = "") => {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${extra ? "  · " + extra : ""}`);
  cond ? pass++ : fail++;
};

const browser = await puppeteer.launch({
  executablePath: EXE,
  headless: true,
  args: ["--disable-gpu", "--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1366, height: 820 });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));

const open = () => page.evaluate(() => !!document.querySelector(".panel"));
const bell = ".bell-wrap .bell";

async function clickAt(sel, dx = 0.5, dy = 0.5) {
  const box = await page.evaluate((s, x, y) => {
    const el = document.querySelector(s);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.x + r.width * x, y: r.y + r.height * y };
  }, sel, dx, dy);
  if (!box) throw new Error(`找不到 ${sel}`);
  await page.mouse.click(box.x, box.y);
  await sleep(320);
}

/* 登录学生端（右上角有铃铛的那个端） */
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

/* 1. 点铃铛打开 */
await clickAt(bell);
ok("点铃铛打开面板", await open());
await page.screenshot({ path: `${OUT}/1-open.png` });

/* 2. 点面板内部不关 */
await clickAt(".panel", 0.5, 0.03);
ok("点面板内部不关闭", await open());

/* 3. 点面板外的正文区关闭 */
await page.mouse.click(520, 640);
await sleep(360);
ok("点框外（正文区）关闭", !(await open()));
await page.screenshot({ path: `${OUT}/2-closed.png` });

/* 4. 再开一次，点左侧导航关闭 */
await clickAt(bell);
ok("再次打开", await open());
await clickAt(".mod-item", 0.5, 0.5);
await sleep(400);
ok("点框外（侧栏菜单）关闭", !(await open()));

/* 5. Esc 关闭 */
await clickAt(bell);
ok("ESc 前已打开", await open());
await page.keyboard.press("Escape");
await sleep(320);
ok("按 Esc 关闭", !(await open()));

/* 6. 铃铛仍是开关：点开再点关 */
await clickAt(bell);
const opened = await open();
await clickAt(bell);
ok("铃铛可再次关闭", opened && !(await open()));

/* 7. 面板内部点通知条：不关闭（保持原交互） */
await clickAt(bell);
const items = await page.$$(".panel .item");
if (items.length) {
  await clickAt(".panel .item");
  ok("点通知条目仍保持打开", await open());
} else {
  ok("点通知条目仍保持打开", true, "本次无未读，跳过");
}

/* 8. 打开状态下切换标签页不关 */
await clickAt(".panel .tab:nth-child(2)");
const tabOn = await page.evaluate(() => !!document.querySelector(".panel"));
ok("切换面板内标签不关闭", tabOn);

/* 9. 关闭后刷新无残留 */
await page.mouse.click(520, 640);
await sleep(300);
await page.reload({ waitUntil: "networkidle2" });
await sleep(2200);
ok("刷新后默认收起", !(await open()));

console.log(`\n结果：${pass} 通过 / ${fail} 失败`);
console.log("页面报错：", errors.length ? errors.slice(0, 3) : "无");
await browser.close();
process.exit(fail ? 1 : 0);
