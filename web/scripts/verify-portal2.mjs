import puppeteer from "puppeteer-core";

/**
 * 门户改版验收：
 * ① 五个端首屏只有画布，节点数 = 清单条目数，没有侧栏、没有看板卡片、不滚动
 * ② 点节点是「直接换页」，只渲染那一块，其它版块不出现
 * ③ 内页有「返回门户」，AI 抽屉能从内页唤起
 * ④ 旧锚点地址自动改写成新路由
 */
const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8620";
const OUT = "C:/Users/lenovo/WorkBuddy/2026-11-03-16-18-31/_v8/shots_portal2";

let pass = 0;
let fail = 0;
const ok = (cond, name, extra = "") => {
  if (cond) pass++;
  else fail++;
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${extra ? "  " + extra : ""}`);
};

async function token(role, account, password) {
  const r = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ role, account, password }),
  });
  return (await r.json()).token;
}

const ACC = {
  student: ["20240023", "0000", "/student", 11],
  counselor: ["2024014589", "1111", "/counselor", 4],
  admin: ["1234567899", "2222", "/admin", 5],
  teacher: ["2024014501", "4444", "/teacher", 3],
  parent: ["20240067", "3333", "/parent", 3],
};

const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox"] });

function newPage(t) {
  return (async () => {
    const p = await b.newPage();
    await p.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
    await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
    return p;
  })();
}

/* ---------------- ① 首屏：只有画布 ---------------- */
for (const [role, [acc, pwd, path, count]] of Object.entries(ACC)) {
  const t = await token(role, acc, pwd);
  const p = await newPage(t);
  const errs = [];
  p.on("pageerror", (e) => errs.push(e.message));
  await p.goto(BASE + path, { waitUntil: "networkidle2" });
  await new Promise((s) => setTimeout(s, 2200));
  const info = await p.evaluate(() => {
    const view = document.querySelector(".view");
    return {
      nodes: document.querySelectorAll("[data-node]").length,
      sidebar: !!document.querySelector(".sidebar"),
      modItem: document.querySelectorAll(".mod-item").length,
      cards: document.querySelectorAll(".card").length,
      bands: document.querySelectorAll(".region-band, .region").length,
      scrollable: (view?.scrollHeight || 0) > (view?.clientHeight || 0) + 4,
      dock: !!document.querySelector('[data-test="ai-dock"]'),
    };
  });
  ok(info.nodes === count, `${role} 节点数 = 清单条目数`, `${info.nodes}/${count}`);
  ok(!info.sidebar && info.modItem === 0, `${role} 左侧任务栏已删除`);
  ok(info.cards === 0, `${role} 首屏没有看板卡片`, `cards=${info.cards}`);
  ok(info.bands === 0, `${role} 首屏没有版块标题条`, `bands=${info.bands}`);
  ok(!info.scrollable, `${role} 首屏不出现滚动（一屏放得下）`);
  ok(info.dock, `${role} 底部 AI 输入条还在`);
  ok(errs.length === 0, `${role} 无控制台报错`, errs[0] || "");

  // 点第一个普通节点 → 必须换地址（不是原地滚动）
  const before = await p.evaluate(() => location.pathname);
  await p.evaluate(() => {
    const n = [...document.querySelectorAll("[data-node]")].find((x) => x.dataset.node !== "chat");
    n.click();
  });
  await new Promise((s) => setTimeout(s, 1400));
  const after = await p.evaluate(() => ({
    path: location.pathname,
    top: document.querySelector(".view")?.scrollTop,
    cards: document.querySelectorAll(".card").length,
    back: !!document.querySelector('[data-test="back-home"]'),
  }));
  ok(after.path !== before, `${role} 点节点直接跳转（URL 变了）`, `${before} → ${after.path}`);
  // 家校沟通是独立页面（不是卡片布局），其余节点进去都应该带内容
  ok(after.cards > 0 || after.path === "/messages", `${role} 跳转后只显示点开的那一块`, `cards=${after.cards}`);
  ok(after.back, `${role} 内页有「返回门户」`);
  await p.close();
}

/* ---------------- ② 学生端逐节点：进去只看到那一块 ---------------- */
{
  const t = await token("student", "20240023", "0000");
  const p = await newPage(t);
  await p.goto(BASE + "/student", { waitUntil: "networkidle2" });
  await new Promise((s) => setTimeout(s, 2200));

  const cases = [
    { key: "overview", has: ["学业总览", "风险从哪里来"], not: ["成绩走势 · 从大一到这学期", "课堂考勤 · 具体到每一天", "对数据或评分有异议"] },
    { key: "grade", has: ["成绩走势 · 从大一到这学期"], not: ["风险从哪里来", "课堂考勤 · 具体到每一天"] },
    { key: "records", has: ["课堂考勤 · 具体到每一天", "作业清单 · 要交什么写清楚"], not: ["成绩走势 · 从大一到这学期", "风险从哪里来"] },
    { key: "appeal", has: ["对数据或评分有异议"], not: ["课堂考勤 · 具体到每一天", "风险从哪里来"] },
    { key: "schedule", has: ["课表"], not: ["风险从哪里来"] },
    { key: "tree", has: ["智慧树"], not: ["风险从哪里来"] },
  ];

  for (const c of cases) {
    await p.goto(BASE + "/student", { waitUntil: "networkidle2" });
    await new Promise((s) => setTimeout(s, 1600));
    await p.evaluate((k) => document.querySelector(`[data-node="${k}"]`).click(), c.key);
    await new Promise((s) => setTimeout(s, 1800));
    const txt = await p.evaluate(() => document.querySelector(".view")?.innerText || "");
    const url = await p.evaluate(() => location.pathname);
    const hit = c.has.every((w) => txt.includes(w));
    const clean = c.not.every((w) => !txt.includes(w));
    ok(hit, `student/${c.key} 进去看到该版块`, url);
    ok(clean, `student/${c.key} 其它版块没露出来`);
  }
  await p.close();
}

/* ---------------- ③ 教务/辅导员/教师/家长 的版块页 ---------------- */
{
  const groups = [
    { role: "admin", acc: "1234567899", pwd: "2222", home: "/admin", cases: [
      { path: "/admin/board", has: "风险等级分布", not: "预警规则配置" },
      { path: "/admin/rules", has: "预警规则配置", not: "风险等级分布" },
      { path: "/admin/accounts", has: "账号", not: "预警规则配置" },
    ]},
    { role: "counselor", acc: "2024014589", pwd: "1111", home: "/counselor", cases: [
      { path: "/counselor/roster", has: "风险名单", not: "智慧森林" },
      { path: "/counselor/forest", has: "智慧森林", not: "风险名单（共" },
    ]},
    { role: "teacher", acc: "2024014501", pwd: "4444", home: "/teacher", cases: [
      { path: "/teacher/classroom", has: "课堂", not: "" },
    ]},
    { role: "parent", acc: "20240067", pwd: "3333", home: "/parent", cases: [
      { path: "/parent/overview", has: "学校正在做什么", not: "" },
    ]},
  ];

  for (const g of groups) {
    const t = await token(g.role, g.acc, g.pwd);
    const p = await newPage(t);
    for (const c of g.cases) {
      await p.goto(BASE + c.path, { waitUntil: "networkidle2" });
      await new Promise((s) => setTimeout(s, 1800));
      const txt = await p.evaluate(() => document.querySelector(".view")?.innerText || "");
      ok(txt.includes(c.has), `${g.role} ${c.path} 内容正确`);
      if (c.not) ok(!txt.includes(c.not), `${g.role} ${c.path} 未混入其它版块`);
    }
    // 返回门户
    await p.click('[data-test="back-home"]');
    await new Promise((s) => setTimeout(s, 1200));
    const home = await p.evaluate(() => ({ path: location.pathname, nodes: document.querySelectorAll("[data-node]").length }));
    ok(home.path === g.home && home.nodes > 0, `${g.role} 返回门户回到画布`, home.path);
    await p.close();
  }
}

/* ---------------- ④ 旧锚点地址自动改写 ---------------- */
{
  const t = await token("student", "20240023", "0000");
  const p = await newPage(t);
  for (const [old, want] of [["/student#grade", "/student/grade"], ["/student#records", "/student/records"], ["/student#appeal", "/student/appeal"]]) {
    await p.goto(BASE + old, { waitUntil: "networkidle2" });
    await new Promise((s) => setTimeout(s, 1500));
    const path = await p.evaluate(() => location.pathname);
    ok(path === want, `老地址 ${old} 改写为 ${want}`, path);
  }
  await p.close();
}

/* ---------------- ⑤ AI 抽屉：门户与内页都能唤起 ---------------- */
{
  const t = await token("student", "20240023", "0000");
  const p = await newPage(t);
  await p.goto(BASE + "/student", { waitUntil: "networkidle2" });
  await new Promise((s) => setTimeout(s, 2200));
  await p.click('[data-test="ai-dock"]');
  await new Promise((s) => setTimeout(s, 900));
  const sheet = await p.evaluate(() => {
    const el = document.querySelector(".ai-sheet");
    const r = el?.getBoundingClientRect();
    return { open: !!el, w: Math.round(r?.width || 0), h: Math.round(r?.height || 0), left: Math.round(r?.left || 0) };
  });
  ok(sheet.open && sheet.w >= 1400 && sheet.left <= 2, "点 AI 条：抽屉铺满整个窗口", `${sheet.w}×${sheet.h} left=${sheet.left}`);
  await p.click('[data-test="sheet-close"]');
  await new Promise((s) => setTimeout(s, 800));
  const closed = await p.evaluate(() => ({ sheet: !!document.querySelector(".ai-sheet"), nodes: document.querySelectorAll("[data-node]").length }));
  ok(!closed.sheet && closed.nodes > 0, "收起后回到门户画布");

  // 画布上的「学业对话」节点：唤起抽屉，不是跳页
  const beforeChat = await p.evaluate(() => location.pathname);
  await p.click('[data-node="chat"]');
  await new Promise((s) => setTimeout(s, 900));
  const chatNode = await p.evaluate(() => ({
    sheet: !!document.querySelector(".ai-sheet"),
    path: location.pathname,
  }));
  ok(chatNode.sheet && chatNode.path === beforeChat, "点「学业对话」节点唤起抽屉（不跳页）", chatNode.path);
  await p.keyboard.press("Escape");
  await new Promise((s) => setTimeout(s, 700));
  ok(!(await p.evaluate(() => !!document.querySelector(".ai-sheet"))), "Esc 收起抽屉");
  await p.screenshot({ path: `${OUT}/student_portal_final.png` });

  // 内页唤起
  await p.goto(BASE + "/student/grade", { waitUntil: "networkidle2" });
  await new Promise((s) => setTimeout(s, 1800));
  // 右上角的消息弹窗会盖住顶栏，先关掉（这也是真实用户会做的事）
  await p.evaluate(() => document.querySelectorAll(".el-notification__closeBtn").forEach((b) => b.click()));
  await new Promise((s) => setTimeout(s, 500));
  await p.click('[data-test="back-ai"]');
  await new Promise((s) => setTimeout(s, 900));
  ok(await p.evaluate(() => !!document.querySelector(".ai-sheet")), "内页「问 AI」能唤起抽屉");
  await p.close();
}

/* ---------------- ⑥ 手机端 ---------------- */
{
  const t = await token("student", "20240023", "0000");
  const p = await b.newPage();
  await p.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
  await p.goto(BASE + "/student", { waitUntil: "networkidle2" });
  await new Promise((s) => setTimeout(s, 2200));
  const m = await p.evaluate(() => ({
    nodes: document.querySelectorAll("[data-node]").length,
    dock: !!document.querySelector('[data-test="ai-dock"]'),
    sidebar: !!document.querySelector(".sidebar"),
    overflowX: document.documentElement.scrollWidth > window.innerWidth + 2,
  }));
  ok(m.nodes === 11 && m.dock && !m.sidebar, "手机端 390：11 个节点 + AI 条，无侧栏");
  ok(!m.overflowX, "手机端无横向溢出");
  await p.screenshot({ path: `${OUT}/student_mobile.png` });
  await p.close();
}

await b.close();
console.log(`\n${pass}/${pass + fail} 通过`);
process.exit(fail ? 1 : 0);
