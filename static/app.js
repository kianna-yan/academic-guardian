const state = {
  meta: null,
  role: "student",
  sid: null,
  view: null,
  roster: [],
  overview: null,
  filters: { class_name: "", level: "" },
  chatOpen: true,
  busy: false,
};

const LEVEL_TEXT = { red: "红色预警", yellow: "黄色关注", green: "状态正常" };
const LEVEL_COLOR = { red: "#dc2626", yellow: "#d97706", green: "#047857" };
const DEFAULT_SUGGEST = {
  student: ["我的风险分为什么这么高？", "这学期还来得及吗？", "挂多少学分会被降级？"],
  counselor: ["本班谁的风险上升最快？", "哪些班级红色预警最多？", "这周该找谁谈话？"],
  admin: ["全校风险分布如何？", "哪些班级问题最集中？", "缺勤和挂科是什么关系？"],
  parent: ["孩子这学期情况怎么样？", "学校什么情况下会通知家长？", "他还来得及毕业吗？"],
};

/* ---------------- 工具 ---------------- */
// 发布到公网后，网关要求每个请求都带分享码，否则一律 403。
// 从当前地址里取出分享码，附加到所有接口请求上，页面才能正常加载。
const SHARE_CODE = new URLSearchParams(location.search).get("sharecode") || "";

function withShareCode(path) {
  if (!SHARE_CODE) return path;
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}sharecode=${encodeURIComponent(SHARE_CODE)}`;
}

async function api(path, opts) {
  const res = await fetch(withShareCode(path), opts);
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  return res.json();
}

function el(id) { return document.getElementById(id); }

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function mdToHtml(md) {
  const lines = String(md || "").split("\n");
  let html = "", list = null, table = null;

  const closeList = () => { if (list) { html += `</${list}>`; list = null; } };
  const closeTable = () => { if (table) { html += "</table>"; table = null; } };

  for (let raw of lines) {
    const line = raw.trimEnd();
    if (/^\|/.test(line)) {
      const cells = line.split("|").slice(1, -1).map(c => c.trim());
      if (cells.every(c => /^-{2,}$/.test(c) || c === "")) continue;
      if (!table) {
        closeList();
        html += "<table>";
        table = true;
        html += "<tr>" + cells.map(c => `<th>${inline(c)}</th>`).join("") + "</tr>";
      } else {
        html += "<tr>" + cells.map(c => `<td>${inline(c)}</td>`).join("") + "</tr>";
      }
      continue;
    }
    closeTable();
    if (/^#{2,4}\s/.test(line)) {
      closeList();
      html += `<h3>${inline(line.replace(/^#+\s*/, ""))}</h3>`;
      continue;
    }
    if (/^\s*[-•]\s+/.test(line)) {
      if (list !== "ul") { closeList(); html += "<ul>"; list = "ul"; }
      html += `<li>${inline(line.replace(/^\s*[-•]\s+/, ""))}</li>`;
      continue;
    }
    if (/^\s*\d+\.\s+/.test(line)) {
      if (list !== "ol") { closeList(); html += "<ol>"; list = "ol"; }
      html += `<li>${inline(line.replace(/^\s*\d+\.\s+/, ""))}</li>`;
      continue;
    }
    closeList();
    if (line.trim() === "") { html += "<div style='height:6px'></div>"; continue; }
    html += `<p style="margin:4px 0">${inline(line)}</p>`;
  }
  closeList(); closeTable();
  return html;
}

function inline(s) {
  return esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/`(.+?)`/g, '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">$1</code>');
}

function ringSVG(score, level) {
  const r = 52, c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(100, score));
  const color = LEVEL_COLOR[level] || "#1d4ed8";
  return `<svg width="140" height="140" viewBox="0 0 140 140" role="img" aria-label="风险分 ${Math.round(v)}">
    <circle cx="70" cy="70" r="${r}" fill="none" stroke="#eef0f3" stroke-width="11"/>
    <circle cx="70" cy="70" r="${r}" fill="none" stroke="${color}" stroke-width="11"
      stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - v / 100)}"
      transform="rotate(-90 70 70)"/>
    <text x="70" y="66" text-anchor="middle" font-size="30" font-weight="500" fill="#111827">${Math.round(v)}</text>
    <text x="70" y="86" text-anchor="middle" font-size="11" fill="#6b7280">风险分 / 100</text>
  </svg>`;
}

