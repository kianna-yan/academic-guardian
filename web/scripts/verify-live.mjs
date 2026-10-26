/**
 * 线上复验（对话即首页 + 文书导出版）：发布后跑同一套验收。
 * 与 verify-agent.mjs 的差异：BASE 线上域名；首访 ?sharecode= 种网关 Cookie；超时放宽；
 * 浏览器直连（网关健康时 WorkBuddy 客户端网络层可解析内部域名），LIVE_PROXY 可强制代理。
 * 用法：node scripts/verify-live.mjs
 */
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = process.env.BASE_URL || "https://academic-guardian.app.workbuddy.host";
const OUT = process.env.OUT_DIR || "shots_live";
mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
function check(name, ok, extra = "") {
  results.push({ name, ok, extra });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  " + extra : ""}`);
}

const browser = await puppeteer.launch({
  executablePath: EXE,
  headless: true,
  args: [
    "--disable-gpu",
    "--no-sandbox",
    "--font-render-hinting=none",
    ...(process.env.LIVE_PROXY ? [`--proxy-server=${process.env.LIVE_PROXY}`] : []),
  ],
});
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 940 });

// ---- 首访：带 sharecode 种网关 Cookie（无 Cookie 任何路径 403）----
const SHARECODE = process.env.SHARECODE || "XNKLXQ7EPB";
await page.goto(`${BASE}/?sharecode=${SHARECODE}`, { waitUntil: "domcontentloaded", timeout: 60000 });
await sleep(1500);

const errors = [];
page.on("console", (m) => {
  if (m.type() === "error") errors.push(`console: ${m.text()}`);
});
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("requestfailed", (r) => {
  const u = r.url();
  if (u.startsWith(BASE)) errors.push(`requestfailed: ${u} ${r.failure()?.errorText}`);
});

async function loginAs(role, account, password) {
  const res = await page.evaluate(
    async (body) => {
      const r = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      return { status: r.status, data: await r.json().catch(() => ({})) };
    },
    { role, account, password },
  );
  if (!res.data?.token) throw new Error(`登录失败 ${role}: ${JSON.stringify(res.data)}`);
  await page.evaluate((t) => localStorage.setItem("ag.token", t), res.data.token);
  return res.data.profile;
}

/** 在整页对话里发一句话，等流式回答真正结束（按钮恢复、光标消失） */
async function ask(text, { wait = 45000 } = {}) {
  // 上一轮流式还在跑就先等完，否则 send() 会被 streaming 守卫静默丢弃。
  // 不能用 disabled 判断：输入框为空时按钮本来就 disabled，永远等不到。
  await page.waitForFunction(
    () => {
      const btn = document.querySelector(".ch-draft button[type=submit]");
      return !btn || !btn.textContent.includes("…");
    },
    { timeout: 20000, polling: 200 },
  );
  const input = await page.$(".ch-draft input");
  if (!input) throw new Error("整页对话输入框不存在");
  await input.click({ clickCount: 3 });
  await page.keyboard.type(text, { delay: 6 });
  await page.keyboard.press("Enter");
  // 结束条件：最后一条助手消息有正文、无 spinner、无打字光标
  await page.waitForFunction(
    () => {
      const msgs = document.querySelectorAll(".chat-stream .msg");
      const last = msgs[msgs.length - 1];
      if (!last || last.classList.contains("user")) return false;
      if (last.querySelector(".spinner")) return false;
      if (last.querySelector(".typing-caret")) return false;
      const bubble = last.querySelector(".bubble");
      return !!bubble && bubble.textContent.trim().length > 0;
    },
    { timeout: wait, polling: 250 },
  );
  await sleep(300);
}

const lastAssistant = () =>
  page.evaluate(() => {
    const msgs = [...document.querySelectorAll(".chat-stream .msg")];
    const last = msgs.reverse().find((m) => !m.classList.contains("user"));
    return {
      text: last?.querySelector(".bubble")?.textContent || "",
      thoughts: [...(last?.querySelectorAll(".thought-line") || [])].map((t) => t.textContent.trim()),
      intent: last?.querySelector(".chat-intent")?.textContent || "",
      tools: [...(last?.querySelectorAll(".trace-step") || [])].map((t) => t.textContent.trim()),
    };
  });

