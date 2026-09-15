const apiBase = window.BANBOOS_API_BASE || "http://127.0.0.1:8000";
const $ = (id) => document.getElementById(id);
let analysisSourceRunId = null;
let analysisAnnualRevenueYuan = null;
let analysisScale = null;
let financialSourceRunId = null;

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
  const body = await get("/api/v1/nodes", { province: $("province").value });
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

async function syncCurveDateRange() {
  const nodeId = $("curveNode").value;
  if (!nodeId) return;
  const range = await get("/api/v1/price/range", { node_id: nodeId, market: $("curveMarket").value });
  if (range.first_date) $("curveStart").value = range.first_date;
  if (range.last_date) $("curveEnd").value = range.last_date;
}

function drawCurves(curves, selectedIndex = 0) {
  const canvas = $("curveChart");
  const width = canvas.clientWidth || 700;
  const height = 340;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = width * ratio; canvas.height = height * ratio;
  const context = canvas.getContext("2d"); context.scale(ratio, ratio);
  context.clearRect(0, 0, width, height);
  if (!curves.length) return;
  const values = curves.flatMap((curve) => curve.prices);
  const min = Math.min(...values); const max = Math.max(...values); const span = max - min || 1;
  const pad = { left: 42, right: 14, top: 18, bottom: 30 };
  context.strokeStyle = "#dfe5e2"; context.lineWidth = 1;
  for (let step = 0; step <= 4; step += 1) {
    const y = pad.top + (height - pad.top - pad.bottom) * step / 4;
    context.beginPath(); context.moveTo(pad.left, y); context.lineTo(width - pad.right, y); context.stroke();
    context.fillStyle = "#5f7068"; context.font = "11px Microsoft YaHei"; context.fillText((max - span * step / 4).toFixed(1), 4, y + 4);
  }
  curves.forEach((curve, curveIndex) => {
    context.strokeStyle = curveIndex === selectedIndex ? "#176b50" : "#9fc5b1";
    context.lineWidth = curveIndex === selectedIndex ? 2.4 : 1.2;
    context.beginPath();
    curve.prices.forEach((value, index) => {
      const x = pad.left + (width - pad.left - pad.right) * index / 95;
      const y = pad.top + (height - pad.top - pad.bottom) * (max - value) / span;
      index ? context.lineTo(x, y) : context.moveTo(x, y);
    });
    context.stroke();
  });
  context.fillStyle = "#5f7068"; context.font = "11px Microsoft YaHei";
  context.fillText("00:15", pad.left, height - 8); context.fillText("12:00", width / 2 - 18, height - 8); context.fillText("24:00", width - 48, height - 8);
}

async function loadCurves() {
  const nodeId = $("curveNode").value;
  if (!nodeId) { $("curveState").textContent = "请选择节点"; return; }
  $("curveState").textContent = "加载中"; $("curveState").className = "status status-muted";
  try {
    const curves = await get("/api/v1/price/curves", { node_id: nodeId, market: $("curveMarket").value, start_date: $("curveStart").value, end_date: $("curveEnd").value, limit: $("curveLimit").value });
    const dayList = $("curveDays"); dayList.replaceChildren();
    curves.forEach((curve, index) => { const day = document.createElement("button"); day.className = `curve-day${index === 0 ? " active" : ""}`; day.textContent = curve.run_date; day.addEventListener("click", () => { document.querySelectorAll(".curve-day").forEach((item) => item.classList.remove("active")); day.classList.add("active"); drawCurves(curves, index); $("curveTitle").textContent = `${curve.run_date} · ${$("curveMarket").value}`; }); dayList.appendChild(day); });
    $("curveEmpty").hidden = curves.length > 0; $("curveTitle").textContent = curves.length ? `${curves[0].run_date} · ${$("curveMarket").value}` : "当前范围暂无完整曲线"; $("curveState").textContent = curves.length ? `${curves.length} 天` : "暂无数据"; $("curveState").className = `status ${curves.length ? "status-ok" : "status-muted"}`;
    if (!curves.length) dayList.innerHTML = '<div class="empty-state">数据库暂无完整 96 点曲线</div>'; drawCurves(curves);
  } catch (error) { $("curveState").textContent = "加载失败"; $("curveState").className = "status status-error"; $("curveEmpty").hidden = false; $("curveEmpty").textContent = `读取失败：${error.message}`; }
}