function donutSVG(dist) {
  const total = (dist.red || 0) + (dist.yellow || 0) + (dist.green || 0) || 1;
  const data = [
    { k: "red", v: dist.red, c: "#dc2626" },
    { k: "yellow", v: dist.yellow, c: "#d97706" },
    { k: "green", v: dist.green, c: "#047857" },
  ];
  const R = 58, C = 2 * Math.PI * R;
  let acc = 0, arcs = "";
  for (const d of data) {
    const len = (d.v / total) * C;
    arcs += `<circle cx="80" cy="80" r="${R}" fill="none" stroke="${d.c}" stroke-width="18"
      stroke-dasharray="${len} ${C - len}" stroke-dashoffset="${-acc}" transform="rotate(-90 80 80)"/>`;
    acc += len;
  }
  return `<div style="display:flex;align-items:center;gap:18px">
    <svg width="160" height="160" viewBox="0 0 160 160" role="img" aria-label="风险等级分布">
      ${arcs}
      <text x="80" y="76" text-anchor="middle" font-size="22" font-weight="500" fill="#111827">${total}</text>
      <text x="80" y="94" text-anchor="middle" font-size="11" fill="#6b7280">在册学生</text>
    </svg>
    <div style="font-size:12.5px;line-height:2">
      ${data.map(d => `<div><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${d.c};margin-right:7px"></span>
        ${LEVEL_TEXT[d.k]} <b>${d.v}</b> 人
        <span class="muted">（${((d.v / total) * 100).toFixed(1)}%）</span></div>`).join("")}
    </div>
  </div>`;
}

function trendTag(row) {
  const cls = row.direction === "up" ? "trend-up" : row.direction === "down" ? "trend-down" : "trend-flat";
  const arrow = row.direction === "up" ? "↑" : row.direction === "down" ? "↓" : "→";
  return `<span class="${cls}">${arrow} ${Math.abs(row.delta).toFixed(0)}</span>`;
}

function scoreChip(score, level) {
  return `<span class="score-chip ${level}">${Math.round(score)}</span>`;
}

/* ---------------- 角色导航 ---------------- */
function renderRoleNav() {
  const nav = el("roleNav");
  nav.innerHTML = state.meta.roles.map(r => `
    <button class="role-btn ${r.key === state.role ? "active" : ""}" data-role="${r.key}">
      <span>${r.name}</span><em>${r.desc}</em>
    </button>`).join("");
  nav.querySelectorAll(".role-btn").forEach(b => {
    b.onclick = () => switchRole(b.dataset.role);
  });
}

function switchRole(role) {
  state.role = role;
  state.filters = { class_name: "", level: "" };
  if (role === "student") state.sid = state.meta.demo.student;
  if (role === "parent") state.sid = state.meta.demo.parent;
  if (role === "counselor") state.sid = null;
  if (role === "admin") state.sid = null;
  history.replaceState(null, "", "#" + role);
  state.suggest = DEFAULT_SUGGEST[role];
  state.chatReset = true;
  renderRoleNav();
  render();
}

/* ---------------- 顶栏 ---------------- */
function renderTopbar() {
  const titles = {
    student: ["学生端", "看清自己的学业状态，并拿到可执行的补救路径"],
    counselor: ["辅导员端", "按风险排序的名单、谈话要点与跟踪记录"],
    admin: ["教务端", "规则配置、全校看板与预警名单导出"],
    parent: ["家长端", "了解孩子在校情况，与学校形成合力"],
  };
  el("pageTitle").textContent = titles[state.role][0];
  el("pageSub").textContent = titles[state.role][1];

  const right = el("topActions");
  const classes = state.meta.classes;
  if (state.role === "counselor") {
    right.innerHTML = `
      <select class="select" id="filterClass">
        <option value="">全部班级</option>
        ${classes.map(c => `<option value="${c}" ${state.filters.class_name === c ? "selected" : ""}>${c}</option>`).join("")}
      </select>
      <select class="select" id="filterLevel">
        <option value="">全部等级</option>
        <option value="red" ${state.filters.level === "red" ? "selected" : ""}>仅红色预警</option>
        <option value="yellow" ${state.filters.level === "yellow" ? "selected" : ""}>仅黄色关注</option>
      </select>
      <button class="btn" id="btnReport">生成班级周报</button>`;
    el("filterClass").onchange = e => { state.filters.class_name = e.target.value; render(); };
    el("filterLevel").onchange = e => { state.filters.level = e.target.value; render(); };
    el("btnReport").onclick = () => openClassReport();
  } else if (state.role === "admin") {
    right.innerHTML = `<span class="badge" style="background:#eff6ff;color:#1d4ed8">规则版本 v1.2</span>
      <button class="btn" id="btnExport">导出预警名单</button>`;
    el("btnExport").onclick = exportCSV;
  } else if (state.role === "parent") {
    right.innerHTML = `<span class="badge" style="background:#fff7ed;color:#b45309">家长视角</span>
      <button class="btn primary" id="btnParentLetter">生成家长信</button>`;
    el("btnParentLetter").onclick = () => openLetter(state.sid, "parent");
  } else {
    right.innerHTML = `<span class="badge" style="background:#f1f5f9;color:#475569">演示学号 ${esc(state.meta.demo.student)}</span>
      <button class="btn primary" id="btnStudentLetter">生成告知函</button>`;
    el("btnStudentLetter").onclick = () => openLetter(state.sid, "student");
  }
}

