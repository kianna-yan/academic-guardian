/**
 * 验证「+ → 提示词」完整流程：
 * 展开抽屉 → 点「+」→ 点「提示词」→ 选一条 → 点「添加到输入框」→
 * 检查输入框里出现【标签】开头的整段提示词。教师端、学生端各跑一遍。
 */
import puppeteer from "puppeteer-core";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8600";
const ACC = {
  teacher: ["2024014501", "4444"],
  student: ["20240067", "0000"],
};

const b = await puppeteer.launch({
  executablePath: EXE,
  headless: true,
  args: ["--no-sandbox", "--proxy-server=direct://", "--proxy-bypass-list=*"],
});

for (const [role, [account, password]] of Object.entries(ACC)) {
  const r = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ role, account, password }),
  });
  const token = (await r.json()).token;
  const p = await b.newPage();
  await p.setViewport({ width: 1440, height: 900 });
  await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), token);
  await p.goto(`${BASE}/${role}`, { waitUntil: "networkidle2" });
  await new Promise((s) => setTimeout(s, 3200));
  await p.evaluate(() => document.querySelectorAll(".el-notification").forEach((n) => n.remove()));

  // 1. 点首页 AI 卡的输入条，展开全屏对话抽屉
  await p.click(".ai-card .ai-input");
  await new Promise((s) => setTimeout(s, 900));

  // 2. 点「+」→ 菜单里应有「提示词」
  await p.click(".ch-plus");
  await new Promise((s) => setTimeout(s, 400));
  const menuHas = await p.evaluate(() =>
    [...document.querySelectorAll(".ch-menu .tx b")].some((x) => x.textContent === "提示词"),
  );

  // 3. 点「提示词」→ 二级面板列出该端预置项
  await p.evaluate(() => {
    const btn = [...document.querySelectorAll(".ch-menu button.has-sub")].find((x) =>
      x.textContent.includes("提示词"),
    );
    btn.click();
  });
  await new Promise((s) => setTimeout(s, 400));
  const items = await p.evaluate(() =>
    [...document.querySelectorAll(".ch-prompts .sub-item b")].map((x) => x.textContent.trim()),
  );

  // 4. 选第一条 → 点「添加到输入框」
  await p.click(".ch-prompts .sub-item");
  await new Promise((s) => setTimeout(s, 250));
  const addBtnText = await p.evaluate(() => {
    const a = document.querySelector(".ch-prompts .prompt-add");
    return a ? a.textContent.trim() : "";
  });
  await p.click(".ch-prompts .prompt-add");
  await new Promise((s) => setTimeout(s, 400));

  const draft = await p.evaluate(() => {
    const t = document.querySelector('[data-test="chat-input"]');
    return t ? t.value : "";
  });

  console.log(
    JSON.stringify(
      { role, menuHas, count: items.length, items: items.slice(0, 3), addBtnText, draftHead: draft.slice(0, 40), draftLen: draft.length },
      null,
      1,
    ),
  );

  if (role === "teacher") {
    await p.screenshot({ path: "C:/tmp/prompt_panel.png" });
  }
  await p.close();
}
await b.close();
console.log("done");