/** 取最后一条助手消息里的下载链接（已由前端补 ag_token） */
const lastLink = () =>
  page.evaluate(() => {
    const msgs = [...document.querySelectorAll(".chat-stream .msg")];
    const last = msgs.reverse().find((m) => !m.classList.contains("user"));
    const a = last?.querySelector(".bubble a[href*='/api/export/']");
    return a ? { href: a.href, text: a.textContent.trim() } : null;
  });

/** 在页面上下文里 fetch 下载链接，回状态码 + 文件魔数 */
const fetchFile = (href) =>
  page.evaluate(async (url) => {
    const r = await fetch(url);
    const buf = new Uint8Array(await r.arrayBuffer()).subarray(0, 4);
    return { status: r.status, magic: String.fromCharCode(...buf), type: r.headers.get("content-type") || "" };
  }, href);

/** 从整页对话进入数据看板 */
async function goDash() {
  await page.click(".ch-go-dash");
  await page.waitForSelector(".dash-nav", { timeout: 25000 });
}

/** 从看板回到整页对话 */
async function backChat() {
  await page.click("[data-test=back-chat]");
  await page.waitForSelector(".chat-home", { timeout: 25000 });
}

// ============================================================
// 一、学生端：进页面即整页对话 + 简报 + 按键前往看板 + 图表问 AI
// ============================================================
await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
await loginAs("student", "20240001", "0000");
await page.goto(`${BASE}/student`, { waitUntil: "networkidle0" });
await sleep(1800);

const homeState = await page.evaluate(() => ({
  chatHome: !!document.querySelector(".chat-home"),
  input: !!document.querySelector(".ch-draft input"),
  noDash: !document.querySelector(".dash-nav"),
  noRiskHero: !document.querySelector(".risk-hero"),
  goDashBtn: document.querySelector(".ch-go-dash")?.textContent.trim() || "",
}));
check("进学生端就是整页 AI 问答", homeState.chatHome && homeState.input);
check("对话页没有看板内容（风险主卡不在）", homeState.noDash && homeState.noRiskHero);
check("头部有「前往看板」按键", homeState.goDashBtn.includes("学情档案"), homeState.goDashBtn);
await page.screenshot({ path: `${OUT}/agent_home_student.png`, fullPage: false });

let briefing = await page.evaluate(() => ({
  exists: !!document.querySelector(".briefing"),
  greet: document.querySelector(".b-greet")?.textContent || "",
  points: document.querySelectorAll(".b-point").length,
  asks: document.querySelectorAll(".b-asks .chip").length,
}));
check("整页对话里 AI 先开口（主动简报）", briefing.exists);
check("简报问候语是打字机推进", briefing.greet.length > 6, `len=${briefing.greet.length}`);
// 等打字机跑完
await sleep(4000);
briefing = await page.evaluate(() => ({
  points: document.querySelectorAll(".b-point").length,
  asks: document.querySelectorAll(".b-asks .chip").length,
}));
check("简报要点逐条出现", briefing.points >= 3, `points=${briefing.points}`);
check("简报追问按钮出现", briefing.asks >= 2, `asks=${briefing.asks}`);

// 按键前往数据看板
await goDash();
await page.waitForSelector(".risk-hero", { timeout: 25000 });
const dashState = await page.evaluate(() => ({
  dashNav: !!document.querySelector(".dash-nav"),
  backBtn: document.querySelector("[data-test=back-chat]")?.textContent.trim() || "",
  askAi: !!document.querySelector(".card .ask-ai"),
  hasTrendCard: [...document.querySelectorAll(".card-head h3")].some((h) => h.textContent.includes("成绩走势")),
}));
check("按键进入学情看板", dashState.dashNav && dashState.hasTrendCard);
check("看板顶部有「回到 AI 对话」", dashState.backBtn.includes("回到 AI 对话"), dashState.backBtn);
check("看板走势卡上有「问 AI」按钮", dashState.askAi);
await page.screenshot({ path: `${OUT}/agent_dash_student.png`, fullPage: false });