/* ---------------- 路由 ---------------- */
async function render() {
  renderTopbar();
  const view = el("view");
  view.innerHTML = `<div class="empty"><span class="spinner"></span></div>`;
  try {
    if (state.role === "student") await renderStudent(view);
    else if (state.role === "counselor") await renderCounselor(view);
    else if (state.role === "admin") await renderAdmin(view);
    else await renderParent(view);
  } catch (err) {
    view.innerHTML = `<div class="card"><b>加载失败</b><p class="tiny muted">${esc(err.message)}</p></div>`;
  }
  setupChat();
}

/* ---------------- 学生端 ---------------- */
async function renderStudent(view) {
  const d = await api(`/api/students/${state.sid}`);
  const s = d.student, r = d.risk;
  state.view = d;

  const facts = [
    ["缺勤次数", `${r.raw.absent} 次`, `${r.raw.sessions} 次课中`],
    ["作业提交", `${r.raw.hw_submitted}/${r.raw.hw_assigned}`, "本学期"],
    ["期中均分", r.raw.mid_avg, `班级 ${r.raw.cohort_avg}`],
    ["累计挂科", `${s.history.failed_credits}`, "学分"],
  ];

  view.innerHTML = `
    <div class="card risk-hero ${r.level}">
      <div class="ring-wrap">
        ${ringSVG(r.score, r.level)}
        <span class="level-pill ${r.level}">${r.level_label}</span>
      </div>
      <div>
        <div class="risk-title">
          <span class="risk-name">${esc(s.name)}</span>
          <span class="tiny muted">${esc(s.class_name)} · ${esc(s.major)} · ${esc(s.grade)}</span>
        </div>
        <p class="tiny muted" style="margin:0 0 10px">
          较上学期 <b class="${r.trend.direction === "up" ? "trend-up" : r.trend.direction === "down" ? "trend-down" : "trend-flat"}">
          ${r.trend.label} ${r.trend.delta > 0 ? "+" : ""}${r.trend.delta.toFixed(0)} 分</b>
          （上学期折算 ${r.trend.last_score} 分） · 数据截至第 ${state.meta.week} 教学周
        </p>
        <div class="risk-facts">
          ${facts.map(f => `<div class="fact"><b>${f[1]}</b><span>${f[0]} · ${f[2]}</span></div>`).join("")}
        </div>
        ${r.overrides.length ? `<div class="tiny" style="margin-top:10px;color:#b91c1c;background:#fef2f2;border:1px solid #fecaca;border-radius:6px;padding:6px 10px">
          ${r.overrides.map(o => esc(o)).join("；")}</div>` : ""}
      </div>
    </div>

    <div class="two-col" style="margin-top:14px">
      <div class="card">
        <div class="card-head">
          <h3>风险从哪里来</h3>
          <span class="hint">每一项的分数相加等于风险分</span>
        </div>
        ${r.factors.map(f => {
          const pct = Math.min(100, f.value * 100);
          const cls = f.points > 15 ? "hot" : f.points > 9 ? "warm" : "";
          return `<div class="factor">
            <div class="factor-top"><b>${f.label}</b><span class="pt">${f.points.toFixed(1)} 分</span></div>
            <div class="bar"><i class="${cls}" style="width:${pct}%"></i></div>
          </div>`;
        }).join("")}
        <p class="tiny muted" style="margin:14px 0 0;padding-top:12px;border-top:1px dashed var(--line)">
          计算方式：各因素归一化后按权重加权，命中硬性红线时直接抬升等级。调整阈值可在教务端修改。
        </p>
      </div>

      <div class="card">
        <div class="card-head">
          <h3>接下来做什么</h3>
          <span class="hint">${d.actions.length} 条行动建议</span>
        </div>
        ${d.actions.map((a, i) => `
          <div class="action-item">
            <div class="action-no">${i + 1}</div>
            <div class="action-body">
              <b>${esc(a.title)}</b>
              <p>${esc(a.detail)}</p>
              <div class="action-meta">
                <span class="tag ${a.priority === "high" ? "high" : ""}">${a.priority === "high" ? "优先" : "常规"}</span>
                <span>${esc(a.owner)}</span><span>${esc(a.deadline)}</span>
              </div>
            </div>
          </div>`).join("")}
      </div>
    </div>

    <div class="card" style="margin-top:14px">
      <div class="card-head">
        <h3>课程风险明细</h3>
        <span class="hint">挂科概率由期中成绩、作业与出勤共同估算</span>
      </div>
      <table class="table">
        <thead><tr>
          <th>课程</th><th>学分</th><th>期中</th><th>班级均分</th><th>出勤</th><th>作业</th><th>挂科概率</th>
        </tr></thead>
        <tbody>
          ${d.courses.map(c => {
            const p = r.pass_probability.find(x => x.code === c.code);
            const fp = p ? p.fail_probability : 0;
            const color = fp > 0.5 ? "var(--red)" : fp > 0.25 ? "#d97706" : "var(--green)";
            return `<tr>
              <td>${esc(c.name)}<span class="tiny muted"> · ${esc(c.teacher)}</span></td>
              <td class="num">${c.credit}</td>
              <td class="num">${c.midterm}</td>
              <td class="num muted">${p ? p.cohort_avg : "-"}</td>
              <td class="num">缺 ${c.absent}</td>
              <td class="num">${c.hw_submitted}/${c.hw_assigned}</td>
              <td>
                <div style="display:flex;align-items:center;gap:8px">
                  <div class="bar" style="flex:1;height:5px"><i style="width:${(fp * 100).toFixed(0)}%;background:${color}"></i></div>
                  <span class="tiny num" style="color:${color};width:34px">${(fp * 100).toFixed(0)}%</span>
                </div>
              </td>
            </tr>`;
          }).join("")}
        </tbody>
      </table>
    </div>

    <p class="tiny muted" style="margin:14px 2px 0">
      数据来自教务成绩、课堂考勤、作业平台与学习行为日志，仅用于学业帮扶。若数据有误，可在“申诉”中提交复核。
    </p>`;
}

