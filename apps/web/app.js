const apiBase = window.BANBOOS_API_BASE || "http://127.0.0.1:8000";
const $ = (id) => document.getElementById(id);
let analysisSourceRunId = null;
let analysisScenarioRunId = null;
let analysisAnnualRevenueYuan = null;
let analysisScale = null;
let financialSourceRunId = null;
let portfolioRunId = null;
let financialTemplateAvailable = false;
let lpReconcileRunId = null;
let financialRunId = null;
let portfolioCandidateSnapshotId = null;
let portfolioCandidateSource = new Map();
let importPreviewId = null;

function displaySource(value) {
  if (!value) return "未标注来源";
  const text = String(value);
  if (/^[A-Za-z]:[\\/]/.test(text) || text.includes("\\")) {
    const fileName = text.split(/[\\/]/).filter(Boolean).at(-1);
    if (!fileName) return "本地数据文件";
    const shortName = fileName.length > 24 ? fileName.slice(0, 20) + "…" + fileName.slice(-4) : fileName;
    return "本地文件 · " + shortName;
  }
  return text;
}

const runKindLabels = { financial: "财务测算", sensitivity: "敏感性分析", "price-analysis": "节点电价分析", "strict-dispatch": "约束回放", "lp-analysis": "LP 分析", "portfolio-optimization": "组合优化", "investment-scenario": "投资情景", weather: "气象专题" };
const gateCheckLabels = { api_auth: "接口认证", postgres: "数据库", redis: "任务队列", financial_template: "财务模板", production_control: "生产控制", tenant_isolation: "租户隔离" };
function runKindLabel(value) { return runKindLabels[value] || value || "—"; }

async function get(path, params = {}) {
  const url = new URL(apiBase + path);
  Object.entries(params).filter(([, value]) => value !== "" && value != null).forEach(([key, value]) => url.searchParams.set(key, value));
  const response = await fetch(url);
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || `API ${response.status}`);
  return body;
}

async function post(path, body) {
  const response = await fetch(apiBase + path, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || `API ${response.status}`);
  return result;
}

function setStatus(text, kind = "muted") {
  $("apiState").textContent = text;
  $("apiState").className = `status status-${kind}`;
}

function activateView(viewId) {
  document.querySelectorAll(".view").forEach((view) => { view.hidden = view.id !== viewId; });
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === viewId));
}

function renderStationList(items) {
  const list = $("stationList");
  if (!items.length) { list.innerHTML = '<div class="empty-state">当前筛选没有节点</div>'; return; }
  list.replaceChildren(...items.map((item) => {
    const row = document.createElement("div");
    row.className = "station-row";
    row.innerHTML = `<span class="station-mark">${item.province.slice(0, 1) || "站"}</span><span class="station-name"><b>${item.name}</b><small>${item.province || "未配置省份"}</small></span><span class="station-state"><i></i>只读在线</span>`;
    return row;
  }));
}

