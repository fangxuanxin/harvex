// fxharvest Web UI 前端逻辑（原生 JS，无框架/无依赖）。
// 列动态渲染：表头与单元格由后端返回的记录字段决定，适配任意项目的字段模型。

"use strict";

const state = { q: "", limit: 50, offset: 0, total: 0, columns: [] };

const $ = (sel) => document.querySelector(sel);

// —— 视图切换（hash 路由） ——
function showView() {
  const hash = location.hash.replace("#", "") || "records";
  const view = hash === "health" ? "health" : "records";
  $("#view-records").hidden = view !== "records";
  $("#view-health").hidden = view !== "health";
  document.querySelectorAll(".tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.view === view);
  });
  if (view === "health") loadHealth();
  else loadRecords();
}

// —— 记录列表 ——
async function loadRecords() {
  const params = new URLSearchParams({ limit: state.limit, offset: state.offset });
  if (state.q) params.set("q", state.q);
  let data;
  try {
    const resp = await fetch(`/api/records?${params}`);
    data = await resp.json();
  } catch (e) {
    $("#body").innerHTML = `<tr><td>加载失败：${e}</td></tr>`;
    return;
  }
  state.total = data.total || 0;
  renderRecords(data.records || []);
  renderPager();
}

// 业务列：排除框架内部时间戳，id 单独处理
function businessColumns(rec) {
  return Object.keys(rec).filter((k) => k !== "id" && k !== "created_at" && k !== "updated_at");
}

function renderRecords(records) {
  const empty = $("#records-empty");
  const table = $("#records-table");
  if (!records.length) {
    empty.hidden = false; table.hidden = true; $("#head-row").innerHTML = ""; $("#body").innerHTML = "";
    $("#total-badge").textContent = `0 条记录`;
    return;
  }
  empty.hidden = true; table.hidden = false;
  state.columns = businessColumns(records[0]);

  $("#head-row").innerHTML =
    `<th class="col-id">id</th>` + state.columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("");

  $("#body").innerHTML = records.map((rec) => {
    const cells = state.columns.map((c) => `<td title="${escapeAttr(rec[c])}">${escapeHtml(short(rec[c]))}</td>`).join("");
    return `<tr data-id="${rec.id}"><td class="col-id">${rec.id ?? ""}</td>${cells}</tr>`;
  }).join("");

  $("#body").querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => openDetail(tr.dataset.id));
  });
  $("#total-badge").textContent = `${state.total} 条记录`;
}

function renderPager() {
  const from = state.total ? state.offset + 1 : 0;
  const to = Math.min(state.offset + state.limit, state.total);
  $("#page-info").textContent = `${from}–${to} / ${state.total}`;
  $("#prev").disabled = state.offset <= 0;
  $("#next").disabled = state.offset + state.limit >= state.total;
}

// —— 详情抽屉 ——
async function openDetail(id) {
  try {
    const resp = await fetch(`/api/record/${id}`);
    if (!resp.ok) return;
    const rec = await resp.json();
    const dl = $("#detail-list");
    dl.innerHTML = Object.entries(rec).map(([k, v]) => {
      const val = looksJson(v)
        ? `<pre>${escapeHtml(prettyJson(v))}</pre>`
        : escapeHtml(String(v ?? ""));
      return `<dt>${escapeHtml(k)}</dt><dd>${val}</dd>`;
    }).join("");
    $("#drawer").hidden = false;
  } catch (_) { /* 忽略 */ }
}

// —— 健康视图 ——
async function loadHealth() {
  let data;
  try {
    const resp = await fetch("/api/health");
    data = await resp.json();
  } catch (e) {
    $("#health-cards").innerHTML = `加载失败：${e}`;
    return;
  }
  $("#total-badge").textContent = `共 ${data.total_records ?? 0} 条`;
  $("#health-cards").innerHTML = (data.summaries || []).map((s) => {
    const st = s.last_status || "running";
    const fails = s.consecutive_failures || 0;
    return `<div class="card">
      <div class="name">${escapeHtml(s.source_slug || "?")}</div>
      <div class="row"><span>最近状态</span><b class="s-${st}"><span class="dot"></span>${escapeHtml(st)}</b></div>
      <div class="row"><span>最近数量</span><b>${s.last_job_count ?? "—"}</b></div>
      <div class="row"><span>连续失败</span><b style="color:${fails ? "var(--bad)" : "inherit"}">${fails}</b></div>
      <div class="row"><span>最近时间</span><b>${fmtTime(s.last_run_at)}</b></div>
    </div>`;
  }).join("") || `<div class="empty">暂无抓取历史。</div>`;

  $("#runs-body").innerHTML = (data.recent_runs || []).map((r) => {
    const st = r.status || "running";
    return `<tr>
      <td>${escapeHtml(r.source_slug || "")}</td>
      <td class="s-${st}"><span class="dot"></span>${escapeHtml(st)}</td>
      <td class="num">${r.job_count ?? ""}</td>
      <td class="num">${r.total_job_count ?? ""}</td>
      <td>${fmtTime(r.started_at)}</td>
      <td>${fmtTime(r.finished_at)}</td>
      <td title="${escapeAttr(r.error_message)}">${escapeHtml(short(r.error_message))}</td>
    </tr>`;
  }).join("") || `<tr><td colspan="7" class="empty">暂无流水。</td></tr>`;
}

// —— 工具函数 ——
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function escapeAttr(s) { return escapeHtml(s).replace(/\n/g, " "); }
function short(s, n = 60) { s = String(s ?? ""); return s.length > n ? s.slice(0, n) + "…" : s; }
function looksJson(v) { return typeof v === "string" && /^[\[{]/.test(v.trim()); }
function prettyJson(v) { try { return JSON.stringify(JSON.parse(v), null, 2); } catch { return v; } }
function fmtTime(s) { return s ? String(s).replace("T", " ").slice(0, 19) : "—"; }

// —— 事件绑定 ——
let searchTimer;
$("#search").addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { state.q = e.target.value.trim(); state.offset = 0; loadRecords(); }, 250);
});
$("#prev").addEventListener("click", () => { state.offset = Math.max(0, state.offset - state.limit); loadRecords(); });
$("#next").addEventListener("click", () => { state.offset += state.limit; loadRecords(); });
$("#drawer-close").addEventListener("click", () => { $("#drawer").hidden = true; });
$("#drawer").addEventListener("click", (e) => { if (e.target.id === "drawer") $("#drawer").hidden = true; });
window.addEventListener("hashchange", showView);

showView();