/* ---------------- 辅导员端 ---------------- */
async function renderCounselor(view) {
  const qs = new URLSearchParams();
  if (state.filters.class_name) qs.set("class_name", state.filters.class_name);
  if (state.filters.level) qs.set("level", state.filters.level);
  const data = await api(`/api/students?${qs.toString()}`);
  state.roster = data.rows;
  const red = data.rows.filter(r => r.level === "red").length;
  const yellow = data.rows.filter(r => r.level === "yellow").length;
  const rising = data.rows.filter(r => r.direction === "up" && r.level !== "green").length;
  const avg = data.rows.length ? (data.rows.reduce((a, b) => a + b.score, 0) / data.rows.length).toFixed(1) : 0;

  view.innerHTML = `
    <div class="stats">
      <div class="stat red"><b>${red}</b><span>红色预警 · 本周需谈话</span></div>
      <div class="stat amber"><b>${yellow}</b><span>黄色关注 · 持续观察</span></div>
      <div class="stat"><b>${rising}</b><span>风险较上学期上升</span></div>
      <div class="stat"><b>${avg}</b><span>平均风险分</span></div>
    </div>

    <div class="card">
      <div class="card-head">
        <h3>风险名单（共 ${data.total} 人）</h3>
        <span class="hint">按风险分降序，点击任意一行查看详情</span>
      </div>
      <table class="table">
        <thead><tr>
          <th>学生</th><th>班级</th><th>风险分</th><th>等级</th><th>趋势</th>
          <th>主因</th><th>缺勤</th><th>作业未交</th><th>期中均分</th><th></th>
        </tr></thead>
        <tbody>
          ${state.roster.slice(0, 60).map(r => `
            <tr class="clickable" data-sid="${r.id}">
              <td><b>${esc(r.name)}</b><span class="tiny muted"> ${r.id}</span></td>
              <td>${esc(r.class_name)}</td>
              <td>${scoreChip(r.score, r.level)}</td>
              <td><span class="level-pill ${r.level}" style="font-size:11px">${r.level === "red" ? "红" : r.level === "yellow" ? "黄" : "绿"}</span></td>
              <td>${trendTag(r)}</td>
              <td class="muted">${esc(r.top_factor)}</td>
              <td class="num">${r.absent}</td>
              <td class="num">${r.missed_hw}</td>
              <td class="num">${r.mid_avg}</td>
              <td><span class="tiny" style="color:var(--brand)">查看 →</span></td>
            </tr>`).join("")}
        </tbody>
      </table>
      ${state.roster.length === 0 ? `<div class="empty">没有符合条件的学生</div>` : ""}
    </div>`;

  view.querySelectorAll("tr.clickable").forEach(tr => {
    tr.onclick = () => openStudent(tr.dataset.sid);
  });
}