// 看板图表上的「问 AI」：自动回到整页并发问
const askBtn = await page.$(".card .ask-ai");
if (askBtn) {
  await askBtn.click();
  await page.waitForSelector(".chat-home", { timeout: 25000 });
  check("点「问 AI」自动回到整页对话", true);
  await page.waitForFunction(
    () => {
      const msgs = document.querySelectorAll(".chat-stream .msg");
      const last = msgs[msgs.length - 1];
      if (!last || last.classList.contains("user")) return false;
      if (last.querySelector(".spinner") || last.querySelector(".typing-caret")) return false;
      const bubble = last.querySelector(".bubble");
      return !!bubble && bubble.textContent.trim().length > 0;
    },
    { timeout: 20000, polling: 250 },
  );
  await sleep(300);
  const a = await lastAssistant();
  check("图表追问收到回答", a.text.includes("走势") || a.text.includes("分") || a.text.length > 30, a.text.slice(0, 40));
  check("思考链在整页对话里渲染", a.thoughts.length >= 1, a.thoughts[0] || "无");
  await page.screenshot({ path: `${OUT}/agent_chat_thought.png`, fullPage: false });
}

// 「回到 AI 对话」按键本身也能往返
await goDash();
await backChat();
check("看板一键回到对话", !!(await page.$(".chat-home")));

// 学生端也能在对话里导自己的告知函
await ask("导出我的告知函");
let sLink = await lastLink();
check("学生对话里导出告知函给出链接", !!sLink, sLink?.text || "无");
if (sLink) {
  const f = await fetchFile(sLink.href);
  check("告知函 Word 真实可下载", f.status === 200 && f.magic.startsWith("PK"), `${f.status} ${f.magic}`);
}

// ============================================================
// 二、辅导员端：多轮指代全链路（直接在整页对话里进行）
// ============================================================
await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
await loginAs("counselor", "2024014589", "1111");
await page.goto(`${BASE}/counselor`, { waitUntil: "networkidle0" });
await sleep(2500);
const cb = await page.evaluate(() => ({
  chatHome: !!document.querySelector(".chat-home"),
  exists: !!document.querySelector(".briefing"),
  greet: document.querySelector(".b-greet")?.textContent || "",
  points: document.querySelectorAll(".b-point").length,
  goDashBtn: document.querySelector(".ch-go-dash")?.textContent.trim() || "",
}));
check("进辅导员端就是整页对话", cb.chatHome);
check("辅导员端有主动简报", cb.exists && cb.points >= 3, `points=${cb.points}`);
check("辅导员简报按名下学生过滤", cb.greet.includes("刘老师") || cb.points >= 3, cb.greet.slice(0, 24));
check("辅导员按键文案是预警名单", cb.goDashBtn.includes("预警名单"), cb.goDashBtn);
await page.screenshot({ path: `${OUT}/agent_brief_counselor.png`, fullPage: false });

// 第一轮：要上升名单
await ask("本班谁的风险上升最快？");
let r = await lastAssistant();
check("风险上升名单有内容", /上升最快/.test(r.text) || /风险分/.test(r.text), r.text.slice(0, 36));
check("名单回答带思考链", r.thoughts.length >= 1, r.thoughts[0] || "无");
check("工具轨迹含查名单", r.tools.some((t) => t.includes("查风险名单")) || r.tools.some((t) => t.includes("拉")), r.tools.join(",").slice(0, 50));

// 第二轮：第 2 个
await ask("第 2 个的情况展开说说");
r = await lastAssistant();
check("「第 2 个」指代消解成功", r.thoughts.some((t) => t.includes("第2个") || t.includes("指的是")), r.thoughts[0] || "无");
check("指代后回答的是具体学生", /风险分/.test(r.text) && /拆开看/.test(r.text), r.text.slice(0, 30));

// 第三轮：他
await ask("他为什么风险这么高？");
r = await lastAssistant();
check("「他」指代上一轮学生", r.thoughts.some((t) => t.includes("他") && t.includes("上一轮")), r.thoughts[0] || "无");