function drawWeather(series) {
  const canvas = $("weatherChart"); const width = canvas.clientWidth || 760; const height = 330; const ratio = window.devicePixelRatio || 1;
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
  try {
    const rawSeries = await get("/api/v1/weather/series", { node_id: nodeId, start_time: $("weatherStart").value, end_time: $("weatherEnd").value, limit: 744 });
    const series = aggregateWeather(rawSeries, $("weatherGranularity").value);
    const mean = (key) => { const values = series.map((row) => row[key]).filter((value) => value != null); return values.length ? (values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(1) : "—"; };
    $("weatherObservations").textContent = series.length; $("weatherGhi").textContent = mean("ghi_w_m2"); $("weatherWind").textContent = mean("wind_speed_m_s"); $("weatherTemp").textContent = mean("temp_c"); $("weatherSourceDetail").textContent = series.length ? `${series[0].source || "未标注来源"} · ${series[0].is_power_simulated ? "功率估算" : "功率实测"}` : "当前范围暂无气象观测"; $("weatherChartTitle").textContent = series.length ? `${series[0].data_time.slice(0, 10)} 至 ${series[series.length - 1].data_time.slice(0, 10)}` : "当前范围暂无观测"; $("weatherEmpty").hidden = series.length > 0; if (!series.length) $("weatherEmpty").textContent = "数据库暂无气象观测"; drawWeather(series);
  } catch (error) { $("weatherEmpty").hidden = false; $("weatherEmpty").textContent = `读取失败：${error.message}`; }
}

async function submitAnalysis() {
  const nodeId = $("node").value; const state = $("analysisState"); const resultBox = $("analysisResult");
  analysisSourceRunId = null; analysisAnnualRevenueYuan = null; analysisScale = null;
  $("useAnalysisForFinance").disabled = true;
  const power = Number($("analysisPower").value); const capacity = Number($("analysisCapacity").value);
  const duration = capacity / power;
  if (!nodeId) { resultBox.hidden = false; state.textContent = "请选择节点"; state.className = "status status-error"; return; }
  if (!Number.isFinite(duration) || duration < 0.25 || duration > 24) { resultBox.hidden = false; state.textContent = "参数无效"; state.className = "status status-error"; $("analysisMessage").textContent = "容量/功率时长须在 0.25 至 24 小时之间"; return; }
  resultBox.hidden = false; $("analysisMonthly").hidden = true; state.textContent = "提交中"; state.className = "status status-muted"; $("analysisMessage").textContent = "正在读取完整历史日并计算价差…"; $("analysisAnnual").textContent = "—"; $("analysisDays").textContent = "—"; analysisSourceRunId = null; analysisAnnualRevenueYuan = null; $("submitAnalysis").disabled = true;
  try {
    const run = await post("/api/v1/runs", { kind: "price-analysis", parameters: { node_id: Number(nodeId), market: $("market").value, start_date: $("startDate").value, end_date: $("endDate").value, power_mw: power, capacity_mwh: capacity, round_trip_efficiency: Number($("analysisEta").value) / 100 } });
    const finished = await pollAnalysis(run.run_id); const data = finished.result || {};
    analysisSourceRunId = run.run_id; analysisAnnualRevenueYuan = Number(data.annualized_revenue_yuan); analysisScale = { power: data.power_mw, capacity: data.capacity_mwh };
    state.textContent = "计算完成"; state.className = "status status-ok";
    $("analysisMessage").textContent = `连续低/高均价 ${Number(data.charge_price_yuan_per_mwh).toFixed(2)} / ${Number(data.discharge_price_yuan_per_mwh).toFixed(2)} 元/MWh；均价差 ${Number(data.spread_yuan_per_mwh).toFixed(2)}`;
    $("analysisAnnual").textContent = `${(analysisAnnualRevenueYuan / 10000).toLocaleString(undefined, {maximumFractionDigits: 2})} 万元/年（估算）`;
    $("analysisDays").textContent = `${data.baseline_policy === "latest_complete_year" ? "最近完整年度" : "不足完整年度，全部有效日"}：${data.start_date} 至 ${data.end_date}，${data.valid_days} 天；快照 ${data.snapshot_id.slice(0, 12)}`;
    renderAnalysisMonthly(data.monthly);
    $("useAnalysisForFinance").disabled = false;
  } catch (error) { state.textContent = "计算失败"; state.className = "status status-error"; $("analysisMessage").textContent = error.message; } finally { $("submitAnalysis").disabled = false; }
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
  financialSourceRunId = analysisSourceRunId; updateDurationHint();
  activateView("taskView"); $("taskMessage").textContent = `已带入节点价差结果（run_id: ${analysisSourceRunId}）`; $("taskState").textContent = "待提交"; $("taskState").className = "status status-muted";
}

function invalidateAnalysisSelection() {
  analysisSourceRunId = null; analysisAnnualRevenueYuan = null; analysisScale = null; $("useAnalysisForFinance").disabled = true; $("analysisResult").hidden = true; $("analysisMonthly").hidden = true;
}

async function submitDispatch() {
  const nodeId = $("dispatchNode").value; const state = $("dispatchState"); const message = $("dispatchMessage");
  if (!nodeId) { message.textContent = "请选择节点"; return; }
  const power = Number($("dispatchPower").value); const capacity = Number($("dispatchCapacity").value);
  if (!Number.isFinite(power) || !Number.isFinite(capacity) || power <= 0 || capacity <= 0 || capacity / power < 0.25 || capacity / power > 24) { state.textContent = "参数无效"; state.className = "status status-error"; message.textContent = "容量/功率时长须在 0.25 至 24 小时之间"; return; }
  state.textContent = "提交中"; state.className = "status status-muted"; $("dispatchResult").hidden = true;
  const parameters = { node_id: Number(nodeId), market: $("dispatchMarket").value, start_date: $("dispatchStart").value, end_date: $("dispatchEnd").value, power_mw: power, capacity_mwh: capacity, eta_charge: Number($("dispatchEta").value) / 100, eta_discharge: Number($("dispatchEta").value) / 100, max_daily_cycles: Number($("dispatchCycles").value), hurdle_yuan_per_mwh: Number($("dispatchHurdle").value) };
  try { const run = await post("/api/v1/runs", { kind: "strict-dispatch", parameters }); $("dispatchRunId").textContent = run.run_id; const finished = await pollDispatch(run.run_id); renderDispatchResult(finished.result); } catch (error) { state.textContent = "回放失败"; state.className = "status status-error"; message.textContent = error.message; }
}

async function pollDispatch(runId) {
  const state = $("dispatchState"); const message = $("dispatchMessage");
  for (let attempt = 0; attempt < 300; attempt += 1) { const run = await get(`/api/v1/runs/${runId}`); state.textContent = `${run.status} ${run.progress}%`; state.className = run.status === "succeeded" ? "status status-ok" : "status status-muted"; message.textContent = run.message || "任务执行中"; if (run.status === "succeeded") return run; if (["failed", "cancelled"].includes(run.status)) throw new Error(`${run.message || "任务未完成"}${run.error_code ? `（${run.error_code}）` : ""}`); await new Promise((resolve) => setTimeout(resolve, 1000)); }
  throw new Error("回放轮询超时，请稍后按 run_id 查询");
}

function renderDispatchResult(result) {
  if (!result) return; const money = (value) => value == null ? "—" : `${(Number(value) / 10000).toLocaleString(undefined, {maximumFractionDigits: 2})} 万元`; $("dispatchValidDays").textContent = result.valid_days ?? "—"; $("dispatchTotalRevenue").textContent = money(result.total_net_revenue_yuan); $("dispatchAnnualRevenue").textContent = money(result.annualized_net_revenue_yuan); $("dispatchSnapshot").textContent = result.snapshot_id ? `${result.snapshot_id.slice(0, 8)}…` : "—"; $("dispatchResult").hidden = false;
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
    $("priceSource").textContent = price.sources.length ? price.sources.join("、") : "演示/暂无来源文件";
    $("priceRange").textContent = price.first_date ? `${price.first_date} 至 ${price.last_date}` : "所选范围暂无有效日";
    $("weatherSource").textContent = weather.source || "暂无气象观测";
    $("overviewValidDays").textContent = price.valid_days;
    $("overviewDataPoints").textContent = price.data_points.toLocaleString();
    $("overviewCoverage").textContent = `${(quality.coverage_ratio * 100).toFixed(1)}%`;
    $("overviewRange").textContent = price.first_date ? `${price.first_date} 至 ${price.last_date}` : "所选范围暂无有效日";
    await refreshOperationsSummary();
    $("notice").textContent = "只读结果已更新。正式分析、控制指令和生产数据接入将在后续阶段开放。";
  } catch (error) {
    $("notice").textContent = `读取失败：${error.message}`;
    setStatus("API 请求失败", "error");
  }
}

