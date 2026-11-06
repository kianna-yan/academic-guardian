import puppeteer from "puppeteer-core";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8620";
const OUT = "C:/Users/lenovo/WorkBuddy/2026-11-03-16-18-31/_v8/shots_portal";

const res = [];
const ok = (n, p, e = "") => {
  res.push(p);
  console.log(`${p ? "PASS" : "FAIL"}  ${n}${e ? "  " + e : ""}`);
};

async function token(role, account, password) {
  const r = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ role, account, password }),
  });
  return (await r.json()).token;
}

const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox"] });

/* ---------- ① 抽屉里真发一句话，能收到回答 ---------- */
{
  const t = await token("counselor", "2024014589", "1111");
  const p = await b.newPage();
  await p.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1.5 });
  const errs = [];
  p.on("pageerror", (e) => errs.push(e.message));
  await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
  await p.goto(BASE + "/counselor", { waitUntil: "networkidle2" });
  await new Promise((s) => setTimeout(s, 2500));
  await p.click('[data-test="ai-dock"]');
  await new Promise((s) => setTimeout(s, 700));
  await p.type("[data-test=chat-input]", "本班谁的风险上升最快？");
  await p.click("[data-test=chat-send]");
  await new Promise((s) => setTimeout(s, 1500));
  // 流式作答，等到没有 pending 气泡
  for (let i = 0; i < 40; i++) {
    const busy = await p.evaluate(() => !!document.querySelector(".typing-caret, .spinner"));
    if (!busy) break;
    await new Promise((s) => setTimeout(s, 700));
  }
  const out = await p.evaluate(() => {
    const msgs = [...document.querySelectorAll(".msg")];
    const last = msgs[msgs.length - 1];
    return {
      user: msgs.filter((m) => m.classList.contains("user")).map((m) => m.textContent.trim()).slice(-1)[0],
      answer: last ? last.textContent.trim().slice(0, 120) : "",
      len: last ? last.textContent.trim().length : 0,
      inSheet: !!document.querySelector(".ai-sheet .msg"),
    };
  });
  ok("抽屉里能发问", (out.user || "").includes("风险上升最快"), out.user?.slice(0, 20));
  ok("抽屉里收到回答", out.len > 30 && out.inSheet, `${out.len} 字｜${out.answer.slice(0, 40)}…`);
  await p.screenshot({ path: `${OUT}/sheet-reply.png` });

  // 收起再展开，历史还在（不是每次都重来）
  await p.click('[data-test="sheet-close"]');
  await new Promise((s) => setTimeout(s, 700));
  await p.click('[data-test="ai-dock"]');
  await new Promise((s) => setTimeout(s, 700));
  const kept = await p.evaluate(() => document.querySelectorAll(".ai-sheet .msg").length);
  ok("收起再展开，问答记录还在", kept >= 3, `${kept} 条`);
  ok("无控制台报错", errs.length === 0, errs.slice(0, 1).join(""));
  await p.close();
}

/* ---------- ② 子页面上的「问 AI」也能把抽屉唤起来 ---------- */
{
  const t = await token("student", "20240067", "0000");
  const p = await b.newPage();
  await p.setViewport({ width: 1440, height: 900 });
  await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
  // 看板版块现在是独立页面，图表旁的「问 AI」在成绩走势这一页
  await p.goto(BASE + "/student/grade", { waitUntil: "networkidle2" });
  await new Promise((s) => setTimeout(s, 3500));
  const btn = await p.$(".ask-ai");
  await btn?.evaluate((e) => e.scrollIntoView({ block: "center" }));
  if (!btn) {
    ok("子页面有「问 AI」入口", false, "未找到 .ask-ai");
  } else {
    await btn.click();
    await new Promise((s) => setTimeout(s, 1200));
    const st = await p.evaluate(() => {
      const s = document.querySelector(".ai-sheet");
      const users = [...document.querySelectorAll(".ai-sheet .msg.user")];
      return { open: !!s, q: users.length ? users[users.length - 1].textContent.trim().slice(0, 30) : "" };
    });
    ok("子页面「问 AI」直接唤起抽屉", st.open && st.q.length > 0, st.q);
    await p.screenshot({ path: `${OUT}/ask-from-sub.png` });
  }
  await p.close();
}

/* ---------- ③ 内页「问 AI」也能唤起（侧栏撤掉后，这是内页唯一的 AI 入口） ---------- */
{
  const t = await token("student", "20240067", "0000");
  const p = await b.newPage();
  await p.setViewport({ width: 1440, height: 900 });
  await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
  await p.goto(BASE + "/student/schedule", { waitUntil: "networkidle2" });
  await new Promise((s) => setTimeout(s, 2500));
  const clicked = await p.evaluate(() => {
    const btn = document.querySelector('[data-test="back-ai"]');
    if (btn) btn.click();
    return !!btn;
  });
  await new Promise((s) => setTimeout(s, 1600));
  const st = await p.evaluate(() => ({
    open: !!document.querySelector(".ai-sheet"),
    url: location.pathname,
    sidebar: !!document.querySelector(".sidebar"),
  }));
  ok("内页「问 AI」唤起抽屉（侧栏已删除）", clicked && st.open && !st.sidebar, `${st.url}`);
  await p.close();
}

await b.close();
const bad = res.filter((x) => !x).length;
console.log(`\n${res.length - bad}/${res.length} 通过`);
process.exit(bad ? 1 : 0);