/* ---------------- 教务端 ---------------- */
async function renderAdmin(view) {
  const o = await api("/api/overview");
  state.overview = o;
  const cfg = state.meta.config;
  const maxClass = Math.max(...Object.values(o.by_class).map(c => c.total));

  view.innerHTML = `
    <div class="stats">
      <div class="stat"><b>${o.total}</b><span>在册学生</span></div>
      <div class="stat red"><b>${o.dist.red}</b><span>红色预警 · ${o.dist_pct.red}%</span></div>
      <div class="stat amber"><b>${o.dist.yellow}</b><span>黄色关注 · ${o.dist_pct.yellow}%</span></div>
      <div class="stat"><b>${o.rising_count}</b><span>风险上升人数</span></div>
    </div>

    <div class="two-col">
      <div class="card">
        <div class="card-head"><h3>风险等级分布</h3><span class="hint">数据截至第 ${state.meta.week} 教学周</span></div>
        ${donutSVG(o.dist)}
      </div>
      <div class="card">
        <div class="card-head"><h3>最普遍的风险因素</h3><span class="hint">全校人均摊到的分数</span></div>
        ${o.top_factors.map(f => `
          <div class="factor">
            <div class="factor-top"><b>${f.label}</b><span class="pt">${f.points} 分</span></div>
            <div class="bar"><i style="width:${Math.min(100, f.points * 3)}%"></i></div>
          </div>`).join("")}
      </div>
    </div>

    <div class="card" style="margin-top:14px">
      <div class="card-head"><h3>班级风险对比</h3><span class="hint">柱长为班级人数，红色段为预警人数</span></div>
      ${Object.entries(o.by_class).map(([name, c]) => {
        const w = (c.total / maxClass) * 100;
        const rw = (c.red / c.total) * 100;
        const yw = (c.yellow / c.total) * 100;
        return `<div style="display:flex;align-items:center;gap:12px;margin-bottom:9px">
          <div style="width:78px;font-size:12.5px">${name}</div>
          <div style="flex:1;height:16px;background:#f3f4f6;border-radius:4px;overflow:hidden;position:relative">
            <div style="width:${w}%;height:100%;display:flex">
              <div style="width:${rw}%;background:#dc2626"></div>
              <div style="width:${yw}%;background:#d97706"></div>
              <div style="flex:1;background:#e5e7eb"></div>
            </div>
          </div>
          <div class="tiny muted" style="width:136px;text-align:right;white-space:nowrap">
            红 ${c.red} · 黄 ${c.yellow} · 均分 ${c.avg_score}
          </div>
        </div>`;
      }).join("")}
    </div>

    <div class="card" style="margin-top:14px">
      <div class="card-head">
        <h3>预警规则配置</h3>
        <span class="hint">修改后立即重算全校，可用于“一校一规”</span>
      </div>
      <div class="three-col">
        <div class="field">
          <label>红色预警线（风险分 ≥）</label>
          <input type="number" id="cfgRed" value="${cfg.red_line}" min="1" max="100" step="1" />
          <div class="hint">当前 ${o.dist.red} 人</div>
        </div>
        <div class="field">
          <label>黄色关注线（风险分 ≥）</label>
          <input type="number" id="cfgYellow" value="${cfg.yellow_line}" min="0" max="99" step="1" />
          <div class="hint">当前 ${o.dist.yellow} 人</div>
        </div>
        <div class="field">
          <label>缺勤率硬性触发线</label>
          <input type="number" id="cfgAbsence" value="${Math.round(cfg.policy.absence_warn_ratio * 100)}" min="5" max="80" step="5" />
          <div class="hint">单位 %，超过直接抬升等级</div>
        </div>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <button class="btn primary" id="btnSaveCfg">保存并重算</button>
        <span class="tiny muted" id="cfgMsg"></span>
      </div>
    </div>`;

  el("btnSaveCfg").onclick = async () => {
    const red = Number(el("cfgRed").value);
    const yellow = Number(el("cfgYellow").value);
    const absence = Number(el("cfgAbsence").value) / 100;
    el("cfgMsg").textContent = "重算中…";
    try {
      const res = await api("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ red_line: red, yellow_line: yellow, absence_warn_ratio: absence }),
      });
      state.meta.config = res.config;
      el("cfgMsg").textContent = `已重算：红色 ${res.overview.dist.red} 人，黄色 ${res.overview.dist.yellow} 人`;
      render();
    } catch (e) {
      el("cfgMsg").textContent = "保存失败：" + e.message;
    }
  };
}