async function submitFinancial() {
  const state = $("taskState");
  const message = $("taskMessage");
  const download = $("downloadReport");
  $("financeResult").hidden = true;
  download.hidden = true;
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
    message.textContent = `任务 ${run.run_id} 已进入队列`;
    const finished = await pollRun(run.run_id);
    renderFinancialResult(finished.result);
  } catch (error) {
    state.textContent = "提交失败";
    state.className = "status status-error";
    message.textContent = error.message;
  }
}

function collectFinancialParameters() {
  const percent = (id) => Number($(id).value) / 100;
  const optionalNumber = (id) => $(id).value === "" ? null : Number($(id).value);
  return {
    power_mw: Number($("powerMw").value), capacity_mwh: Number($("capacityMwh").value), annual_revenue_yuan: financialSourceRunId ? null : Number($("annualRevenue").value),
    capacity_lease_yuan: Number($("capacityLease").value), capacity_fee_yuan: Number($("capacityFee").value), subsidy_yuan: Number($("subsidy").value),
    primary_frequency_yuan: Number($("primaryFrequency").value), secondary_frequency_yuan: Number($("secondaryFrequency").value), capex_yuan_per_wh: Number($("capex").value), source_run_id: financialSourceRunId || undefined,
    operation_years: Number($("operationYears").value), om_rate: percent("omRate"), om_growth: percent("omGrowth"), first_year_eol: percent("firstEol"), final_eol: percent("finalEol"), residual_rate: percent("residualRate"), income_tax_rate: percent("incomeTaxRate"), discount_rate: percent("discountRate"), loan_ratio: percent("loanRatio"), loan_years: Number($("loanYears").value), loan_rate: percent("loanRate"), construction_years: Number($("constructionYears").value), construction_loan_rate: percent("constructionLoanRate"), replace_year: optionalNumber("replaceYear"), replace_capex_yuan: Number($("replaceCapex").value),
  };
}

