/** 线上验收：待办勾选只打勾、点叉号才删除。打分享链接实测，不走本地。 */
import puppeteer from "puppeteer-core";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const LINK = process.env.LINK || "https://academic-guardian-56914.app.workbuddy.host/?sharecode=G4NKZPCZAO";
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
await page.setViewport({ width: 1366, height: 820 });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));

const rows = () =>
  page.evaluate(() =>
    [...document.querySelectorAll(".panel .item.todo")].map((el) => ({
      title: el.querySelector(".item-main b")?.textContent?.trim() || "",
      done: !!el.querySelector('input[type="checkbox"]')?.checked,
      doneCls: el.className.includes("done"),
      hasX: !!el.querySelector(".todo-x"),
    })),
  );

async function clickRowEl(title, sel) {
  const box = await page.evaluate(
    (t, s) => {
      const list = [...document.querySelectorAll(".panel .item.todo")];
      const row = list.find((r) => (r.querySelector(".item-main b")?.textContent || "").trim() === t);
      const target = row && (s ? row.querySelector(s) : row);
      if (!target) return null;
      const r = target.getBoundingClientRect();
      return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
    },
    title,
    sel,
  );
  if (!box) throw new Error(`找不到行：${title}`);
  await page.mouse.click(box.x, box.y);
  await sleep(520);
}

await page.goto(LINK, { waitUntil: "networkidle2", timeout: 60000 });
await page.evaluate(() => localStorage.clear());
await page.reload({ waitUntil: "networkidle2" });
await sleep(1800);

/* 学生端登录：点含「学生」的示例账号 */
const picked = await page.evaluate(() => {
  const r = [...document.querySelectorAll(".hint-row")].find((e) => e.innerText.includes("学生"));
  if (!r) return false;
  r.click();
  return true;
});
ok("登录页可选中学生账号", picked);
await sleep(300);
await page.click(".submit");
await page.waitForFunction(() => !location.pathname.includes("login"), { timeout: 30000 });
await sleep(2800);

await page.click(".bell-wrap .bell");
await sleep(500);
await page.click(".panel .tab:nth-child(2)");
await sleep(600);

const before = await rows();
ok("线上待办列表有条目", before.length > 0, `${before.length} 条`);
ok("线上每行都有叉号", before.length > 0 && before.every((r) => r.hasX));
await page.screenshot({ path: "shots_todo/live-1-list.png" });

if (before[0]) {
  const first = before[0];
  await clickRowEl(first.title, 'input[type="checkbox"]');
  const after = await rows();
  const row = after.find((r) => r.title === first.title);
  ok("线上勾选后条目仍在（不删除）", after.length === before.length);
  ok("线上勾选后打勾+置灰", !!row?.done && !!row?.doneCls);
  ok("线上勾完沉底", !!row && after.indexOf(row) === after.length - 1);
  await page.screenshot({ path: "shots_todo/live-2-checked.png" });

  await clickRowEl(first.title, ".todo-x");
  const dropped = await rows();
  ok("线上点叉号后该条消失", !dropped.some((r) => r.title === first.title));
  ok("线上点叉号面板不关", await page.evaluate(() => !!document.querySelector(".panel")));
  await page.screenshot({ path: "shots_todo/live-3-drop.png" });
}

ok("线上页面无 JS 报错", errors.length === 0, errors.slice(0, 2).join(" | "));
console.log(`\n结果：${pass} 通过 / ${fail} 失败`);
await browser.close();
process.exit(fail ? 1 : 0);