/* ---------------- 家长端 ---------------- */
async function renderParent(view) {
  const d = await api(`/api/students/${state.sid}`);
  const s = d.student, r = d.risk;
  const tone = r.level === "red"
    ? "本学期学业状态需要重点关注，学校已启动帮扶。"
    : r.level === "yellow"
      ? "本学期部分指标出现下滑，建议近期与孩子沟通一次。"
      : "本学期整体状态正常，保持现有节奏即可。";

  view.innerHTML = `
    <div class="card" style="border-left:3px solid ${LEVEL_COLOR[r.level]}">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:20px;flex-wrap:wrap">
        <div>
          <div class="risk-title"><span class="risk-name">${esc(s.name)}</span>
            <span class="level-pill ${r.level}">${r.level_label}</span></div>
          <p class="tiny muted" style="margin:0">${esc(s.class_name)} · ${esc(s.major)} · 辅导员 ${esc(s.advisor)}</p>
          <p style="margin:12px 0 0;font-size:13.5px">${tone}</p>
        </div>
        <div style="text-align:center">${ringSVG(r.score, r.level)}</div>
      </div>
      <div class="risk-facts" style="margin-top:16px">
        <div class="fact"><b>${r.raw.absent} 次</b><span>本学期缺勤</span></div>
        <div class="fact"><b>${r.raw.hw_submitted}/${r.raw.hw_assigned}</b><span>作业提交</span></div>
        <div class="fact"><b>${r.raw.mid_avg}</b><span>期中加权均分</span></div>
        <div class="fact"><b>${s.credits.earned}</b><span>已修学分</span></div>
      </div>
    </div>

    <div class="two-col" style="margin-top:14px">
      <div class="card">
        <div class="card-head"><h3>学校正在做什么</h3><span class="hint">已启动的帮扶动作</span></div>
        ${d.actions.slice(0, 3).map((a, i) => `
          <div class="action-item">
            <div class="action-no">${i + 1}</div>
            <div class="action-body">
              <b>${esc(a.title)}</b>
              <p>${esc(a.detail)}</p>
              <div class="action-meta"><span>${esc(a.owner)}</span><span>${esc(a.deadline)}</span></div>
            </div>
          </div>`).join("")}
      </div>
      <div class="card">
        <div class="card-head"><h3>家长可以配合的</h3><span class="hint">比追问成绩更有效的三件事</span></div>
        <div class="action-item"><div class="action-no">1</div><div class="action-body">
          <b>先问状态，不问分数</b>
          <p>“最近睡得怎么样、课听得懂吗”比“为什么考这么差”更容易得到真实回答。</p></div></div>
        <div class="action-item"><div class="action-no">2</div><div class="action-body">
          <b>确认是否有实际困难</b>
          <p>作息颠倒、经济压力、情绪问题都会表现为缺勤和作业拖延，这类问题需要学校介入。</p></div></div>
        <div class="action-item"><div class="action-no">3</div><div class="action-body">
          <b>与辅导员保持固定联系</b>
          <p>约定每两周沟通一次，比出事才联系更有效。辅导员：${esc(s.advisor)}。</p></div></div>
        <p class="tiny muted" style="margin-top:12px;padding-top:10px;border-top:1px dashed var(--line)">
          学校不会仅凭系统评分作出处分，任何预警都会经过人工核实，家长和学生均可提出申诉。
        </p>
      </div>
    </div>`;

  setupChat();
}

/* ---------------- 弹窗 ---------------- */
function openModal(title, sub, body, foot) {
  el("modalTitle").textContent = title;
  el("modalSub").textContent = sub || "";
  el("modalBody").innerHTML = body;
  el("modalFoot").innerHTML = foot || `<button class="btn" onclick="closeModal()">关闭</button>`;
  el("modal").classList.add("open");
}
function closeModal() { el("modal").classList.remove("open"); }
window.closeModal = closeModal;
el("modalClose").onclick = closeModal;
el("modal").onclick = e => { if (e.target === el("modal")) closeModal(); };