// 第四轮：姓名直呼 → 谈话要点
await ask("给黄伟诚生成谈话要点");
r = await lastAssistant();
check("姓名直呼生成谈话要点", /谈话前需要知道的|谈话的性质|建议的谈话顺序/.test(r.text), r.text.slice(0, 40));
check("要点生成走了 counselor_brief", r.tools.some((t) => t.includes("谈话要点")), r.tools.join(",").slice(0, 60));

// 第五轮：记录归档
await ask("记录：今天下午已经谈过了，约了下周三复查");
r = await lastAssistant();
check("对话式记录写入台账", /已记录到/.test(r.text), r.text.slice(0, 40));

// 建议词跟随上下文（整页对话底部）
const sugg = await page.evaluate(() => [...document.querySelectorAll(".ch-suggest .chip")].map((c) => c.textContent.trim()));
check("建议词跟随上下文", sugg.some((s) => /要点|记录|本班/.test(s)), sugg.join(" / ").slice(0, 60));
await page.screenshot({ path: `${OUT}/agent_chat_counselor.png`, fullPage: false });

// ============================================================
// 二·五、文书导出与触达：对话里要文件 → 链接 → 真下载验证
// ============================================================
// 导出黄伟诚的家长信（沿用上一轮记忆里的黄伟诚）
await ask("导出黄伟诚的家长信");
r = await lastAssistant();
let link = await lastLink();
check("对话里导出家长信给出下载链接", !!link, link?.text || "无链接");
check("导出意图走了 export_file 工具", r.tools.some((t) => t.includes("export_file")), r.tools.join(",").slice(0, 40));
if (link) {
  const f = await fetchFile(link.href);
  check("家长信 Word 真实可下载（PK 魔数）", f.status === 200 && f.magic.startsWith("PK"), `${f.status} ${f.magic} ${f.type.slice(0, 30)}`);
}

// 把家长信发给家长（记忆里还是黄伟诚）：eml 双模式
await ask("把家长信发给家长");
r = await lastAssistant();
link = await lastLink();
check("发送家长信给出 .eml 邮件文件", !!link && /\.eml/.test(r.text), (link?.text || "").slice(0, 30));
if (link) {
  const f = await fetchFile(link.href);
  check(".eml 邮件文件可下载（收件人已填好）", f.status === 200 && f.magic.startsWith("Cont"), `${f.status} ${f.magic.slice(0, 4)}`);
}

// 今日日报：正文 + 链接
await ask("今日日报说了什么？");
r = await lastAssistant();
link = await lastLink();
check("对话里问日报得到摘要", /预警日报|上升/.test(r.text), r.text.slice(0, 40));
if (link) {
  const f = await fetchFile(link.href);
  check("日报 Word 真实可下载", f.status === 200 && f.magic.startsWith("PK"), `${f.status} ${f.magic}`);
}

// 学期汇报 PPT
await ask("生成学期汇报 PPT");
link = await lastLink();
check("对话里生成学期汇报 PPT 链接", !!link, link?.text || "无");
if (link) {
  const f = await fetchFile(link.href);
  check("学期 PPT 真实可下载（PK 魔数）", f.status === 200 && f.magic.startsWith("PK"), `${f.status} ${f.magic}`);
}
await page.screenshot({ path: `${OUT}/agent_export_chat.png`, fullPage: false });

// 记录真的落库：去预警名单看板打开黄伟诚的抽屉核对
await goDash();
await page.waitForSelector(".el-table__row", { timeout: 30000 });
await sleep(800);
const row = await page.evaluateHandle(() => {
  const rows = [...document.querySelectorAll(".el-table__row")];
  return rows.find((r) => r.textContent.includes("黄伟诚")) || rows[0];
});
if (row) {
  await row.asElement().click();
  await sleep(1400);
  const iv = await page.evaluate(() => ({
    n: document.querySelectorAll(".iv-item").length,
    first: document.querySelector(".iv-item .iv-title, .iv-item")?.textContent || "",
    exports: [...document.querySelectorAll(".drawer-exports .chip")].map((c) => c.textContent.trim()),
  }));
  check("抽屉里能看到刚写入的干预记录", iv.n >= 1 && /谈/.test(iv.first), `n=${iv.n} ${iv.first.slice(0, 30)}`);
  check("抽屉里有四个文书导出入口", iv.exports.length >= 4, iv.exports.join("/"));
  await page.screenshot({ path: `${OUT}/agent_drawer.png`, fullPage: false });
  await page.keyboard.press("Escape");
  await sleep(400);
}

