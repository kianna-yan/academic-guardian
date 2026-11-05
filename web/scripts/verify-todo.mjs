/**
 * 待办交互验收：勾选只打勾（留在列表），点右上角叉号才删除。
 *
 * 断言：
 *  1 打开待办 tab 有条目
 *  2 勾选后条目还在（不消失）
 *  3 勾选后 input 真的打勾
 *  4 勾选后该行拿到 done 样式（划横线/淡化）
 *  5 勾完沉到列表下方
 *  6 徽标只数未完成（勾完减 1）
 *  7 再点一次可以取消勾选（勾错了能退回）
 *  8 取消后回到未完成区
 *  9 面板在勾选/取消过程中一直开着
 * 10 叉号存在且可点
 * 11 点叉号后该条消失
 * 12 点叉号不会把面板一起关掉
 * 13 后端也删了（刷新后不复活）
 * 14 勾选状态刷新后保留（勾了但没叉的不复活成未完成）
 * 15 页面无 JS 报错
 */
import puppeteer from "puppeteer-core";
import fs from "node:fs";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8620";
const OUT = "shots_todo";
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
const rows = () =>
  page.evaluate(() =>
    [...document.querySelectorAll(".panel .item.todo")].map((el) => ({
      title: el.querySelector(".item-main b")?.textContent?.trim() || "",
      done: !!el.querySelector('input[type="checkbox"]')?.checked,
      doneCls: el.className.includes("done"),
      hasX: !!el.querySelector(".todo-x"),
    })),
  );
const badge = () =>
  page.evaluate(() => {
    const em = document.querySelectorAll(".panel .tab")[1]?.querySelector("em");
    return em ? Number(em.textContent.trim()) || 0 : 0;
  });

async function clickRowEl(title, sel) {
  const box = await page.evaluate(
    (t, s) => {
      const list = [...document.querySelectorAll(".panel .item.todo")];
      const row = list.find((r) => (r.querySelector(".item-main b")?.textContent || "").trim() === t);
      if (!row) return null;
      const target = s ? row.querySelector(s) : row;
      if (!target) return null;
      const r = target.getBoundingClientRect();
      return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
    },
    title,
    sel,
  );
  if (!box) throw new Error(`找不到待办行：${title}`);
  await page.mouse.click(box.x, box.y);
  await sleep(520);
}

const bell = ".bell-wrap .bell";

/* 登录学生端 */
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

/* 打开面板 → 待办 tab */
await page.click(bell);
await sleep(400);
await page.click(".panel .tab:nth-child(2)");
await sleep(500);
ok("打开待办 tab", await open());

const before = await rows();
ok("待办列表有条目", before.length > 0, `${before.length} 条`);
const badge0 = await badge();
ok("徽标数=未完成数", badge0 === before.filter((r) => !r.done).length, `徽标 ${badge0}`);
await page.screenshot({ path: `${OUT}/1-todo-list.png` });

const first = before[0];
if (!first) {
  console.log("没有待办，后续断言跳过");
} else {
  ok("每行都有右上角叉号", before.every((r) => r.hasX));

  /* 勾选 */
  await clickRowEl(first.title, 'input[type="checkbox"]');
  const afterCheck = await rows();
  ok("勾选后条目仍在列表（不删除）", afterCheck.length === before.length, `${afterCheck.length} 条`);
  const row1 = afterCheck.find((r) => r.title === first.title);
  ok("勾选后打上勾", !!row1?.done);
  ok("勾选后有已完成样式", !!row1?.doneCls);
  ok(
    "勾完沉到列表下方",
    !!row1 && afterCheck.indexOf(row1) === afterCheck.length - 1,
    `位置 ${row1 ? afterCheck.indexOf(row1) : -1}/${afterCheck.length - 1}`,
  );
  ok("徽标只数未完成（-1）", (await badge()) === badge0 - 1, `${badge0} → ${await badge()}`);
  ok("勾选过程面板保持打开", await open());
  await page.screenshot({ path: `${OUT}/2-checked.png` });

  /* 取消勾选 */
  await clickRowEl(first.title, 'input[type="checkbox"]');
  const afterUndo = await rows();
  const row2 = afterUndo.find((r) => r.title === first.title);
  ok("再点一次可取消勾选", !!row2 && !row2.done);
  ok("取消后回到未完成区（不在最后）", !!row2 && afterUndo.indexOf(row2) !== afterUndo.length - 1);
  ok("徽标恢复", (await badge()) === badge0, `${await badge()}`);

  /* 勾上 → 刷新 → 状态保留 */
  await clickRowEl(first.title, 'input[type="checkbox"]');
  await sleep(300);
  await page.reload({ waitUntil: "networkidle2" });
  await sleep(2400);
  await page.click(bell);
  await sleep(400);
  await page.click(".panel .tab:nth-child(2)");
  await sleep(500);
  const afterReload = await rows();
  const rowR = afterReload.find((r) => r.title === first.title);
  ok("刷新后勾选状态保留（仍带勾）", !!rowR && rowR.done);
  ok("刷新后仍留在列表（没被自动删）", afterReload.length === before.length);

  /* 点叉号删除 */
  await clickRowEl(first.title, ".todo-x");
  const afterDrop = await rows();
  ok("点叉号后该条消失", !afterDrop.some((r) => r.title === first.title), `${afterDrop.length} 条`);
  ok("点叉号不会关掉面板", await open());
  await page.screenshot({ path: `${OUT}/3-after-drop.png` });

  /* 后端确认已删 */
  const api1 = await fetch(`${BASE}/api/notifications`, {
    headers: { Authorization: `Bearer ${auth.token}` },
  }).then((r) => r.json());
  ok(
    "后端列表里也没了（真删除）",
    !(api1.todos || []).some((t) => t.title === first.title),
    `后端 ${(api1.todos || []).length} 条`,
  );
  ok(
    "后端未完成计数与前端徽标一致",
    api1.counts?.todo === (await badge()),
    `后端 ${api1.counts?.todo} / 前端 ${await badge()}`,
  );
}

ok("页面无 JS 报错", errors.length === 0, errors.slice(0, 2).join(" | "));

console.log(`\n结果：${pass} 通过 / ${fail} 失败`);
await browser.close();
process.exit(fail ? 1 : 0);
