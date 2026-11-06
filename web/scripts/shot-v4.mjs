import puppeteer from "puppeteer-core";
import fs from "node:fs";

const EXE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = process.env.AG_BASE || "http://127.0.0.1:8630";
const OUT = "C:/Users/lenovo/WorkBuddy/2026-11-03-16-18-31/_v8/shots_v4";
fs.mkdirSync(OUT, { recursive: true });

async function token(role, account, password) {
  const r = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ role, account, password }),
  });
  const j = await r.json().catch(() => ({}));
  return j.token || "";
}

const ACC = {
  student: ["20240023", "0000", "/student"],
  counselor: ["2024014589", "1111", "/counselor"],
  admin: ["1234567899", "2222", "/admin"],
  teacher: ["2024014501", "4444", "/teacher"],
  parent: ["20240067", "3333", "/parent"],
};

const b = await puppeteer.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox"] });

// 1) 五端门户
for (const [role, [acc, pwd, path]] of Object.entries(ACC)) {
  const t = await token(role, acc, pwd);
  if (!t) { console.log("SKIP", role); continue; }
  const p = await b.newPage();
  await p.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1.5 });
  await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
  await p.goto(BASE + path, { waitUntil: "networkidle2" });
  await new Promise((s) => setTimeout(s, 2600));
  await p.screenshot({ path: `${OUT}/${role}.png` });

  // 节点两两不重叠：几何脚本量一遍
  const boxes = await p.$$eval(".pt-node", (els) =>
    els.map((e) => {
      const r = e.getBoundingClientRect();
      return { k: e.getAttribute("data-node"), x: r.x, y: r.y, w: r.width, h: r.height };
    }),
  );
  let hit = 0;
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], c = boxes[j];
      const ox = Math.min(a.x + a.w, c.x + c.w) - Math.max(a.x, c.x);
      const oy = Math.min(a.y + a.h, c.y + c.h) - Math.max(a.y, c.y);
      if (ox > 6 && oy > 6) { hit++; console.log("  overlap", a.k, c.k, Math.round(ox), Math.round(oy)); }
    }
  }
  const stats = await p.$$eval(".pt-stats .st", (els) => els.map((e) => e.textContent.trim()));
  const hero = await p.$eval(".pt-hero", (e) => e.textContent.replace(/\s+/g, " ").trim()).catch(() => "");
  console.log(role, "nodes", boxes.length, "overlap", hit, "|", hero, "|", stats.join(" / "));
  await p.close();
}

// 2) AI 抽屉（辅导员端）
{
  const t = await token("counselor", "2024014589", "1111");
  const p = await b.newPage();
  await p.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1.5 });
  await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
  await p.goto(BASE + "/counselor", { waitUntil: "networkidle2" });
  await new Promise((s) => setTimeout(s, 2200));
  await p.click('[data-test="ai-dock"]');
  await new Promise((s) => setTimeout(s, 1200));
  await p.screenshot({ path: `${OUT}/ai_sheet.png` });
  const badge = await p.$eval('[data-test="model-badge"]', (e) => ({
    text: e.innerText.replace(/\s+/g, " ").trim(),
    box: e.getBoundingClientRect().toJSON(),
  })).catch(() => null);
  console.log("model badge", JSON.stringify(badge));
  await p.close();
}

// 3) 家长端家校沟通：发一张照片试试
{
  const t = await token("parent", "20240067", "3333");
  const p = await b.newPage();
  await p.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1.5 });
  await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
  await p.goto(BASE + "/messages", { waitUntil: "networkidle2" });
  await new Promise((s) => setTimeout(s, 2200));
  const hasPhoto = await p.$('[data-test="msg-photo"]');
  const hasVoice = await p.$('[data-test="msg-voice"]');
  console.log("parent message photo/voice", !!hasPhoto, !!hasVoice);

  const file = await p.$(".ci-file");
  if (file) {
    await file.uploadFile("C:/Users/lenovo/WorkBuddy/2026-11-03-16-18-31/_v8/share_shot.png");
    await new Promise((s) => setTimeout(s, 1800));
    await p.screenshot({ path: `${OUT}/parent_message_attach.png` });
    const ta = await p.$(".ci-row textarea");
    if (ta) await ta.type("刘老师，孩子这周的作业拍给您，麻烦帮着看看。");
    await p.click(".ci-row .btn.ok");
    await new Promise((s) => setTimeout(s, 2200));
    const imgs = await p.$$eval(".bubble-media .bm-img img", (els) => els.length);
    console.log("sent photo bubbles", imgs);
  }
  await p.screenshot({ path: `${OUT}/parent_message.png` });
  await p.close();
}

// 4) 手机端
{
  const t = await token("student", "20240023", "0000");
  const p = await b.newPage();
  await p.setViewport({ width: 390, height: 844, deviceScaleFactor: 2, isMobile: true });
  await p.evaluateOnNewDocument((x) => localStorage.setItem("ag.token", x), t);
  await p.goto(BASE + "/student", { waitUntil: "networkidle2" });
  await new Promise((s) => setTimeout(s, 2600));
  await p.screenshot({ path: `${OUT}/mobile_top.png` });
  const w = await p.evaluate(() => ({ sw: document.body.scrollWidth, cw: document.documentElement.clientWidth }));
  console.log("mobile width", JSON.stringify(w));
  await p.screenshot({ path: `${OUT}/mobile_full.png`, fullPage: true });
  await p.close();
}

await b.close();
console.log("done");