async function submitSensitivity() {
  const state = $("sensitivityState"); const message = $("sensitivityMessage"); const resultBox = $("sensitivityResult");
  const down = Number($("sensitivityDown").value) / 100; const up = Number($("sensitivityUp").value) / 100; const step = Number($("sensitivityStep").value) / 100;
  if (!Number.isFinite(down) || !Number.isFinite(up) || !Number.isFinite(step) || down >= up || step <= 0 || Math.ceil((up - down) / step) + 1 > 9) { state.textContent = "参数无效"; state.className = "status status-error"; message.textContent = "请检查上下限和步长，情景点数须为 3 至 9 个"; return; }
  const changeRates = []; for (let value = down; value <= up + 1e-9; value += step) changeRates.push(Number(value.toFixed(6)));
  if (changeRates.length < 3) { state.textContent = "参数无效"; state.className = "status status-error"; message.textContent = "至少需要 3 个情景点"; return; }
  state.textContent = "提交中"; state.className = "status status-muted"; message.textContent = "正在生成敏感性情景…"; resultBox.hidden = true; $("submitSensitivity").disabled = true;
  try {
    const run = await post("/api/v1/runs", { kind: "sensitivity", parameters: { base: collectFinancialParameters(), variable: $("sensitivityVariable").value, change_rates: changeRates } });
    $("sensitivityRunId").textContent = run.run_id; const finished = await pollSensitivity(run.run_id); renderSensitivityResult(finished.result); state.textContent = "计算完成"; state.className = "status status-ok"; message.textContent = "情景结果已绑定当前财务参数。";
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
}

function updateDurationHint() {
  const power = Number($("powerMw").value);
  const capacity = Number($("capacityMwh").value);
  const duration = capacity / power;
  $("durationHint").textContent = Number.isFinite(duration) ? `时长：${duration.toFixed(2)} 小时` : "请输入有效功率和容量";
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
$("loadCurves").addEventListener("click", loadCurves);
$("loadWeather").addEventListener("click", loadWeather);
$("submitAnalysis").addEventListener("click", submitAnalysis);
$("useAnalysisForFinance").addEventListener("click", useAnalysisForFinance);
$("submitDispatch").addEventListener("click", submitDispatch);
$("refresh").addEventListener("click", refresh);
$("submitFinancial").addEventListener("click", submitFinancial);
$("submitSensitivity").addEventListener("click", submitSensitivity);
$("powerMw").addEventListener("input", updateDurationHint);
$("capacityMwh").addEventListener("input", updateDurationHint);
["powerMw", "capacityMwh", "annualRevenue"].forEach((id) => $(id).addEventListener("input", () => {
  if (financialSourceRunId) $("taskMessage").textContent = "已修改规模或收入，当前使用手动财务假设；可重新从节点分析带入。";
  financialSourceRunId = null;
}));
document.querySelectorAll("[data-view]").forEach((item) => item.addEventListener("click", () => activateView(item.dataset.view)));
activateView("overviewView");
loadNodes().then(refresh).catch((error) => { $("notice").textContent = `无法连接 API：${error.message}`; setStatus("API 未连接", "error"); });