// ============================================================
// 三、家长端：整页对话 + 简报（身份隔离抽查）
// ============================================================
await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
await loginAs("parent", "20240001", "3333");
await page.goto(`${BASE}/parent`, { waitUntil: "networkidle0" });
await sleep(3500);
const pb = await page.evaluate(() => ({
  chatHome: !!document.querySelector(".chat-home"),
  exists: !!document.querySelector(".briefing"),
  greet: document.querySelector(".b-greet")?.textContent || "",
  points: document.querySelectorAll(".b-point").length,
  goDashBtn: document.querySelector(".ch-go-dash")?.textContent.trim() || "",
}));
check("进家长端就是整页对话", pb.chatHome);
check("家长端有主动简报", pb.exists && pb.points >= 2, `points=${pb.points}`);
check("家长简报口吻正确", pb.greet.includes("家校") || pb.greet.includes("您好"), pb.greet.slice(0, 24));
check("家长按键文案是学情报告", pb.goDashBtn.includes("学情报告"), pb.goDashBtn);
await page.screenshot({ path: `${OUT}/agent_brief_parent.png`, fullPage: false });

// 家长也能去孩子的数据看板（家长端主卡类名是 parent-head）
await goDash();
await page.waitForSelector(".parent-head", { timeout: 25000 });
check("家长按键进入孩子学情报告", !!(await page.$(".parent-head")));
const parentExport = await page.evaluate(() =>
  [...document.querySelectorAll(".view-actions .btn")].map((b) => b.textContent.trim()).join("/"));
check("家长看板有「导出家长信 Word」按钮", parentExport.includes("导出家长信"), parentExport);
await page.screenshot({ path: `${OUT}/agent_dash_parent.png`, fullPage: false });

// ============================================================
// 三·五、教务端：日报卡 + 学期汇报 PPT 入口（看板即数据仪表盘）
// ============================================================
await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
await loginAs("admin", "1234567899", "2222");
await page.goto(`${BASE}/admin`, { waitUntil: "networkidle0" });
await sleep(2500);
const adminHome = await page.evaluate(() => ({
  chatHome: !!document.querySelector(".chat-home"),
  goDashBtn: document.querySelector(".ch-go-dash")?.textContent.trim() || "",
}));
check("进教务端就是整页对话", adminHome.chatHome);
await goDash();
await sleep(1200);
const adminDash = await page.evaluate(() => ({
  dailyCard: [...document.querySelectorAll(".card-head h3")].some((h) => h.textContent.includes("每日预警日报")),
  dailySummary: document.querySelector(".report-strip") ? true : false,
  pptBtn: [...document.querySelectorAll(".view-actions .btn")].map((b) => b.textContent.trim()).join("/"),
}));
check("教务看板有每日预警日报卡", adminDash.dailyCard && adminDash.dailySummary);
check("教务看板有学期汇报 PPT 按钮", adminDash.pptBtn.includes("学期汇报"), adminDash.pptBtn.slice(0, 60));
await page.screenshot({ path: `${OUT}/agent_dash_admin.png`, fullPage: false });

// ============================================================
// 四、控制台 / 请求零错误
// ============================================================
check("无 console 错误", errors.length === 0, errors.slice(0, 3).join(" | "));
check("无失败请求", errors.filter((e) => e.startsWith("requestfailed")).length === 0, "");

await browser.close();

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} 项通过`);
if (failed.length) {
  console.log("失败项：", failed.map((f) => f.name).join("、"));
  process.exit(1);
}