async function loadNodes() {
  ReportUI.invalidate("curve"); ReportUI.invalidate("weather");
  const body = await get("/api/v1/nodes");
  const selectedProvince = $("province").value;
  const provinces = [...new Set(body.items.map((item) => item.province).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN"));
  $("province").replaceChildren(new Option("全部省份", ""), ...provinces.map((name) => new Option(name, name)));
  if (provinces.includes(selectedProvince)) $("province").value = selectedProvince;
  body.items = body.items.filter((item) => !$("province").value || item.province === $("province").value);
  renderStationList(body.items);
  $("overviewNodes").textContent = body.items.length;
  $("node").replaceChildren(...body.items.map((item) => new Option(`${item.name} · ${item.province}`, item.id)));
  $("curveNode").replaceChildren(...body.items.map((item) => new Option(`${item.name} · ${item.province}`, item.id)));
  $("weatherNode").replaceChildren(...body.items.map((item) => new Option(`${item.name} · ${item.province}`, item.id)));
  $("dispatchNode").replaceChildren(...body.items.map((item) => new Option(`${item.name} · ${item.province}`, item.id)));
  if (!body.items.length) $("node").add(new Option("暂无节点", ""));
  if (!body.items.length) $("curveNode").add(new Option("暂无节点", ""));
  if (!body.items.length) $("weatherNode").add(new Option("暂无节点", ""));
  if (!body.items.length) $("dispatchNode").add(new Option("暂无节点", ""));
  await syncDateRange();
  let summaryAvailable = true;
  try { await refreshOperationsSummary(); } catch { summaryAvailable = false; }
  setStatus(summaryAvailable ? `API 已连接 · ${body.data_mode}` : "运营摘要暂不可用", summaryAvailable ? "ok" : "error");
}

async function loadPortfolio() {
  const state = $("portfolioState"); const body = $("portfolioBody"); state.textContent = "加载中"; body.replaceChildren();
  try {
    const nodes = await get("/api/v1/nodes");
    const rows = await Promise.all(nodes.items.map(async (node) => {
      const summary = await get("/api/v1/price/summary", { node_id: node.id, market: $("portfolioMarket").value, start_date: $("portfolioStart").value, end_date: $("portfolioEnd").value });
      const coverage = (summary.valid_days && summary.data_points) ? `${(summary.data_points / (summary.valid_days * 96) * 100).toFixed(1)}%` : "0.0%";
      return [node.name, node.province || "—", summary.valid_days, summary.data_points.toLocaleString(), coverage, summary.valid_days ? "可评估" : "数据不足"];
    }));
    rows.forEach((values) => { const tr = document.createElement("tr"); values.forEach((value) => { const td = document.createElement("td"); td.textContent = value; tr.appendChild(td); }); body.appendChild(tr); });
    const provinceMap = new Map(); rows.forEach((row) => { const key = row[1]; const item = provinceMap.get(key) || { nodes: 0, days: 0, coverage: 0 }; item.nodes += 1; item.days += Number(row[2]) || 0; item.coverage += Number.parseFloat(row[4]) || 0; provinceMap.set(key, item); });
    const provinceBody = $("provinceBody"); provinceBody.replaceChildren(); provinceMap.forEach((item, province) => { const tr = document.createElement("tr"); [province, item.nodes, item.days, `${(item.coverage / item.nodes).toFixed(1)}%`].forEach((value) => { const td = document.createElement("td"); td.textContent = value; tr.appendChild(td); }); provinceBody.appendChild(tr); });
    state.textContent = `${rows.length} 个节点`; state.className = "status status-ok";
  } catch (error) { state.textContent = "加载失败"; state.className = "status status-error"; body.innerHTML = `<tr><td colspan="6">${error.message}</td></tr>`; }
}

function invalidatePortfolio() {
  ReportUI.clearRun("portfolioOptimizer");
  $("portfolioOptState").textContent = "待计算";
  $("portfolioOptState").className = "status status-muted";
  $("portfolioOptBody").innerHTML = '<tr><td colspan="4">参数已修改，请重新计算。</td></tr>';
  $("portfolioOptMessage").textContent = "当前为手工情景；修改后的参数尚未计算。";
}

function syncPortfolioObjective() {
  const minimum = $("portfolioObjective").value === "min_investment";
  $("portfolioRevenueTarget").disabled = !minimum;
  $("portfolioRevenueTarget").required = minimum;
  $("portfolioBudget").required = !minimum;
}

function addPortfolioProject(project = {}) {
  const body = $("portfolioProjectBody");
  if (body.rows.length >= 50) return;
  const row = document.createElement("tr");
  row.dataset.nodeId = project.node_id == null ? "" : String(project.node_id);
  const number = body.rows.length + 1;
  [["name", "项目名称", "text", null, 120], ["capacity_mwh", "容量", "number", 0.001, 1000000],
    ["unit_investment_yuan_wh", "单位投资", "number", 0.000001, 100],
    ["annual_revenue_wan", "年净现金流", "number", 0, 1000000000]].forEach(([key, label, type, min, max]) => {
    const td = document.createElement("td"); const input = document.createElement("input");
    input.type = type; input.dataset.field = key; input.required = true;
    input.setAttribute("aria-label", `项目 ${number} ${label}`);
    if (type === "number") { input.min = min; input.max = max; input.step = "any"; }
    else input.maxLength = max;
    input.value = project[key] ?? ""; td.append(input); row.append(td);
  });
  const action = document.createElement("td"); const remove = document.createElement("button");
  remove.type = "button"; remove.textContent = "删除"; remove.setAttribute("aria-label", `删除项目 ${number}`);
  remove.addEventListener("click", () => { row.remove(); $("addPortfolioProject").disabled = false; invalidatePortfolio(); });
  action.append(remove); row.append(action); body.append(row);
  $("addPortfolioProject").disabled = body.rows.length >= 50;
}

async function generatePortfolioCandidates() {
  const button = $("generatePortfolioCandidates"); const message = $("portfolioOptMessage");
  const power = Number($("portfolioPower").value); const capacity = Number($("portfolioCapacity").value);
  if (!Number.isFinite(power) || !Number.isFinite(capacity) || capacity / power < 0.25 || capacity / power > 24) {
    message.textContent = "候选项目规模无效：容量/功率时长须在 0.25 至 24 小时之间。"; return;
  }
  button.disabled = true; message.textContent = "正在读取真实节点并生成候选项目…";
  const query = { market: $("portfolioMarket").value, start_date: $("portfolioStart").value,
    end_date: $("portfolioEnd").value, power_mw: power, capacity_mwh: capacity, round_trip_efficiency: 0.92 };
  const ticket = ReportUI.begin("portfolioCandidates", query, "原始候选快照");
  $("exportPortfolioCandidates").disabled = true;
  $("optimizePortfolioSnapshot").disabled = true;
  try {
    const result = await get("/api/v1/portfolio/candidates", query);
    if (!ReportUI.current("portfolioCandidates", ticket)) return;
    $("portfolioProjectBody").replaceChildren();
    portfolioCandidateSnapshotId = result.snapshot_id === "demo" ? null : result.snapshot_id;
    portfolioCandidateSource = new Map(result.candidates.map((candidate) => [String(candidate.node_id), structuredClone(candidate)]));
    result.candidates.forEach(addPortfolioProject);
    $("exportPortfolioCandidates").disabled = !result.candidates.length;
    ReportUI.complete("portfolioCandidates", ticket, portfolioCandidateSnapshotId ? result.candidates.length : 0,
      result.algorithm_version, { snapshot_id: portfolioCandidateSnapshotId });
    $("optimizePortfolioSnapshot").disabled = !portfolioCandidateSnapshotId || !result.candidates.length;
    invalidatePortfolio();
    message.textContent = `已生成 ${result.candidates.length} 个真实节点候选（${result.market}，${result.start_date} 至 ${result.end_date}）；快照 ${result.snapshot_id.slice(0, 12)}…；请确认预算和目标后运行组合优化。`;
  } catch (error) {
    if (!ReportUI.current("portfolioCandidates", ticket)) return;
    ReportUI.invalidate("portfolioCandidates", `候选生成失败：${error.message}`);
    message.textContent = `候选生成失败：${error.message}`;
  }
  finally { button.disabled = false; }
}

async function optimizePortfolioSnapshot() {
  if (!portfolioCandidateSnapshotId) return;
  const message = $("portfolioOptMessage"); const button = $("optimizePortfolioSnapshot");
  button.disabled = true; message.textContent = "正在按原始候选快照提交组合优化…";
  const parameters = { objective: $("portfolioObjective").value,
    budget_limit_wan: $("portfolioBudget").value === "" ? null : Number($("portfolioBudget").value),
    revenue_target_wan: $("portfolioRevenueTarget").disabled ? null : Number($("portfolioRevenueTarget").value),
    discount_rate: Number($("portfolioRate").value) / 100, operation_years: Number($("portfolioYears").value) };
  try {
    const run = await post("/api/v1/portfolio/candidates/" + portfolioCandidateSnapshotId + "/optimize", parameters);
    portfolioRunId = run.run_id; $("resumePortfolio").hidden = false;
    await pollPortfolio();
  } catch (error) { message.textContent = "快照优化失败：" + error.message; }
  finally { button.disabled = false; }
}

function exportPortfolioCandidates() {
  const rows = Array.from($("portfolioProjectBody").rows).map((row) => {
    const values = Object.fromEntries(Array.from(row.querySelectorAll("input"), (input) => [input.dataset.field, input.value]));
    return { node_id: row.dataset.nodeId || "", ...values };
  });
  if (!rows.length) return;
  const columns = ["node_id", "name", "capacity_mwh", "unit_investment_yuan_wh", "annual_revenue_wan"];
  const csv = [
    `# snapshot_id=${portfolioCandidateSnapshotId || "manual"}`,
    columns.join(","),
    ...rows.map((row) => columns.map((column) => `"${String(row[column] ?? "").replaceAll('"', '""')}"`).join(",")),
  ].join("\r\n");
  const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a"); link.href = URL.createObjectURL(blob);
  link.download = `banboos-portfolio-candidates-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click(); URL.revokeObjectURL(link.href);
}

function renderPortfolioResult(result) {
  const body = $("portfolioOptBody"); body.replaceChildren();
  result.selected_projects.forEach((project) => {
    const tr = document.createElement("tr");
    [project.name, project.investment_wan.toFixed(2), project.npv_wan.toFixed(2), project.annual_revenue_wan.toFixed(2)].forEach((value) => {
      const td = document.createElement("td"); td.textContent = value; tr.append(td);
    }); body.append(tr);
  });
  if (!result.selected_projects.length) {
    const tr = document.createElement("tr"); const td = document.createElement("td");
    td.colSpan = 4; td.textContent = result.message; tr.append(td); body.append(tr);
  }
  $("portfolioOptState").textContent = result.outcome === "optimal" ? "计算完成" : "无可选组合";
  $("portfolioOptState").className = `status status-${result.outcome === "optimal" ? "ok" : "muted"}`;
  $("portfolioOptMessage").textContent = `${result.message} 总投资 ${result.total_investment_wan.toFixed(2)} 万元 · 总 NPV ${result.total_npv_wan.toFixed(2)} 万元 · 组合 IRR ${result.portfolio_irr == null ? "无有效根" : (result.portfolio_irr * 100).toFixed(2) + "%"}。${result.cashflow_note}`;
  ReportUI.run("portfolioOptimizer", portfolioRunId, "组合优化", apiBase);
}

async function pollPortfolio() {
  for (let i = 0; i < 90; i += 1) {
    const status = await get(`/api/v1/runs/${portfolioRunId}`);
    $("portfolioOptMessage").textContent = `${status.message || "计算中"} · ${status.progress}% · 任务 ${portfolioRunId}`;
    if (status.status === "succeeded") { renderPortfolioResult(status.result); return; }
    if (["failed", "cancelled"].includes(status.status)) throw new Error(status.message);
    await new Promise((resolve) => setTimeout(resolve, 700));
  }
  throw new Error("任务仍在后台执行，可点击恢复上次任务继续查询。");
}

async function submitPortfolio(event) {
  event.preventDefault();
  if (!$("portfolioProjectBody").rows.length) {
    $("portfolioOptMessage").textContent = "请至少添加一个候选项目。"; return;
  }
  const projects = Array.from($("portfolioProjectBody").rows, (row) => Object.fromEntries(
    Array.from(row.querySelectorAll("input"), (input) => [input.dataset.field, input.type === "number" ? Number(input.value) : input.value.trim()])));
  const changed = projects.filter((project, index) => {
    const nodeId = $("portfolioProjectBody").rows[index].dataset.nodeId;
    const source = portfolioCandidateSource.get(nodeId);
    return source && ["name", "capacity_mwh", "unit_investment_yuan_wh", "annual_revenue_wan"].some((key) =>
      String(project[key]) !== String(source[key]));
  }).length;
  const parameters = { objective: $("portfolioObjective").value, projects,
    budget_limit_wan: $("portfolioBudget").value === "" ? null : Number($("portfolioBudget").value),
    revenue_target_wan: $("portfolioRevenueTarget").disabled ? null : Number($("portfolioRevenueTarget").value),
    discount_rate: Number($("portfolioRate").value) / 100, operation_years: Number($("portfolioYears").value) };
  invalidatePortfolio();
  if (changed && portfolioCandidateSnapshotId) {
    $("portfolioOptMessage").textContent = `已基于快照 ${portfolioCandidateSnapshotId.slice(0, 12)}…提交；其中 ${changed} 个节点候选包含手工调整。`;
  }
  $("portfolioFields").disabled = true; $("resumePortfolio").disabled = true;
  $("portfolioOptState").textContent = "计算中";
  try {
    const run = await post("/api/v1/runs", { kind: "portfolio-optimization", parameters });
    portfolioRunId = run.run_id;
    try { localStorage.setItem("banboosPortfolioRun", portfolioRunId); } catch { /* Storage can be disabled. */ }
    $("resumePortfolio").hidden = false;
    await pollPortfolio();
  } catch (error) {
    $("portfolioOptState").textContent = "请检查任务"; $("portfolioOptState").className = "status status-error";
    $("portfolioOptMessage").textContent = error.message;
  } finally { $("portfolioFields").disabled = false; $("resumePortfolio").disabled = false; }
}

async function resumePortfolio() {
  if (!portfolioRunId) return;
  $("portfolioFields").disabled = true; $("resumePortfolio").disabled = true;
  ReportUI.clearRun("portfolioOptimizer");
  try {
    const run = await get(`/api/v1/runs/${portfolioRunId}`);
    if (run.kind !== "portfolio-optimization") throw new Error("任务类型不匹配");
    const p = run.parameters;
    $("portfolioObjective").value = p.objective; $("portfolioBudget").value = p.budget_limit_wan ?? "";
    $("portfolioRevenueTarget").value = p.revenue_target_wan ?? "";
    $("portfolioRate").value = p.discount_rate * 100; $("portfolioYears").value = p.operation_years;
    $("portfolioProjectBody").replaceChildren(); p.projects.forEach(addPortfolioProject);
    syncPortfolioObjective(); await pollPortfolio();
  } catch (error) { $("portfolioOptMessage").textContent = error.message; }
  finally { $("portfolioFields").disabled = false; $("resumePortfolio").disabled = false; }
}

async function refreshLegacyManagement() {
  const kind = $("legacyTableKind").value; const state = $("legacyState");
  const head = $("legacyHead"); const body = $("legacyBody");
  state.textContent = "读取隔离副本中…"; head.replaceChildren(); body.replaceChildren();
  try {
    const result = await get(`/api/v1/legacy/${kind}`, { limit: 200 });
    const items = result.items || [];
    if (!items.length) { body.innerHTML = '<tr><td>当前数据模式没有可显示的管理记录</td></tr>'; state.textContent = `0 条 · ${result.source_mode}`; return; }
    const columns = Object.keys(items[0]);
    columns.forEach((column) => { const th = document.createElement("th"); th.textContent = column; head.append(th); });
    items.forEach((item) => { const tr = document.createElement("tr"); columns.forEach((column) => { const td = document.createElement("td"); td.textContent = item[column] == null ? "—" : String(item[column]); tr.append(td); }); body.append(tr); });
    state.textContent = `${items.length} 条 · ${result.source_mode}`;
  } catch (error) { state.textContent = `读取失败：${error.message}`; body.innerHTML = '<tr><td>请检查 API 和隔离副本配置</td></tr>'; }
}

async function refreshSystem() {
  const health = $("systemHealth"); const ready = $("systemReady"); const checks = $("systemChecks");
  try { const [healthBody, meta] = await Promise.all([get("/health"), get("/api/v1/meta")]); financialTemplateAvailable = meta.financial_template_available === "True"; health.textContent = healthBody.status === "ok" ? "正常" : (healthBody.status || "异常"); health.className = healthBody.status === "ok" ? "value-ok" : "value-error"; $("systemHealthDetail").textContent = `版本 ${healthBody.version || "—"}`; $("systemMode").textContent = meta.data_mode === "staging-readonly" ? "隔离只读" : (meta.data_mode || "—"); } catch (error) { financialTemplateAvailable = false; health.textContent = "异常"; health.className = "value-error"; $("systemHealthDetail").textContent = error.message; $("systemMode").textContent = "不可用"; }
  try { const body = await get("/readyz"); const isReady = body.status === "ready"; ready.textContent = isReady ? "已就绪" : (body.status || "未就绪"); ready.className = isReady ? "value-ok" : "value-error"; $("systemReadyDetail").textContent = isReady ? "所有依赖已就绪" : "存在待处理依赖"; checks.textContent = JSON.stringify(body.checks || {}, null, 2); } catch (error) { ready.textContent = "未就绪"; ready.className = "value-error"; $("systemReadyDetail").textContent = error.message; checks.textContent = error.message; }
  try { const runs = await get("/api/v1/runs", { kind: $("systemRunKind").value, status: $("systemRunStatus").value, limit: 50 }); const body = $("systemRunsBody"); body.replaceChildren(); runs.forEach((run) => { const tr = document.createElement("tr"); const values = [runKindLabel(run.kind), run.status, `${run.progress}%`, run.created_at ? new Date(run.created_at).toLocaleString("zh-CN") : "—", run.error_code || "—"]; values.forEach((value, index) => { const td = document.createElement("td"); if (index === 1) { const badge = document.createElement("span"); badge.className = `status ${run.status === "succeeded" ? "status-ok" : run.status === "failed" ? "status-error" : "status-muted"}`; badge.textContent = run.status === "succeeded" ? "已完成" : run.status === "failed" ? "失败" : run.status === "running" ? "运行中" : "排队中"; td.appendChild(badge); } else { td.textContent = value; } tr.appendChild(td); }); body.appendChild(tr); }); $("systemRunsState").textContent = `${runs.length} 条记录`; $("systemRunsState").className = `status ${runs.length ? "status-ok" : "status-muted"}`; } catch (error) { $("systemRunsState").textContent = "加载失败"; $("systemRunsState").className = "status status-error"; }
}

async function syncCurveDateRange() {
  const nodeId = $("curveNode").value;
  if (!nodeId) return;
  const range = await get("/api/v1/price/range", { node_id: nodeId, market: $("curveMarket").value });
  if (range.first_date) $("curveStart").value = range.first_date;
  if (range.last_date) $("curveEnd").value = range.last_date;
}

let curvePointer = null;

function priceColor(value, min, max) {
  const ratio = Math.max(0, Math.min(1, (value - min) / Math.max(1, max - min)));
  const stops = [[0, [190, 62, 62]], [0.5, [211, 164, 45]], [1, [23, 107, 80]]];
  const upper = stops.findIndex(([stop]) => ratio <= stop);
  if (upper <= 0) return `rgb(${stops[0][1].join(",")})`;
  const [rightStop, rightColor] = stops[upper]; const [leftStop, leftColor] = stops[upper - 1];
  const factor = (ratio - leftStop) / (rightStop - leftStop);
  return `rgb(${rightColor.map((color, index) => Math.round(leftColor[index] + (color - leftColor[index]) * factor)).join(",")})`;
}

async function refreshLaunchGate() {
  const state = $("launchGateState"); const target = $("launchGateChecks");
  state.textContent = "正在检查发布门禁…";
  try {
    const report = await get("/api/v1/system/launch-gate");
    target.replaceChildren();
    const table = document.createElement("table"); table.innerHTML = "<thead><tr><th>检查项</th><th>状态</th><th>说明</th></tr></thead>";
    const body = document.createElement("tbody");
    report.checks.forEach((item) => { const row = document.createElement("tr"); const name = document.createElement("td"); name.textContent = gateCheckLabels[item.name] || item.name; const status = document.createElement("td"); const badge = document.createElement("span"); const passed = item.status === "pass" || item.status === "ok" || item.status === "ready"; badge.className = `status ${passed ? "status-ok" : item.status === "warn" ? "status-muted" : "status-error"}`; badge.textContent = passed ? "通过" : item.status === "warn" ? "提示" : "未通过"; status.appendChild(badge); const detail = document.createElement("td"); detail.textContent = item.detail; row.append(name, status, detail); body.appendChild(row); });
    table.appendChild(body); target.appendChild(table);
    state.textContent = `${report.status === "staging-ready" ? "隔离环境已就绪" : "门禁未通过"} · ${report.environment || "未知环境"} · ${report.control_mode || "未知控制模式"}`;
    state.className = `task-progress ${report.status === "staging-ready" ? "status-ok" : "status-error"}`;
  } catch (error) { state.textContent = `门禁检查失败：${error.message}`; state.className = "task-progress status-error"; }
}

async function previewImport() {
  const state = $("importState"); const commit = $("importCommitButton");
  importPreviewId = null; commit.disabled = true; state.textContent = "正在校验导入内容…";
  let rows;
  try { rows = JSON.parse($("importRows").value); } catch { state.textContent = "预览失败：内容必须是 JSON 数组。"; return; }
  try {
    const result = await post("/api/v1/import/preview", { source_name: $("importSourceName").value.trim() || "manual-preview.json", market: $("importMarket").value, rows });
    importPreviewId = result.preview_id; commit.disabled = result.status !== "ready";
    state.textContent = `${result.status === "ready" ? "预览通过" : "预览拒绝"} · ${result.accepted_count}/${result.row_count} 行有效 · ${result.rejected_count} 个错误 · ${result.preview_id.slice(0, 12)}…${result.errors.length ? ` · ${result.errors[0]}` : ""}`;
    state.className = `task-progress ${result.status === "ready" ? "status-ok" : "status-error"}`;
  } catch (error) { state.textContent = `预览失败：${error.message}`; state.className = "task-progress status-error"; }
}

async function commitImport() {
  if (!importPreviewId) return;
  const state = $("importState"); const commit = $("importCommitButton"); commit.disabled = true; state.textContent = "正在写入导入审计记录…";
  try {
    const result = await post("/api/v1/import/commit", { preview_id: importPreviewId, confirm: true });
    state.textContent = `已记录导入审计 ${result.audit_id} · ${result.accepted_count} 行通过校验；当前仍为隔离只读模式，未写入生产数据库。`;
    state.className = "task-progress status-ok";
  } catch (error) { state.textContent = `导入未提交：${error.message}`; state.className = "task-progress status-error"; commit.disabled = false; }
}

function curveScale(values) {
  const dataMin = Math.min(...values); const dataMax = Math.max(...values);
  let lower = Math.max(-1000, Math.floor((dataMin - 50) / 100) * 100);
  let upper = Math.min(3000, Math.ceil((dataMax + 50) / 100) * 100);
  if (upper <= lower) upper = Math.min(3000, lower + 100);
  if (upper <= lower) lower = upper - 100;
  const step = upper - lower > 2000 ? 200 : 100;
  return { min: lower, max: upper, step };
}

function drawCurves(curves, selectedIndex = 0, pointer = null) {
  const canvas = $("curveChart");
  const width = canvas.clientWidth || 700;
  const height = 340;
  const ratio = Math.max(2, window.devicePixelRatio || 1);
  canvas.width = width * ratio; canvas.height = height * ratio;
  const context = canvas.getContext("2d"); context.scale(ratio, ratio);
  context.clearRect(0, 0, width, height);
  if (!curves.length) return;
  const values = curves.flatMap((curve) => curve.prices).filter((value) => Number.isFinite(value));
  if (!values.length) return;
  const scale = curveScale(values); const min = scale.min; const max = scale.max; const span = max - min || 1;
  const pad = { left: 42, right: 14, top: 18, bottom: 30 };
  context.strokeStyle = "#dfe5e2"; context.lineWidth = 1;
  for (let tick = min; tick <= max; tick += scale.step) {
    const y = pad.top + (height - pad.top - pad.bottom) * (max - tick) / span;
    context.beginPath(); context.moveTo(pad.left, y); context.lineTo(width - pad.right, y); context.stroke();
    context.fillStyle = "#5f7068"; context.font = "11px Microsoft YaHei"; context.fillText(tick.toFixed(0), 4, y + 4);
  }
  curves.forEach((curve, curveIndex) => {
    const selected = curveIndex === selectedIndex;
    context.strokeStyle = selected ? "#176b50" : "#9fc5b1";
    context.lineWidth = selected ? 2.4 : 1.2;
    context.beginPath();
    curve.prices.forEach((value, index) => {
      const x = pad.left + (width - pad.left - pad.right) * index / 95;
      const y = pad.top + (height - pad.top - pad.bottom) * (max - Number(value)) / span;
      index ? context.lineTo(x, y) : context.moveTo(x, y);
    });
    context.stroke();
    if (selected) {
      for (let index = 1; index < curve.prices.length; index += 1) {
        const from = Number(curve.prices[index - 1]); const to = Number(curve.prices[index]);
        if (!Number.isFinite(from) || !Number.isFinite(to)) continue;
        const x1 = pad.left + (width - pad.left - pad.right) * (index - 1) / 95;
        const x2 = pad.left + (width - pad.left - pad.right) * index / 95;
        const y1 = pad.top + (height - pad.top - pad.bottom) * (max - from) / span;
        const y2 = pad.top + (height - pad.top - pad.bottom) * (max - to) / span;
        context.strokeStyle = priceColor((from + to) / 2, min, max); context.lineWidth = 2.7;
        context.beginPath(); context.moveTo(x1, y1); context.lineTo(x2, y2); context.stroke();
      }
    }
  });
  if (pointer && pointer.slot >= 0 && pointer.slot < 96) {
    const x = pad.left + (width - pad.left - pad.right) * pointer.slot / 95;
    const value = Number(curves[selectedIndex]?.prices[pointer.slot]);
    if (Number.isFinite(value)) {
      const y = pad.top + (height - pad.top - pad.bottom) * (max - value) / span;
      context.strokeStyle = "rgba(23,107,80,.35)"; context.lineWidth = 1;
      context.setLineDash([4, 4]); context.beginPath(); context.moveTo(x, pad.top); context.lineTo(x, height - pad.bottom); context.stroke(); context.setLineDash([]);
      context.fillStyle = "#fff"; context.strokeStyle = "#176b50"; context.lineWidth = 2;
      context.beginPath(); context.arc(x, y, 4.5, 0, Math.PI * 2); context.fill(); context.stroke();
    }
  }
  context.fillStyle = "#5f7068"; context.font = "11px Microsoft YaHei";
  context.fillText("00:15", pad.left, height - 8); context.fillText("12:00", width / 2 - 18, height - 8); context.fillText("24:00", width - 48, height - 8);
  canvas._curveGeometry = { curves, selectedIndex, width, height, pad, min, max, span };
}

let loadedCurves = [];
let loadedAggregates = null;

function formatCurveTime(slot) {
  const minutes = (slot + 1) * 15; const hour = Math.floor(minutes / 60) % 24; const minute = minutes % 60;
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

function hideCurveHover() {
  curvePointer = null; const hover = $("curveHover"); if (hover) hover.hidden = true;
  if (loadedCurves.length) drawCurves(loadedCurves, activeCurveIndex());
}

function showCurveHover(event) {
  const canvas = $("curveChart"); const geometry = canvas._curveGeometry;
  if (!geometry || !geometry.curves.length) return;
  const rect = canvas.getBoundingClientRect(); const x = event.clientX - rect.left; const y = event.clientY - rect.top;
  if (x < geometry.pad.left || x > geometry.width - geometry.pad.right || y < geometry.pad.top || y > geometry.height - geometry.pad.bottom) { hideCurveHover(); return; }
  const plotWidth = geometry.width - geometry.pad.left - geometry.pad.right;
  const raw = Math.round((x - geometry.pad.left) / plotWidth * 95); const slot = Math.max(0, Math.min(95, raw));
  const selectedIndex = geometry.selectedIndex; const curve = geometry.curves[selectedIndex]; const value = Number(curve?.prices[slot]);
  if (!Number.isFinite(value)) { hideCurveHover(); return; }
  curvePointer = { slot }; drawCurves(geometry.curves, selectedIndex, curvePointer);
  const hover = $("curveHover"); const selectedDay = curve.run_date;
  const nodeLabel = $("curveNode").selectedOptions[0]?.textContent || `节点 ${curve.node_id}`;
  hover.innerHTML = `<strong>${nodeLabel}</strong><br>日期：${selectedDay}　市场：${curve.market}<br>时间：${formatCurveTime(slot)}（第 ${slot + 1}/96 点）<br>电价：<b>${value.toFixed(2)} 元/MWh</b><br>来源：${curve.source_mode || "未标注"}`;
  hover.hidden = false;
  const left = Math.max(8, Math.min(event.clientX - rect.left + 14, rect.width - hover.offsetWidth - 8));
  const top = Math.max(8, Math.min(event.clientY - rect.top - hover.offsetHeight - 10, rect.height - hover.offsetHeight - 8));
  hover.style.left = `${left}px`; hover.style.top = `${top}px`;
}

function activeCurveIndex() {
  const active = document.querySelector("#curveDays .curve-day.active");
  return Number(active?.dataset.index || 0);
}

function updateCurveStats(curves, selectedIndex = 0) {
  const stats = $("curveStats");
  if (!curves.length) { stats.hidden = true; stats.textContent = ""; return; }
  const selected = curves[selectedIndex] || curves[0]; const values = selected.prices;
  const average = values.reduce((sum, value) => sum + value, 0) / values.length;
  stats.hidden = false;
  stats.textContent = `${selected.run_date} · ${values.length} 点 · 均值 ${average.toFixed(2)} · 最低 ${Math.min(...values).toFixed(2)} · 最高 ${Math.max(...values).toFixed(2)} 元/MWh${curves.length > 1 ? ` · 共加载 ${curves.length} 天` : ""}`;
}

function renderCurveAggregates(data) {
  const section = $("curveAggregates"); const body = $("curveAggregateBody");
  body.replaceChildren();
  const rows = [...(data.monthly || []).map((row) => ({...row, period: `${row.period} 月`})),
    ...(data.annual || []).map((row) => ({...row, period: `${row.period} 年`}))];
  if (!rows.length) { section.hidden = true; return; }
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    const values = [row.period, row.valid_days, Number(row.average_price_yuan_per_mwh).toFixed(2),
      Number(row.charge_price_yuan_per_mwh).toFixed(2), Number(row.discharge_price_yuan_per_mwh).toFixed(2),
      Number(row.spread_yuan_per_mwh).toFixed(2), `${Number(row.min_price_yuan_per_mwh).toFixed(2)} / ${Number(row.max_price_yuan_per_mwh).toFixed(2)}`];
    values.forEach((value) => { const td = document.createElement("td"); td.textContent = value; tr.appendChild(td); });
    body.appendChild(tr);
  });
  section.hidden = false;
  $("curveAggregateMeta").textContent = `统计范围 ${data.first_date || "—"} 至 ${data.last_date || "—"} · ${data.valid_days} 个有效日 · ${data.duration_hours} 小时连续窗口 · 来源 ${data.source_mode}`;
}

function exportCurveAggregate() {
  if (!loadedAggregates) return;
  const rows = [
    ["类型", "周期", "有效日", "均价（元/MWh）", "低价窗口", "高价窗口", "价差", "最低", "最高", "重复来源日"],
    ...(loadedAggregates.monthly || []).map((row) => ["月度", row.period, row.valid_days, row.average_price_yuan_per_mwh,
      row.charge_price_yuan_per_mwh, row.discharge_price_yuan_per_mwh, row.spread_yuan_per_mwh,
      row.min_price_yuan_per_mwh, row.max_price_yuan_per_mwh, row.multiple_source_days]),
    ...(loadedAggregates.annual || []).map((row) => ["年度", row.period, row.valid_days, row.average_price_yuan_per_mwh,
      row.charge_price_yuan_per_mwh, row.discharge_price_yuan_per_mwh, row.spread_yuan_per_mwh,
      row.min_price_yuan_per_mwh, row.max_price_yuan_per_mwh, row.multiple_source_days]),
  ];
  const csv = rows.map((row) => row.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(",")).join("\r\n");
  const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = `price-aggregates-${Date.now()}.csv`; link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 0);
}

function exportCurves() {
  if (!loadedCurves.length) return;
  const header = ["日期", ...Array.from({ length: 96 }, (_, index) => `时段${String(index + 1).padStart(2, "0")}`)];
  const rows = loadedCurves.map((curve) => [curve.run_date, ...curve.prices]);
  const csv = [header, ...rows].map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(",")).join("\r\n");
  const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = `price-curves-${Date.now()}.csv`; link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 0);
}

async function loadCurves() {
  const nodeId = $("curveNode").value;
  if (!nodeId) { $("curveState").textContent = "请选择节点"; return; }
  const query = { node_id: nodeId, market: $("curveMarket").value, start_date: $("curveStart").value, end_date: $("curveEnd").value, limit: $("curveLimit").value, duration_hours: $("curveAggregateDuration").value };
  const ticket = ReportUI.begin("curve", query, $("curveNode").selectedOptions[0].textContent);
  $("curveState").textContent = "加载中"; $("curveState").className = "status status-muted";
  try {
    const [curves, aggregates] = await Promise.all([
      get("/api/v1/price/curves", query),
      get("/api/v1/price/aggregates", {...query, duration_hours: $("curveAggregateDuration").value}),
    ]);
    if (!ReportUI.current("curve", ticket)) return;
    loadedCurves = curves; loadedAggregates = aggregates; curvePointer = null; $("curveHover").hidden = true; $("exportCurves").disabled = curves.length === 0; $("exportCurveAggregate").disabled = !(aggregates.monthly?.length || aggregates.annual?.length); $("exportCurveAggregateXlsx").disabled = !(aggregates.monthly?.length || aggregates.annual?.length); $("exportCurvePng").disabled = curves.length === 0; $("exportCurveXlsx").disabled = curves.length === 0; updateCurveStats(curves);
    const dayList = $("curveDays"); dayList.replaceChildren();
    curves.forEach((curve, index) => { const day = document.createElement("button"); day.className = `curve-day${index === 0 ? " active" : ""}`; day.dataset.index = String(index); day.textContent = curve.run_date; day.addEventListener("click", () => { document.querySelectorAll(".curve-day").forEach((item) => item.classList.remove("active")); day.classList.add("active"); curvePointer = null; $("curveHover").hidden = true; drawCurves(curves, index); updateCurveStats(curves, index); $("curveTitle").textContent = `${curve.run_date} · ${$("curveMarket").value}`; }); dayList.appendChild(day); });
    $("curveEmpty").hidden = curves.length > 0; document.querySelector(".curve-card").classList.toggle("curve-empty", !curves.length); $("curveTitle").textContent = curves.length ? `${curves[0].run_date} · ${$("curveMarket").value}` : "当前范围暂无完整曲线"; $("curveState").textContent = curves.length ? `${curves.length} 天` : "暂无数据"; $("curveState").className = `status ${curves.length ? "status-ok" : "status-muted"}`;
    if (!curves.length) dayList.innerHTML = '<div class="empty-state">数据库暂无完整 96 点曲线</div>'; drawCurves(curves); renderCurveAggregates(aggregates);
    ReportUI.complete("curve", ticket, curves.length, `来源模式：${[...new Set(curves.map(c => c.source_mode))].join("、")} · ${curves[0]?.run_date || ""} 至 ${curves.at(-1)?.run_date || ""} · ${curves.length} 个完整日（上限 ${query.limit} 日） · 选中日按价格渐变，其他日期用于对比`);
  } catch (error) { if (!ReportUI.current("curve", ticket)) return; ReportUI.invalidate("curve", "加载失败，重新加载后可导出。"); loadedCurves = []; loadedAggregates = null; $("exportCurves").disabled = true; $("exportCurveAggregate").disabled = true; $("exportCurveAggregateXlsx").disabled = true; $("exportCurvePng").disabled = true; $("exportCurveXlsx").disabled = true; updateCurveStats([]); $("curveAggregates").hidden = true; $("curveState").textContent = "加载失败"; $("curveState").className = "status status-error"; $("curveEmpty").hidden = false; $("curveEmpty").textContent = `读取失败：${error.message}`; }
}

function drawWeather(series) {
  const canvas = $("weatherChart"); const width = canvas.clientWidth || 760; const height = 330; const ratio = Math.max(2, window.devicePixelRatio || 1);
  canvas.width = width * ratio; canvas.height = height * ratio; const context = canvas.getContext("2d"); context.scale(ratio, ratio); context.clearRect(0, 0, width, height);
  if (!series.length) return;
  const ghi = series.map((row) => row.ghi_w_m2).filter((value) => value != null); const pv = series.map((row) => row.pv_predict_power_mw).filter((value) => value != null); const wind = series.map((row) => row.wind_speed_m_s).filter((value) => value != null); const maxGhi = Math.max(1, ...ghi); const maxPv = Math.max(1, ...pv); const maxWind = Math.max(1, ...wind); const pad = {left: 46, right: 20, top: 20, bottom: 30}; const x = (index) => pad.left + (width - pad.left - pad.right) * index / Math.max(1, series.length - 1);
  const line = (key, color, max) => { context.strokeStyle = color; context.lineWidth = 2; context.beginPath(); series.forEach((row, index) => { const value = row[key]; if (value == null) return; const y = pad.top + (height - pad.top - pad.bottom) * (1 - value / max); index ? context.lineTo(x(index), y) : context.moveTo(x(index), y); }); context.stroke(); };
  context.strokeStyle = "#dfe5e2"; context.lineWidth = 1; for (let step = 0; step <= 4; step += 1) { const y = pad.top + (height - pad.top - pad.bottom) * step / 4; context.beginPath(); context.moveTo(pad.left, y); context.lineTo(width - pad.right, y); context.stroke(); }
  line("ghi_w_m2", "#d9a441", maxGhi); line("pv_predict_power_mw", "#f07832", maxPv); line("wind_speed_m_s", "#3c8b72", maxWind); line("wind_predict_power_mw", "#6d55b5", Math.max(1, ...series.map((row) => row.wind_predict_power_mw || 0)));
  context.font = "11px Microsoft YaHei"; context.fillStyle = "#d9a441"; context.fillText("辐照度", pad.left, 13); context.fillStyle = "#f07832"; context.fillText("光伏功率（预计）", pad.left + 58, 13); context.fillStyle = "#3c8b72"; context.fillText("风速", pad.left + 168, 13); context.fillStyle = "#6d55b5"; context.fillText("风电功率（预计）", pad.left + 210, 13);
}

async function loadWeather() {
  const nodeId = $("weatherNode").value; if (!nodeId) { $("weatherEmpty").textContent = "请选择节点"; return; }
  const query = { node_id: nodeId, limit: "744" };
  if ($("weatherStart").value) query.start_time = $("weatherStart").value;
  if ($("weatherEnd").value) query.end_time = $("weatherEnd").value;
  const ticket = ReportUI.begin("weather", query, $("weatherNode").selectedOptions[0].textContent);
  try {
    const rawSeries = await get("/api/v1/weather/series", query);
    if (!ReportUI.current("weather", ticket)) return;
    const series = aggregateWeather(rawSeries, $("weatherGranularity").value);
    const mean = (key) => { const values = series.map((row) => row[key]).filter((value) => value != null); return values.length ? (values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(1) : "—"; };
    $("weatherObservations").textContent = series.length; $("weatherGhi").textContent = mean("ghi_w_m2"); $("weatherWind").textContent = mean("wind_speed_m_s"); $("weatherTemp").textContent = mean("temp_c"); $("weatherSourceDetail").textContent = series.length ? `${series[0].source || "未标注来源"} · ${series[0].is_power_simulated ? "功率估算" : "功率实测"}` : "当前范围暂无气象观测"; $("weatherChartTitle").textContent = series.length ? `${series[0].data_time.slice(0, 10)} 至 ${series[series.length - 1].data_time.slice(0, 10)}` : "当前范围暂无观测"; $("weatherEmpty").hidden = series.length > 0; document.querySelector(".weather-chart-card").classList.toggle("weather-empty", !series.length); if (!series.length) $("weatherEmpty").textContent = "数据库暂无气象观测"; $("exportWeatherPng").disabled = !series.length; $("exportWeatherXlsx").disabled = !series.length; drawWeather(series);
    ReportUI.complete("weather", ticket, series.length, `来源：${[...new Set(rawSeries.map(r => r.source || r.source_mode))].join("、")} · ${rawSeries.length} 条原始观测（上限 744 条） · 图表粒度：${$("weatherGranularity").value} · 各曲线独立缩放，仅用于趋势比较；辐照度 W/m²，风速 m/s，功率 MW（模型预计）`);
  } catch (error) { if (!ReportUI.current("weather", ticket)) return; ReportUI.invalidate("weather", "加载失败，请重试。"); $("weatherEmpty").hidden = false; $("weatherEmpty").textContent = `读取失败：${error.message}`; }
}

async function submitAnalysis() {
  ReportUI.clearRun("analysisView");
  const nodeId = $("node").value; const state = $("analysisState"); const resultBox = $("analysisResult");
  analysisSourceRunId = null; analysisScenarioRunId = null; analysisAnnualRevenueYuan = null; analysisScale = null;
  $("useAnalysisForFinance").disabled = true;
  if ($("analysisScenarioState")) $("analysisScenarioState").textContent = "情景生成后可带入财务测算，原始节点分析结果保持不变。";
  const power = Number($("analysisPower").value); const capacity = Number($("analysisCapacity").value);
  const duration = capacity / power;
  if (!nodeId) { resultBox.hidden = false; state.textContent = "请选择节点"; state.className = "status status-error"; return; }
  if (!Number.isFinite(duration) || duration < 0.25 || duration > 24) { resultBox.hidden = false; state.textContent = "参数无效"; state.className = "status status-error"; $("analysisMessage").textContent = "容量/功率时长须在 0.25 至 24 小时之间"; return; }
  resultBox.hidden = false; $("analysisMonthly").hidden = true; state.textContent = "提交中"; state.className = "status status-muted"; $("analysisMessage").textContent = "正在读取完整历史日并计算价差…"; $("analysisAnnual").textContent = "—"; $("analysisDays").textContent = "—"; analysisSourceRunId = null; analysisScenarioRunId = null; analysisAnnualRevenueYuan = null; $("submitAnalysis").disabled = true;
  try {
    const run = await post("/api/v1/runs", { kind: "price-analysis", parameters: { node_id: Number(nodeId), market: $("market").value, start_date: $("startDate").value, end_date: $("endDate").value, power_mw: power, capacity_mwh: capacity, round_trip_efficiency: Number($("analysisEta").value) / 100 } });
    const finished = await pollAnalysis(run.run_id); const data = finished.result || {};
    analysisSourceRunId = run.run_id; analysisAnnualRevenueYuan = Number(data.annualized_revenue_yuan); analysisScale = { power: data.power_mw, capacity: data.capacity_mwh };
    state.textContent = "计算完成"; state.className = "status status-ok";
    $("analysisMessage").textContent = `连续低/高均价 ${Number(data.charge_price_yuan_per_mwh).toFixed(2)} / ${Number(data.discharge_price_yuan_per_mwh).toFixed(2)} 元/MWh；均价差 ${Number(data.spread_yuan_per_mwh).toFixed(2)}`;
    $("analysisAnnual").textContent = `${(analysisAnnualRevenueYuan / 10000).toLocaleString(undefined, {maximumFractionDigits: 2})} 万元/年（估算）`;
    $("analysisDays").textContent = `${data.baseline_policy === "latest_complete_year" ? "最近完整年度" : "不足完整年度，全部有效日"}：${data.start_date} 至 ${data.end_date}，${data.valid_days} 天；快照 ${data.snapshot_id.slice(0, 12)}`;
    renderAnalysisMonthly(data.monthly);
    ReportUI.run("analysisView", run.run_id, "月度价差", apiBase);
    $("useAnalysisForFinance").disabled = false;
  } catch (error) { state.textContent = "计算失败"; state.className = "status status-error"; $("analysisMessage").textContent = error.message; } finally { $("submitAnalysis").disabled = false; }
}

async function createInvestmentScenario() {
  const state = $("analysisScenarioState");
  if (!analysisSourceRunId || !analysisScale) { state.textContent = "请先完成节点价差分析，再生成投资情景。"; return; }
  const spreadFactor = Number($("analysisSpreadFactor").value) / 100;
  const annualCycles = Number($("analysisAnnualCycles").value);
  const utilization = Number($("analysisUtilization").value) / 100;
  const retentionRate = Number($("analysisRetention").value) / 100;
  const scenarioName = $("analysisScenarioName").value.trim() || "基准情景";
  if (![spreadFactor, annualCycles, utilization, retentionRate].every(Number.isFinite)
      || spreadFactor <= 0 || annualCycles < 0 || utilization < 0 || utilization > 1
      || retentionRate <= 0 || retentionRate > 1) {
    state.textContent = "情景参数无效：请检查系数、循环次数、利用率和保持率。";
    return;
  }
  const button = $("createInvestmentScenario"); button.disabled = true; state.textContent = "情景生成中…";
  try {
    const run = await post("/api/v1/runs", { kind: "investment-scenario", parameters: {
      source_run_id: analysisSourceRunId, scenario_name: scenarioName,
      spread_factor: spreadFactor, annual_cycles: annualCycles,
      utilization, retention_rate: retentionRate,
    } });
    const finished = await pollAnalysis(run.run_id); const data = finished.result || {};
    analysisScenarioRunId = run.run_id; analysisAnnualRevenueYuan = Number(data.annual_revenue_yuan);
    state.textContent = `已生成：${data.scenario_name || scenarioName} · 年收入 ${(analysisAnnualRevenueYuan / 10000).toLocaleString(undefined, {maximumFractionDigits: 2})} 万元 · ${run.run_id}`;
    $("useAnalysisForFinance").disabled = false;
  } catch (error) { analysisScenarioRunId = null; state.textContent = `生成失败：${error.message}`; }
  finally { button.disabled = false; }
}

async function pollAnalysis(runId) {
  for (let attempt = 0; attempt < 300; attempt += 1) { const run = await get(`/api/v1/runs/${runId}`); if (run.status === "succeeded") return run; if (["failed", "cancelled"].includes(run.status)) throw new Error(`${run.message || "价差分析未完成"}${run.error_code ? `（${run.error_code}）` : ""}`); await new Promise((resolve) => setTimeout(resolve, 1000)); }
  throw new Error("价差分析轮询超时，请稍后按 run_id 查询");
}

function renderAnalysisMonthly(rows) {
  const section = $("analysisMonthly"); const body = $("analysisMonthlyBody"); body.replaceChildren();
  if (!rows?.length) { section.hidden = true; return; }
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    [row.month, row.valid_days, Number(row.charge_price_yuan_per_mwh).toFixed(2), Number(row.discharge_price_yuan_per_mwh).toFixed(2), Number(row.spread_yuan_per_mwh).toFixed(2)].forEach((value) => { const cell = document.createElement("td"); cell.textContent = value; tr.appendChild(cell); });
    body.appendChild(tr);
  });
  section.hidden = false;
}

function useAnalysisForFinance() {
  if (!analysisSourceRunId || !analysisScale || !Number.isFinite(analysisAnnualRevenueYuan)) return;
  const value = analysisAnnualRevenueYuan;
  if (Number.isFinite(value)) $("annualRevenue").value = Math.round(value);
  $("powerMw").value = analysisScale.power; $("capacityMwh").value = analysisScale.capacity;
  financialSourceRunId = analysisScenarioRunId || analysisSourceRunId; updateDurationHint();
  activateView("taskView"); $("taskMessage").textContent = `已带入${analysisScenarioRunId ? "投资情景" : "节点价差结果"}（run_id: ${financialSourceRunId}）`; $("taskState").textContent = "待提交"; $("taskState").className = "status status-muted";
}

function invalidateAnalysisSelection() {
  analysisSourceRunId = null; analysisScenarioRunId = null; analysisAnnualRevenueYuan = null; analysisScale = null; $("useAnalysisForFinance").disabled = true; $("analysisResult").hidden = true; $("analysisMonthly").hidden = true; if ($("analysisScenarioState")) $("analysisScenarioState").textContent = "情景生成后可带入财务测算，原始节点分析结果保持不变。";
}

async function submitDispatch() {
  ReportUI.clearRun("dispatchView");
  const nodeId = $("dispatchNode").value; const state = $("dispatchState"); const message = $("dispatchMessage");
  if (!nodeId) { message.textContent = "请选择节点"; return; }
  const power = Number($("dispatchPower").value); const capacity = Number($("dispatchCapacity").value);
  if (!Number.isFinite(power) || !Number.isFinite(capacity) || power <= 0 || capacity <= 0 || capacity / power < 0.25 || capacity / power > 24) { state.textContent = "参数无效"; state.className = "status status-error"; message.textContent = "容量/功率时长须在 0.25 至 24 小时之间"; return; }
  state.textContent = "提交中"; state.className = "status status-muted"; $("dispatchResult").hidden = true; lpReconcileRunId = null; $("lpReconcileButton").hidden = true; $("lpReconcileState").hidden = true;
  const parameters = { node_id: Number(nodeId), market: $("dispatchMarket").value, start_date: $("dispatchStart").value, end_date: $("dispatchEnd").value, power_mw: power, capacity_mwh: capacity, eta_charge: Number($("dispatchEta").value) / 100, eta_discharge: Number($("dispatchEta").value) / 100, max_daily_cycles: Number($("dispatchCycles").value), hurdle_yuan_per_mwh: Number($("dispatchHurdle").value) };
  const kind = $("dispatchMode").value || "strict-dispatch";
  if (kind === "lp-analysis") Object.assign(parameters, { include_comparison: true, include_sensitivity: false });
  try { const run = await post("/api/v1/runs", { kind, parameters }); lpReconcileRunId = kind === "lp-analysis" ? run.run_id : null; $("dispatchRunId").textContent = run.run_id; const finished = await pollDispatch(run.run_id); renderDispatchResult(finished.result); ReportUI.run("dispatchView", run.run_id, kind === "lp-analysis" ? "LP详细回放" : "逐日调度", apiBase); } catch (error) { state.textContent = "回放失败"; state.className = "status status-error"; message.textContent = error.message; }
}

async function pollDispatch(runId) {
  const state = $("dispatchState"); const message = $("dispatchMessage");
  for (let attempt = 0; attempt < 300; attempt += 1) { const run = await get(`/api/v1/runs/${runId}`); state.textContent = `${run.status} ${run.progress}%`; state.className = run.status === "succeeded" ? "status status-ok" : "status status-muted"; message.textContent = run.message || "任务执行中"; if (run.status === "succeeded") return run; if (["failed", "cancelled"].includes(run.status)) throw new Error(`${run.message || "任务未完成"}${run.error_code ? `（${run.error_code}）` : ""}`); await new Promise((resolve) => setTimeout(resolve, 1000)); }
  throw new Error("回放轮询超时，请稍后按 run_id 查询");
}

function renderDispatchResult(result) {
  if (!result) return; const money = (value) => value == null ? "—" : `${(Number(value) / 10000).toLocaleString(undefined, {maximumFractionDigits: 2})} 万元`; $("dispatchValidDays").textContent = result.valid_days ?? "—"; $("dispatchTotalRevenue").textContent = money(result.total_net_revenue_yuan); $("dispatchAnnualRevenue").textContent = money(result.annualized_net_revenue_yuan); $("dispatchSnapshot").textContent = result.snapshot_id ? `${result.snapshot_id.slice(0, 8)}…` : "—";
  const body = $("dispatchDays"); body.replaceChildren(); (result.days || []).forEach((day) => { const row = document.createElement("tr"); [day.run_date, money(day.net_revenue_yuan), Number(day.charge_energy_mwh).toFixed(1), Number(day.discharge_energy_mwh).toFixed(1), Number(day.cycles).toFixed(2), day.shutdown ? "低于门槛" : "已执行"].forEach((value) => { const cell = document.createElement("td"); cell.textContent = value; row.appendChild(cell); }); body.appendChild(row); });
  const detail = $("lpResultDetails"); const months = $("lpMonths"); months.replaceChildren(); if (result.monthly?.length) { result.monthly.forEach((item) => { const row = document.createElement("tr"); [item.month, item.days, Number(item.revenue_total_yuan).toFixed(2), Number(item.revenue_avg_yuan).toFixed(2), Number(item.discharge_energy_total_mwh).toFixed(1), Number(item.cycles_avg).toFixed(3)].forEach((value) => { const cell = document.createElement("td"); cell.textContent = value; row.appendChild(cell); }); months.appendChild(row); }); detail.hidden = false; } else detail.hidden = true;
  $("dispatchResult").hidden = false;
  const reconcileButton = $("lpReconcileButton");
  if (reconcileButton) reconcileButton.hidden = !lpReconcileRunId;
}

async function reconcileLpRun() {
  if (!lpReconcileRunId) return;
  const button = $("lpReconcileButton"); const state = $("lpReconcileState");
  button.disabled = true; state.hidden = false; state.textContent = "正在核对逐日轨迹、现金流和月/年汇总…";
  try {
    const report = await get(`/api/v1/runs/${lpReconcileRunId}/reconciliation`);
    const failed = (report.checks || []).filter((item) => item.status === "failed").length;
    state.textContent = `${report.status === "passed" ? "对账通过" : "发现差异"} · ${report.checks.length} 项检查 · 失败 ${failed} 项 · 算法 ${report.algorithm_version}`;
    state.className = `curve-hint ${failed ? "status-error" : "status-ok"}`;
  } catch (error) { state.textContent = `对账失败：${error.message}`; state.className = "curve-hint status-error"; }
  finally { button.disabled = false; }
}

function aggregateWeather(series, granularity) {
  if (granularity === "小时" || !series.length) return series;
  const buckets = new Map();
  series.forEach((row) => {
    const date = row.data_time.slice(0, 10);
    const key = granularity === "周" ? `${date.slice(0, 8)}W${Math.floor((Number(date.slice(8, 10)) - 1) / 7) + 1}` : date;
    const bucket = buckets.get(key) || { ...row, _count: 0, data_time: `${date}T00:00:00` };
    if (!buckets.has(key)) ["ghi_w_m2", "wind_speed_m_s", "temp_c", "pv_predict_power_mw", "wind_predict_power_mw"].forEach((field) => { bucket[field] = 0; });
    ["ghi_w_m2", "wind_speed_m_s", "temp_c", "pv_predict_power_mw", "wind_predict_power_mw"].forEach((field) => { if (row[field] != null) bucket[field] = (bucket[field] || 0) + row[field]; });
    bucket._count += 1; buckets.set(key, bucket);
  });
  return [...buckets.values()].map((row) => { const result = { ...row }; ["ghi_w_m2", "wind_speed_m_s", "temp_c", "pv_predict_power_mw", "wind_predict_power_mw"].forEach((field) => { if (result[field] != null) result[field] = result[field] / result._count; }); delete result._count; return result; });
}

function setSignal(id, value, fallback = "") {
  $(id).textContent = value == null ? "暂不可用" : value;
  if (fallback) $(id).nextElementSibling.textContent = fallback;
}

async function refreshOperationsSummary() {
  try {
    const summary = await get("/api/v1/operations/summary");
    const queued = summary.task_counts.by_status.queued || 0;
    setSignal("overviewQueued", queued, `共 ${summary.task_counts.total} 个任务`);
    setSignal("overviewPendingTelemetry", summary.telemetry.pending_points, `共 ${summary.telemetry.total_points} 个数据点`);
    setSignal("overviewUnackAlerts", summary.alerts.unacknowledged, `共 ${summary.alerts.total} 条告警`);
  } catch (error) {
    setSignal("overviewQueued", null, "运营摘要暂不可用");
    setSignal("overviewPendingTelemetry", null, "运营摘要暂不可用");
    setSignal("overviewUnackAlerts", null, "运营摘要暂不可用");
    throw error;
  }
}

async function syncDateRange() {
  const nodeId = $("node").value;
  if (!nodeId) return;
  const range = await get("/api/v1/price/range", { node_id: nodeId, market: $("market").value });
  if (range.first_date) $("startDate").value = range.first_date;
  if (range.last_date) $("endDate").value = range.last_date;
}

async function refresh() {
  try {
    const nodeId = $("node").value;
    if (!nodeId) throw new Error("请选择节点");
    const price = await get("/api/v1/price/summary", { node_id: nodeId, market: $("market").value, start_date: $("startDate").value, end_date: $("endDate").value });
    const quality = await get("/api/v1/quality/summary", { node_id: nodeId, market: $("market").value, start_date: $("startDate").value, end_date: $("endDate").value });
    const weather = await get("/api/v1/weather/summary", { node_id: nodeId });
    $("validDays").textContent = price.valid_days;
    $("dataPoints").textContent = price.data_points.toLocaleString();
    $("weatherRows").textContent = weather.observations;
    $("coverage").textContent = `${(quality.coverage_ratio * 100).toFixed(1)}%`;
    $("qualityDetail").textContent = quality.total_records ? `${quality.complete_records}/${quality.total_records} 条完整记录` : "暂无记录";
    $("priceSource").textContent = price.sources.length ? price.sources.map(displaySource).join("、") : "演示/暂无来源文件";
    $("priceRange").textContent = price.first_date ? `${price.first_date} 至 ${price.last_date}` : "所选范围暂无有效日";
    $("weatherSource").textContent = weather.source ? displaySource(weather.source) : "暂无气象观测";
    $("overviewValidDays").textContent = price.valid_days;
    $("overviewDataPoints").textContent = price.data_points.toLocaleString();
    $("overviewCoverage").textContent = `${(quality.coverage_ratio * 100).toFixed(1)}%`;
    $("overviewRange").textContent = price.first_date ? `${price.first_date} 至 ${price.last_date}` : "所选范围暂无有效日";
    await refreshOperationsSummary();
    $("notice").textContent = "摘要按去重后的有效日期统计；完整率按原始记录统计。年度财务基准另按完整年度规则计算。";
  } catch (error) {
    $("notice").textContent = `读取失败：${error.message}`;
    setStatus("API 请求失败", "error");
  }
}

async function submitFinancial() {
  const state = $("taskState");
  const message = $("taskMessage");
  const download = $("downloadReport");
  const templateDownload = $("downloadTemplateReport");
  $("financeResult").hidden = true;
  financialRunId = null; $("financialReconcileButton").hidden = true; $("financialReconcileState").hidden = true; $("financialTemplateAuditButton").hidden = true; $("financialTemplateAuditState").hidden = true;
  download.hidden = true;
  templateDownload.hidden = true;
  const power = Number($("powerMw").value);
  const capacity = Number($("capacityMwh").value);
  const duration = capacity / power;
  if (!Number.isFinite(duration) || duration < 0.25 || duration > 24) {
    state.textContent = "参数无效";
    state.className = "status status-error";
    message.textContent = "容量/功率时长须在 0.25 至 24 小时之间。2 小时、4 小时仅是常见配置，不锁死具体规模。";
    return;
  }
  state.textContent = "提交中";
  state.className = "status status-muted";
  try {
    const parameters = collectFinancialParameters();
    const run = await post("/api/v1/runs", { kind: "financial", parameters });
    financialRunId = run.run_id;
    message.textContent = `任务 ${run.run_id} 已进入队列`;
    const finished = await pollRun(run.run_id);
    renderFinancialResult(finished.result);
  } catch (error) {
    state.textContent = "提交失败";
    state.className = "status status-error";
    message.textContent = error.message;
  }
}

async function loadOperationsReport() {
  const state = $("operationsReportState"); const body = $("operationsReportBody");
  const query = { market: $("operationsReportMarket").value,
    start_date: $("operationsReportStart").value, end_date: $("operationsReportEnd").value };
  const ticket = ReportUI.begin("operationsReport", query, "运营汇总");
  state.textContent = "正在汇总节点数据…"; body.replaceChildren();
  try {
    const report = await get("/api/v1/operations/report", query);
    if (!ReportUI.current("operationsReport", ticket)) return;
    if (!report.provinces.length) {
      body.innerHTML = '<tr><td colspan="5" class="empty-table-cell">当前条件没有可汇总的有效节点或日期</td></tr>';
    }
    report.provinces.forEach((item) => {
      const row = document.createElement("tr");
      [item.province, item.node_count, item.valid_nodes, item.valid_days, item.data_points.toLocaleString()].forEach((value) => {
        const cell = document.createElement("td"); cell.textContent = value; row.appendChild(cell);
      }); body.appendChild(row);
    });
    state.textContent = `${report.market} · ${report.start_date} 至 ${report.end_date} · ${report.valid_nodes}/${report.node_count} 个节点有效 · ${report.total_valid_days} 个有效日 · 来源 ${displaySource(report.source_mode)}`;
    state.className = "task-progress status-ok";
    ReportUI.complete("operationsReport", ticket, report.node_count, report.source_mode);
  } catch (error) {
    if (!ReportUI.current("operationsReport", ticket)) return;
    ReportUI.invalidate("operationsReport", `运营报告失败：${error.message}`);
    state.textContent = `运营报告失败：${error.message}`; state.className = "task-progress status-error";
    body.innerHTML = '<tr><td colspan="5">请检查日期范围和 API</td></tr>';
  }
}

function revealFinancialField(id) {
  const label = document.getElementById(id)?.closest("label");
  const group = label?.querySelector("[id]") ? Object.entries(FINANCE_GROUP_FIELDS).find(([, fields]) => fields.has(id))?.[0] : null;
  if (group && $("financialParameterGroup")) {
    $("financialParameterGroup").value = group;
    syncFinancialParameterGroup();
  }
}

function validateFinancialInputs() {
  const numeric = ["powerMw", "capacityMwh", "annualRevenue", "capex", "operationYears", "singleSideEfficiency", "dod", "annualCycles", "auxiliaryEquivalentCycles"];
  if (numeric.some((id) => !Number.isFinite(Number($(id).value)))) throw new Error("财务参数中存在无法识别的数字，请检查输入。");
  if (Number($("powerMw").value) <= 0 || Number($("capacityMwh").value) <= 0) throw new Error("功率和容量必须大于 0。");
  if (Number($("annualRevenue").value) < 0 || Number($("capex").value) <= 0 || Number($("operationYears").value) < 1) throw new Error("收入、单位投资和运营年限参数无效。");
}

function collectFinancialParameters() {
  validateFinancialInputs();
  const percent = (id) => Number($(id).value) / 100;
  const optionalNumber = (id) => $(id).value === "" ? null : Number($(id).value);
  const phaseText = $("revenuePhases").value.trim();
  let revenuePhases = {};
  if (phaseText) {
    try { revenuePhases = JSON.parse(phaseText); } catch { throw new Error("分阶段收益规则不是有效 JSON"); }
    if (!revenuePhases || Array.isArray(revenuePhases) || typeof revenuePhases !== "object") {
      throw new Error("分阶段收益规则必须是 JSON 对象");
    }
  }
  const power = Number($("powerMw").value); const capacity = Number($("capacityMwh").value);
  const efficiency = percent("singleSideEfficiency"); const dod = percent("dod");
  const cycles = Number($("annualCycles").value);
  const component = (modeId, annualId, calculated) => {
    const mode = $(modeId).value;
    return mode === "1" ? calculated : mode === "2" ? Number($(annualId).value) : 0;
  };
  let lease = component("capacityLeaseEnabled", "capacityLease", power * 1000 * Number($("capacityLeasePricePerKw").value) * Number($("capacityLeaseUtilization").value));
  const capacityFee = component("capacityFeeEnabled", "capacityFee", power * Number($("capacityFeePerMw").value) * Number($("capacityFeeSupplyCoeff").value) * Number($("capacityFeeDodCoeff").value) * 10000);
  const dischargeEnergy = capacity * dod * efficiency * cycles;
  let subsidy = component("subsidyEnabled", "subsidy", dischargeEnergy * 1000 * Number($("subsidyPerKwh").value));
  const primary = component("primaryFrequencyEnabled", "primaryFrequency", Number($("primaryFrequencyMileage").value) * Number($("primaryFrequencyPrice").value) * Number($("primaryFrequencyK").value));
  const secondary = component("secondaryFrequencyEnabled", "secondaryFrequency", Number($("secondaryFrequencyMileage").value) * Number($("secondaryFrequencyPrice").value) * Number($("secondaryFrequencyK").value));
  const legacyCapacity = Number($("capacityIncomeWan").value) * 10000;
  const legacyAuxiliary = Number($("auxiliaryIncomeWan").value) * 10000;
  if (lease === 0 && capacityFee === 0) lease = legacyCapacity;
  if (subsidy === 0 && primary === 0 && secondary === 0) subsidy = legacyAuxiliary;
  const replaceEnabled = Number($("replaceBatteryEnabled").value) > 0;
  const replaceCost = replaceEnabled
    ? (Number($("replaceCapex").value) || capacity * 1000000 * Number($("replaceUnitPriceYuanWh").value))
    : 0;
  if (replaceEnabled && (!optionalNumber("replaceYear") || Number($("replaceYear").value) > Number($("operationYears").value))) {
    revealFinancialField("replaceYear");
    throw new Error("启用换电池时，请填写运营期内的更换年份；不更换请选择关闭。");
  }
  return {
    power_mw: power, capacity_mwh: capacity, annual_revenue_yuan: financialSourceRunId ? null : Number($("annualRevenue").value),
    capacity_lease_yuan: lease, capacity_fee_yuan: capacityFee, subsidy_yuan: subsidy, revenue_phases: revenuePhases,
    primary_frequency_yuan: primary, secondary_frequency_yuan: secondary, capex_yuan_per_wh: Number($("capex").value), source_run_id: financialSourceRunId || undefined,
    auxiliary_annual_cycles: Number($("auxiliaryEquivalentCycles").value),
    operation_years: Number($("operationYears").value), single_side_efficiency: efficiency, dod, annual_cycles: cycles, eol_method: $("eolMethod").value, calendar_eol_decline: percent("calendarEolDecline"), cycle_life_cycles: Number($("cycleLifeCycles").value), om_rate: percent("omRate"), om_growth: percent("omGrowth"), land_rent_yuan: Number($("landRent").value), insurance_rate: percent("insuranceRate"), fixed_operation_cost_yuan: Number($("fixedOperationCost").value), revenue_share_threshold_yuan: Number($("revenueShareThreshold").value), revenue_share_rate: percent("revenueShareRate"), other_operating_cost_yuan: Number($("otherOperatingCost").value), vat_rate: percent("vatRate"), vat_surcharge_rate: percent("vatSurchargeRate"), stamp_tax_rate: percent("stampTaxRate"), input_vat_rate_equipment: percent("inputVatRateEquipment"), input_vat_rate_other: percent("inputVatRateOther"), equipment_investment_share: percent("equipmentInvestmentShare"), input_vat_credit_ratio: percent("inputVatCreditRatio"), first_year_eol: percent("firstEol"), final_eol: percent("finalEol"), residual_rate: percent("residualRate"), income_tax_rate: percent("incomeTaxRate"), discount_rate: percent("discountRate"), loan_ratio: percent("loanRatio"), loan_years: Number($("loanYears").value), loan_rate: percent("loanRate"), construction_years: Number($("constructionYears").value), construction_loan_rate: percent("constructionLoanRate"), replace_year: replaceEnabled ? optionalNumber("replaceYear") : null, replace_capex_yuan: replaceCost,
  };
}

const FINANCE_GROUP_FIELDS = {
  storage: new Set(["capex", "operationYears", "singleSideEfficiency", "dod", "annualCycles", "eolMethod", "calendarEolDecline", "cycleLifeCycles", "firstEol", "finalEol", "residualRate", "auxiliaryEquivalentCycles"]),
  operation: new Set(["omRate", "omGrowth", "insuranceRate", "fixedOperationCost", "revenueShareThreshold", "revenueShareRate", "otherOperatingCost", "landRent", "replaceYear", "replaceCapex", "replaceBatteryEnabled", "replaceUnitPriceYuanWh"]),
  finance: new Set(["discountRate", "loanRatio", "loanYears", "loanRate", "constructionYears", "constructionLoanRate", "vatRate", "vatSurchargeRate", "stampTaxRate", "inputVatRateEquipment", "inputVatRateOther", "equipmentInvestmentShare", "inputVatCreditRatio", "incomeTaxRate"]),
  capacity: new Set(["capacityLease", "capacityFee", "capacityLeaseEnabled", "capacityLeasePricePerKw", "capacityLeaseUtilization", "capacityFeeEnabled", "capacityFeePerMw", "capacityFeeSupplyCoeff", "capacityFeeDodCoeff", "capacityIncomeWan", "revenuePhases"]),
  service: new Set(["subsidy", "primaryFrequency", "secondaryFrequency", "subsidyEnabled", "subsidyPerKwh", "primaryFrequencyEnabled", "primaryFrequencyMileage", "primaryFrequencyPrice", "primaryFrequencyK", "secondaryFrequencyEnabled", "secondaryFrequencyMileage", "secondaryFrequencyPrice", "secondaryFrequencyK", "auxiliaryIncomeWan"]),
};

function syncFinancialParameterGroup() {
  const selector = $("financialParameterGroup"); if (!selector) return;
  const allowed = FINANCE_GROUP_FIELDS[selector.value] || FINANCE_GROUP_FIELDS.storage;
  const fields = [...document.querySelectorAll(".advanced-grid > label")];
  fields.forEach((label) => {
    const control = label.querySelector("[id]"); label.hidden = !control || !allowed.has(control.id);
  });
  const summary = $("financialGroupSummary");
  if (summary) summary.textContent = "当前组显示 " + fields.filter((label) => !label.hidden).length + " 项 · 共 " + fields.length + " 项参数";
}

async function submitSensitivity() {
  ReportUI.clearRun("taskView");
  const state = $("sensitivityState"); const message = $("sensitivityMessage"); const resultBox = $("sensitivityResult");
  const down = Number($("sensitivityDown").value) / 100; const up = Number($("sensitivityUp").value) / 100; const step = Number($("sensitivityStep").value) / 100;
  if (!Number.isFinite(down) || !Number.isFinite(up) || !Number.isFinite(step) || down >= up || step <= 0 || Math.ceil((up - down) / step) + 1 > 9) { state.textContent = "参数无效"; state.className = "status status-error"; message.textContent = "请检查上下限和步长，情景点数须为 3 至 9 个"; return; }
  const changeRates = []; for (let value = down; value <= up + 1e-9; value += step) changeRates.push(Number(value.toFixed(6)));
  if (changeRates.length < 3) { state.textContent = "参数无效"; state.className = "status status-error"; message.textContent = "至少需要 3 个情景点"; return; }
  state.textContent = "提交中"; state.className = "status status-muted"; message.textContent = "正在生成敏感性情景…"; resultBox.hidden = true; $("submitSensitivity").disabled = true;
  try {
    const run = await post("/api/v1/runs", { kind: "sensitivity", parameters: { base: collectFinancialParameters(), variable: $("sensitivityVariable").value, change_rates: changeRates } });
    $("sensitivityRunId").textContent = run.run_id; const finished = await pollSensitivity(run.run_id); renderSensitivityResult(finished.result); ReportUI.run("taskView", run.run_id, "敏感性分析", apiBase); state.textContent = "计算完成"; state.className = "status status-ok"; message.textContent = "情景结果已绑定当前财务参数。";
  } catch (error) { state.textContent = "计算失败"; state.className = "status status-error"; message.textContent = error.message; } finally { $("submitSensitivity").disabled = false; }
}

async function pollSensitivity(runId) {
  for (let attempt = 0; attempt < 300; attempt += 1) { const run = await get(`/api/v1/runs/${runId}`); if (run.status === "succeeded") return run; if (["failed", "cancelled"].includes(run.status)) throw new Error(`${run.message || "敏感性分析未完成"}${run.error_code ? `（${run.error_code}）` : ""}`); await new Promise((resolve) => setTimeout(resolve, 1000)); }
  throw new Error("敏感性分析轮询超时，请稍后按 run_id 查询");
}

function renderSensitivityResult(result) {
  const body = $("sensitivityBody"); body.replaceChildren();
  (result?.points || []).forEach((point) => { const tr = document.createElement("tr"); const values = [`${(point.change_rate * 100).toFixed(1)}%`, point.full_irr == null ? "—" : `${(point.full_irr * 100).toFixed(2)}%`, `${(Number(point.full_npv_yuan) / 10000).toLocaleString(undefined, {maximumFractionDigits: 2})}`, point.payback_year == null ? "—" : `${Number(point.payback_year).toFixed(2)} 年`, `${(Number(point.first_year_net_profit_yuan) / 10000).toLocaleString(undefined, {maximumFractionDigits: 2})}`]; values.forEach((value) => { const cell = document.createElement("td"); cell.textContent = value; tr.appendChild(cell); }); body.appendChild(tr); });
  $("sensitivityResult").hidden = !result?.points?.length;
}

function renderFinancialResult(result) {
  if (!result) return;
  const money = (value) => value == null ? "—" : `${(Number(value) / 10000).toLocaleString(undefined, {maximumFractionDigits: 2})} 万元`;
  const rate = (value) => value == null ? "—" : `${(Number(value) * 100).toFixed(2)}%`;
  $("resultInvestment").textContent = money(result.total_investment_yuan);
  $("resultIrr").textContent = rate(result.full_irr);
  $("resultNpv").textContent = money(result.full_npv_yuan);
  $("resultPayback").textContent = result.payback_year == null ? "—" : `${Number(result.payback_year).toFixed(2)} 年`;
  $("financeResult").hidden = false;
  if (financialRunId) { $("financialReconcileButton").hidden = false; $("financialTemplateAuditButton").hidden = false; }
}

async function reconcileFinancialRun() {
  if (!financialRunId) return;
  const button = $("financialReconcileButton"); const state = $("financialReconcileState");
  button.disabled = true; state.hidden = false; state.textContent = "正在核对现金流、NPV、IRR和年度明细…";
  try {
    const report = await get(`/api/v1/runs/${financialRunId}/financial-reconciliation`);
    const failed = (report.checks || []).filter((item) => item.status === "failed").length;
    state.textContent = `${report.status === "passed" ? "财务复核通过" : "发现财务差异"} · ${report.checks.length} 项检查 · 失败 ${failed} 项 · ${report.model_version}`;
    state.className = `curve-hint ${failed ? "status-error" : "status-ok"}`;
  } catch (error) { state.textContent = `复核失败：${error.message}`; state.className = "curve-hint status-error"; }
  finally { button.disabled = false; }
}

async function reconcileFinancialTemplate() {
  if (!financialRunId) return;
  const button = $("financialTemplateAuditButton"); const state = $("financialTemplateAuditState");
  button.disabled = true; state.hidden = false; state.textContent = "正在生成临时 1.6.6 模板并核对关键单元格…";
  try {
    const report = await get(`/api/v1/runs/${financialRunId}/financial-template-reconciliation`);
    const counts = report.counts || {}; const difference = (counts.DIFFERENCE || 0) + (counts.ERROR || 0);
    const pending = counts.PENDING || 0;
    state.textContent = `${report.status === "CACHED_VALUES_MATCH" ? "关键单元格缓存一致" : report.status === "PENDING_RECALCULATION" ? "等待 Excel/WPS 重算" : "发现模板差异"} · 匹配 ${counts.MATCH || 0} · 差异 ${difference} · 待重算 ${pending}`;
    state.className = `curve-hint ${difference ? "status-error" : pending ? "status-muted" : "status-ok"}`;
  } catch (error) { state.textContent = `模板复核失败：${error.message}`; state.className = "curve-hint status-error"; }
  finally { button.disabled = false; }
}

function updateDurationHint() {
  const power = Number($("powerMw").value);
  const capacity = Number($("capacityMwh").value);
  const duration = capacity / power;
  const hint = $("durationHint");
  if (!Number.isFinite(duration) || duration <= 0) {
    hint.textContent = "请输入有效功率和容量";
    hint.className = "input-hint status-error";
    return;
  }
  const standard = Math.abs(duration - 2) < 0.01 || Math.abs(duration - 4) < 0.01;
  hint.textContent = "时长：" + duration.toFixed(2) + " 小时 · " + (standard ? "标准 " + duration.toFixed(0) + " 小时制" : "请核对功率/容量比例");
  hint.className = "input-hint " + (standard ? "status-ok" : "status-muted");
}

async function pollRun(runId) {
  const state = $("taskState");
  const message = $("taskMessage");
  const download = $("downloadReport");
  for (let attempt = 0; attempt < 300; attempt += 1) {
    const run = await get(`/api/v1/runs/${runId}`);
    state.textContent = `${run.status} ${run.progress}%`;
    state.className = run.status === "succeeded" ? "status status-ok" : "status status-muted";
    message.textContent = run.message || "任务执行中";
    if (run.status === "succeeded") {
      download.href = `${apiBase}/api/v1/runs/${runId}/export`;
      download.hidden = false;
      if (run.kind === "financial" && financialTemplateAvailable) {
        const templateDownload = $("downloadTemplateReport");
        templateDownload.href = `${apiBase}/api/v1/runs/${runId}/export?format=xlsm`;
        templateDownload.hidden = false;
      }
      return run;
    }
    if (["failed", "cancelled"].includes(run.status)) throw new Error(run.message || "任务未完成");
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("任务轮询超时，请稍后按 run_id 查询");
}

$("province").addEventListener("change", () => { invalidateAnalysisSelection(); loadNodes().catch((error) => { $("notice").textContent = error.message; setStatus("API 请求失败", "error"); }); });
$("node").addEventListener("change", () => { invalidateAnalysisSelection(); syncDateRange().catch((error) => { $("notice").textContent = error.message; setStatus("API 请求失败", "error"); }); });
$("market").addEventListener("change", () => { invalidateAnalysisSelection(); syncDateRange().catch((error) => { $("notice").textContent = error.message; setStatus("API 请求失败", "error"); }); });
$("curveNode").addEventListener("change", () => syncCurveDateRange().catch(() => {}));
$("curveMarket").addEventListener("change", () => syncCurveDateRange().catch(() => {}));
$("curveChart").addEventListener("mousemove", showCurveHover);
$("curveChart").addEventListener("mouseleave", hideCurveHover);
$("loadCurves").addEventListener("click", loadCurves);
$("exportCurveAggregate").addEventListener("click", exportCurveAggregate);
$("exportCurveAggregateXlsx").addEventListener("click", (event) => {
  const params = ReportUI.loadedQuery("curve");
  if (!params) return;
  ReportUI.download(`${apiBase}/api/v1/price/aggregates/export?${new URLSearchParams(params)}`,
    `price-aggregates-${params.node_id}-${params.start_date}-${params.end_date}.xlsx`, event.currentTarget, "curve");
});
$("exportCurves").addEventListener("click", exportCurves);
$("exportCurvePng").addEventListener("click", () => ReportUI.png("curve", "curveChart", $("curveTitle").textContent));
$("exportCurveXlsx").addEventListener("click", (event) => ReportUI.exportQuery("curve", event.currentTarget, apiBase));
$("exportWeatherPng").addEventListener("click", () => ReportUI.png("weather", "weatherChart", $("weatherChartTitle").textContent));
$("exportWeatherXlsx").addEventListener("click", (event) => ReportUI.exportQuery("weather", event.currentTarget, apiBase));
$("loadWeather").addEventListener("click", loadWeather);
$("submitAnalysis").addEventListener("click", submitAnalysis);
if ($("createInvestmentScenario")) $("createInvestmentScenario").addEventListener("click", createInvestmentScenario);
$("useAnalysisForFinance").addEventListener("click", useAnalysisForFinance);
$("submitDispatch").addEventListener("click", submitDispatch);
if ($("lpReconcileButton")) $("lpReconcileButton").addEventListener("click", reconcileLpRun);
$("refresh").addEventListener("click", refresh);
$("submitFinancial").addEventListener("click", submitFinancial);
if ($("financialReconcileButton")) $("financialReconcileButton").addEventListener("click", reconcileFinancialRun);
if ($("financialTemplateAuditButton")) $("financialTemplateAuditButton").addEventListener("click", reconcileFinancialTemplate);
$("submitSensitivity").addEventListener("click", submitSensitivity);
$("loadPortfolio").addEventListener("click", loadPortfolio);
$("portfolioForm").addEventListener("submit", submitPortfolio);
$("portfolioForm").addEventListener("input", invalidatePortfolio);
$("portfolioObjective").addEventListener("change", syncPortfolioObjective);
$("addPortfolioProject").addEventListener("click", () => { addPortfolioProject(); invalidatePortfolio(); });
$("generatePortfolioCandidates").addEventListener("click", generatePortfolioCandidates);
$("exportPortfolioCandidates").addEventListener("click", exportPortfolioCandidates);
$("exportPortfolioCandidatesXlsx").addEventListener("click", (event) => {
  const params = ReportUI.loadedQuery("portfolioCandidates");
  if (!params?.snapshot_id) return;
  ReportUI.download(`${apiBase}/api/v1/portfolio/candidates/${params.snapshot_id}/export`,
    `portfolio-snapshot-${params.snapshot_id.slice(0, 12)}.xlsx`, event.currentTarget, "portfolioCandidates");
});
$("optimizePortfolioSnapshot").addEventListener("click", optimizePortfolioSnapshot);
$("resumePortfolio").addEventListener("click", resumePortfolio);
try { portfolioRunId = localStorage.getItem("banboosPortfolioRun"); $("resumePortfolio").hidden = !portfolioRunId; } catch { /* Optional task recovery. */ }
addPortfolioProject();
$("refreshSystem").addEventListener("click", refreshSystem);
if ($("refreshLaunchGate")) $("refreshLaunchGate").addEventListener("click", refreshLaunchGate);
if ($("loadOperationsReport")) $("loadOperationsReport").addEventListener("click", loadOperationsReport);
if ($("exportOperationsReport")) $("exportOperationsReport").addEventListener("click", (event) => {
  const params = ReportUI.loadedQuery("operationsReport");
  if (!params) return;
  ReportUI.download(`${apiBase}/api/v1/operations/report/export?${new URLSearchParams(params)}`,
    `operations-${params.start_date}-${params.end_date}.xlsx`, event.currentTarget, "operationsReport");
});
[
  "portfolioMarket", "portfolioStart", "portfolioEnd", "portfolioPower", "portfolioCapacity",
].forEach((id) => $(id)?.addEventListener("input", () => {
  $("exportPortfolioCandidates").disabled = true;
  $("exportPortfolioCandidatesXlsx").disabled = true;
  $("optimizePortfolioSnapshot").disabled = true;
}));
$("refreshLegacy").addEventListener("click", refreshLegacyManagement);
$("legacyTableKind").addEventListener("change", refreshLegacyManagement);
if ($("importPreviewButton")) $("importPreviewButton").addEventListener("click", previewImport);
if ($("importCommitButton")) $("importCommitButton").addEventListener("click", commitImport);
$("systemRunKind").addEventListener("change", refreshSystem);
$("systemRunStatus").addEventListener("change", refreshSystem);
$("powerMw").addEventListener("input", updateDurationHint);
$("capacityMwh").addEventListener("input", updateDurationHint);
if ($("financialParameterGroup")) {
  $("financialParameterGroup").addEventListener("change", syncFinancialParameterGroup);
  syncFinancialParameterGroup();
}
["powerMw", "capacityMwh", "annualRevenue"].forEach((id) => $(id).addEventListener("input", () => {
  if (financialSourceRunId) $("taskMessage").textContent = "已修改规模或收入，当前使用手动财务假设；可重新从节点分析带入。";
  financialSourceRunId = null;
}));
document.querySelectorAll("[data-view]").forEach((item) => item.addEventListener("click", () => activateView(item.dataset.view)));
$("downloadReport").addEventListener("click", (event) => {
  event.preventDefault(); ReportUI.xlsx(event.currentTarget.href, "财务测算.xlsx", event.currentTarget, "taskView");
});
$("downloadTemplateReport").addEventListener("click", (event) => {
  event.preventDefault(); ReportUI.xlsx(event.currentTarget.href, "独立储能项目经济性测算工具.xlsm", event.currentTarget, "taskView");
});
ReportUI.init();
activateView("overviewView");
refreshSystem();
loadNodes().then(refresh).catch((error) => { $("notice").textContent = `无法连接 API：${error.message}`; setStatus("API 未连接", "error"); });