async function openStudent(sid) {
  const d = await api(`/api/students/${sid}`);
  const s = d.student, r = d.risk;
  const body = `
    <div style="display:flex;gap:18px;align-items:center;margin-bottom:14px">
      ${ringSVG(r.score, r.level)}
      <div>
        <h3 style="margin:0 0 4px;font-size:16px">${esc(s.name)} <span class="level-pill ${r.level}">${r.level_label}</span></h3>
        <div class="tiny muted">${esc(s.class_name)} · ${esc(s.major)} · 辅导员 ${esc(s.advisor)}</div>
        <div class="tiny" style="margin-top:6px">较上学期 <b>${r.trend.delta > 0 ? "+" : ""}${r.trend.delta.toFixed(0)}</b> 分（${r.trend.label}）</div>
      </div>
    </div>
    <h3>风险构成</h3>
    ${r.factors.map(f => `<div class="factor">
      <div class="factor-top"><b>${f.label}</b><span class="pt">${f.points.toFixed(1)} 分</span></div>
      <div class="bar"><i style="width:${Math.min(100, f.value * 100)}%"></i></div></div>`).join("")}
    <h3>关键事实</h3>
    <ul>
      <li>缺勤 ${r.raw.absent} / ${r.raw.sessions} 次，作业 ${r.raw.hw_submitted}/${r.raw.hw_assigned}</li>
      <li>期中加权均分 ${r.raw.mid_avg}，班级均分 ${r.raw.cohort_avg}</li>
      <li>上学期 GPA ${s.history.gpa}，累计挂科 ${s.history.failed_credits} 学分</li>
      <li>平台每周登录 ${s.engagement.weekly_logins} 次，${s.engagement.days_since_active} 天未活跃</li>
    </ul>
    <h3>建议先做的三件事</h3>
    <ol>${d.actions.slice(0, 3).map(a => `<li><b>${esc(a.title)}</b>——${esc(a.detail)}</li>`).join("")}</ol>
    <h3>跟踪记录</h3>
    <div id="ivList">${(d.interventions || []).length
      ? d.interventions.map(i => `<div class="tiny" style="padding:4px 0;border-bottom:1px dashed var(--line)">
          <b>${esc(i.title)}</b> · ${esc(i.status)} · ${esc(i.created_at)}${i.note ? " · " + esc(i.note) : ""}</div>`).join("")
      : '<div class="tiny muted">暂无记录</div>'}</div>
    <div style="display:flex;gap:8px;margin-top:10px">
      <input id="ivNote" placeholder="记录一次谈话/联系，例如：已约周三下午面谈" style="flex:1;height:32px;border:1px solid var(--line-strong);border-radius:8px;padding:0 10px;font-size:12.5px" />
      <button class="btn sm" id="btnAddIv">添加记录</button>
    </div>`;

  openModal("学生详情", `${s.id} · ${s.class_name}`, body, `
    <button class="btn" id="mBrief">生成谈话要点</button>
    <button class="btn primary" id="mLetter">生成告知函</button>`);

  el("mBrief").onclick = async () => {
    const l = await api(`/api/letters/${sid}?type=counselor`);
    openModal(l.title, l.subject, mdToHtml(l.body) + citationsHTML(l.citations), `<button class="btn" onclick="closeModal()">关闭</button>`);
  };
  el("mLetter").onclick = () => openLetter(sid, "student");
  el("btnAddIv").onclick = async () => {
    const note = el("ivNote").value.trim();
    if (!note) return;
    await api(`/api/interventions/${sid}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: note.slice(0, 30), note, status: "已记录" }),
    });
    el("btnAddIv").textContent = "已保存";
  };
}

async function openLetter(sid, type) {
  const l = await api(`/api/letters/${sid}?type=${type}`);
  openModal(l.title, l.subject, mdToHtml(l.body) + citationsHTML(l.citations), `
    <button class="btn" id="mCopy">复制正文</button>
    <button class="btn primary" onclick="closeModal()">完成</button>`);
  el("mCopy").onclick = () => {
    navigator.clipboard.writeText(l.body).then(() => { el("mCopy").textContent = "已复制"; });
  };
}

async function openClassReport() {
  const cls = state.filters.class_name || state.meta.classes[0];
  const r = await api(`/api/reports/${encodeURIComponent(cls)}`);
  openModal(r.title, r.subject, mdToHtml(r.body), `<button class="btn primary" onclick="closeModal()">完成</button>`);
}

function citationsHTML(cites) {
  if (!cites || !cites.length) return "";
  return `<h3>引用来源</h3>` + cites.map(c =>
    `<div class="cite" style="margin-bottom:6px"><b>${esc(c.citation)}</b><br>${esc(c.text).slice(0, 160)}…</div>`).join("");
}

/* ---------------- 导出 ---------------- */
async function exportCSV() {
  const data = await api("/api/students?limit=300");
  const head = ["学号", "姓名", "班级", "风险分", "等级", "趋势", "主因", "缺勤", "作业未交", "期中均分"];
  const rows = data.rows.map(r => [r.id, r.name, r.class_name, r.score, r.level_label,
    r.delta, r.top_factor, r.absent, r.missed_hw, r.mid_avg]);
  const csv = "\ufeff" + [head, ...rows].map(r => r.map(x => `"${x}"`).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `学业预警名单_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

/* ---------------- 对话 ---------------- */
function chatRoleMeta() {
  return {
    student: ["学业助手", "基于你的学情数据回答，不猜不编"],
    counselor: ["辅导员助手", "可以问名单、原因、谈话建议"],
    admin: ["教务助手", "全校统计与规则问题"],
    parent: ["家校助手", "用通俗的话说明情况"],
  }[state.role];
}

function setupChat() {
  const [t, sub] = chatRoleMeta();
  el("chatTitle").textContent = t;
  el("chatSub").textContent = sub;
  if (state.chatReset) {
    el("chatBody").innerHTML = "";
    delete el("chatBody").dataset.ready;
    state.chatReset = false;
  }
  if (!state.suggest) state.suggest = DEFAULT_SUGGEST[state.role];
  if (!el("chatBody").dataset.ready) {
    el("chatBody").innerHTML = `<div class="msg"><div class="bubble">${
      state.role === "student" ? "我是你的学业助手。可以问我风险分怎么来的、哪门课最危险、这学期还来不来得及。"
        : state.role === "counselor" ? "我是辅导员助手。可以问“本班谁风险上升最快”“给某人生成谈话要点”。"
        : state.role === "admin" ? "我是教务助手。可以问全校分布、班级对比，或某条校规的具体规定。"
        : "我是家校助手。可以问孩子这学期的情况，或学校什么情况下会通知家长。"
    }</div></div>`;
    el("chatBody").dataset.ready = "1";
  }
  el("chatSuggest").innerHTML = (state.suggest || []).map(s =>
    `<button class="chip">${esc(s)}</button>`).join("");
  el("chatSuggest").querySelectorAll(".chip").forEach(b => {
    b.onclick = () => sendChat(b.textContent);
  });
}

async function sendChat(text) {
  if (state.busy) return;
  state.busy = true;
  const body = el("chatBody");
  body.insertAdjacentHTML("beforeend", `<div class="msg user"><div class="bubble">${esc(text)}</div></div>`);
  body.insertAdjacentHTML("beforeend", `<div class="msg" id="thinking"><div class="bubble"><span class="spinner"></span></div></div>`);
  body.scrollTop = body.scrollHeight;

  try {
    const res = await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: state.role, sid: state.sid, message: text }),
    });
    el("thinking")?.remove();
    const cites = (res.citations || []).map(c =>
      `<div class="cite"><b>${esc(c.citation)}</b> · ${esc(c.text).slice(0, 90)}…</div>`).join("");
    const trace = (res.trace || []).map(t => `<span>${esc(t.tool)}</span>`).join("");
    body.insertAdjacentHTML("beforeend", `<div class="msg">
      <div class="bubble">${mdToHtml(res.reply)}</div>
      ${cites}
      <div class="trace">${trace}<span>${res.elapsed_ms} ms</span></div>
    </div>`);
    if (res.suggestions?.length) {
      state.suggest = res.suggestions;
      el("chatSuggest").innerHTML = res.suggestions.map(s => `<button class="chip">${esc(s)}</button>`).join("");
      el("chatSuggest").querySelectorAll(".chip").forEach(b => b.onclick = () => sendChat(b.textContent));
    }
  } catch (e) {
    el("thinking")?.remove();
    body.insertAdjacentHTML("beforeend", `<div class="msg"><div class="bubble">出错了：${esc(e.message)}</div></div>`);
  }
  body.scrollTop = body.scrollHeight;
  state.busy = false;
}

