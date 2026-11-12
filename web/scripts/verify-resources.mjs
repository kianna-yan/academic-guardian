// 学习资源板块：真题套数 / 下载可用性 / 网课外链跳转（本地 8620）
import puppeteer from "puppeteer-core";
import fs from "node:fs";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8620";
const OUT = "shots_res";
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

const tk = await token("student", "20240221", "0000");

/* ---------- 1. 接口层：套数与文件可用性 ---------- */
const api = async (path) => {
  const r = await fetch(`${BASE}${path}`, { headers: { Authorization: `Bearer ${tk}` } });
  return r;
};

const list = async (kind) => {
  const r = await api(`/api/teacher/resources?kind=${kind}`);
  return (await r.json()).items || [];
};

const exams = await list("exam");
const tuts = await list("tutorial");
console.log("真题:", exams.map((e) => e.filename));
console.log("网课:", tuts.map((e) => `${e.filename}${e.url ? " [link]" : ""}`));

ok("真题至少 5 套", exams.length >= 5, `${exams.length} 套`);
ok("网课至少 5 条", tuts.length >= 5, `${tuts.length} 条`);
ok("网课含外链资源", tuts.filter((t) => t.url).length >= 4, `${tuts.filter((t) => t.url).length} 条外链`);
ok("真题都已进知识库", exams.every((e) => e.kb?.ok), exams.map((e) => e.kb?.sections).join("/"));

// 真实下载一份新真题，检查是能打开的 docx（zip 头 PK）且体积正常
const target = exams.find((e) => e.filename.includes("组成原理")) || exams[0];
const dl = await api(`/api/teacher/resources/${target.id}/download`);
const buf = Buffer.from(await dl.arrayBuffer());
ok("下载返回 200", dl.status === 200, `${dl.status} ${buf.length} B`);
ok("文件是合法 docx（PK 头）", buf[0] === 0x50 && buf[1] === 0x4b, buf.slice(0, 4).toString("hex"));
ok("文件体积正常", buf.length > 20000, `${Math.round(buf.length / 1024)} KB`);
fs.writeFileSync(`${OUT}/downloaded.docx`, buf);

// 外链资源：应 302 到 icourse163
const linkRes = await fetch(`${BASE}/api/teacher/resources/${tuts.find((t) => t.url).id}/download`, {
  headers: { Authorization: `Bearer ${tk}` },
  redirect: "manual",
});
const loc = linkRes.headers.get("location") || "";
ok("外链资源 302 跳转", linkRes.status === 302 && /icourse163\.org/.test(loc), `${linkRes.status} → ${loc}`);

/* ---------- 2. 页面层：渲染与按钮文案 ---------- */
const browser = await puppeteer.launch({
  executablePath: EXE,
  headless: true,
  args: ["--disable-gpu", "--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 980 });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));

await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
await page.evaluate((t) => localStorage.setItem("ag.token", t), tk);
await page.reload({ waitUntil: "domcontentloaded" });
await sleep(1800);
await page.evaluate(() => {
  document.querySelectorAll(".v11-veil,.star-wipe,.pre-veil").forEach((n) => n.remove());
  document.documentElement.classList.remove("v11-veil");
});
// 走「继续进入」→ 点门户节点，避免整页刷新深层路由被 bootNav 守卫弹回登录页
await page.evaluate(() => {
  [...document.querySelectorAll("button")].find((n) => n.textContent.trim() === "继续进入")?.click();
});
await sleep(3000);
const onPortal = await page.evaluate(() => !!document.querySelector(".pt-node"));
const entered = await page.evaluate(() => {
  const n = document.querySelector('.pt-node[data-node="resources"]');
  if (!n) return false;
  n.click();
  return true;
});
await sleep(3000);
await page.evaluate(() => {
  document.querySelectorAll(".v11-veil,.star-wipe,.pre-veil").forEach((n) => n.remove());
  document.documentElement.classList.remove("v11-veil");
});
await sleep(600);
console.log("门户:", onPortal, "进入资源节点:", entered, page.url());

const examTab = await page.evaluate(() => ({
  url: location.pathname,
  count: document.querySelector(".card-head h3")?.textContent.trim(),
  rows: [...document.querySelectorAll(".res-row")].length,
  firstBtn: document.querySelector(".res-row .res-side .btn")?.textContent.trim(),
}));
console.log("页面:", JSON.stringify(examTab));
ok("页面在资源板块", examTab.url.includes("/resources"), examTab.url);
ok("标题显示套数（≥5）", /（[5-9]）/.test(examTab.count || ""), examTab.count);
await page.screenshot({ path: `${OUT}/1-exam.png`, fullPage: true });

// 切到网课 tab
await page.evaluate(() => {
  const b = [...document.querySelectorAll(".rt")].find((n) => n.textContent.includes("网课"));
  b?.click();
});
await sleep(900);
const tutView = await page.evaluate(() => ({
  count: document.querySelector(".card-head h3")?.textContent.trim(),
  rows: [...document.querySelectorAll(".res-row")].map((r) => ({
    name: r.querySelector("b")?.textContent.trim(),
    meta: r.querySelector(".tiny.muted")?.textContent.replace(/\s+/g, " ").trim(),
    btn: r.querySelector(".res-side .btn")?.textContent.trim(),
    ext: !!r.querySelector(".ext-tag"),
  })),
}));
console.log("网课页:", JSON.stringify(tutView, null, 1));
ok("网课标题套数 ≥5", /（[5-9]）/.test(tutView.count || ""), tutView.count);
ok("外链行按钮文案为「去观看」", tutView.rows.filter((r) => r.ext).every((r) => r.btn === "去观看"),
  tutView.rows.map((r) => r.btn).join(","));
ok("外链行显示「在线课程」", tutView.rows.filter((r) => r.ext).every((r) => /在线课程/.test(r.meta || "")),
  tutView.rows[0]?.meta);
await page.screenshot({ path: `${OUT}/2-tutorial.png`, fullPage: true });

ok("页面无 JS 报错", errors.length === 0, errors.slice(0, 2).join(" / "));

await browser.close();
console.log(`\n共 ${pass} 项通过`);