el("chatForm").onsubmit = e => {
  e.preventDefault();
  const v = el("chatInput").value.trim();
  if (!v) return;
  el("chatInput").value = "";
  sendChat(v);
};

el("chatClose").onclick = () => {
  const p = el("chatPanel");
  p.classList.remove("open");
  p.classList.add("hidden");
};
el("chatFab").onclick = () => {
  const p = el("chatPanel");
  p.classList.remove("hidden");
  p.classList.add("open");
};

/* ---------------- 启动 ---------------- */
(async function init() {
  try {
    state.meta = await api("/api/meta");
    el("termText").textContent = state.meta.term;
    el("weekText").textContent = `第 ${state.meta.week} 周`;
    el("updatedAt").textContent = `数据更新于 ${state.meta.updated_at}`;
    const badge = el("llmBadge");
    if (state.meta.llm.enabled) {
      badge.textContent = `大模型已接入 · ${state.meta.llm.model}`;
      badge.classList.add("on");
    } else {
      badge.textContent = "规则引擎模式 · 可接入大模型";
    }
    state.sid = state.meta.demo.student;
    const hash = (location.hash || "").replace("#", "");
    if (["student", "counselor", "admin", "parent"].includes(hash)) {
      state.role = hash;
      if (hash === "parent") state.sid = state.meta.demo.parent;
      if (hash === "counselor" || hash === "admin") state.sid = null;
    }
    renderRoleNav();
    // 窄屏（手机 / 小笔记本）聊天面板是浮层，默认收起，避免一进来就盖住正文
    if (window.innerWidth < 1080) el("chatPanel").classList.add("hidden");
    await render();
  } catch (e) {
    el("view").innerHTML = `<div class="card">初始化失败：${esc(e.message)}</div>`;
  }
})();
