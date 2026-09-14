const apiBase = window.BANBOOS_API_BASE || "http://127.0.0.1:8000";
const $ = (id) => document.getElementById(id);

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
  if (!body.items.length) $("node").add(new Option("暂无节点", ""));
  await syncDateRange();
  setStatus(`API 已连接 · ${body.data_mode}`, "ok");
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
    const run = await post("/api/v1/runs", { kind: "financial", parameters: {
      power_mw: power, capacity_mwh: capacity,
      annual_revenue_yuan: Number($("annualRevenue").value),
    }});
    message.textContent = `任务 ${run.run_id} 已进入队列`;
    await pollRun(run.run_id);
  } catch (error) {
    state.textContent = "提交失败";
    state.className = "status status-error";
    message.textContent = error.message;
  }
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
      return;
    }
    if (["failed", "cancelled"].includes(run.status)) throw new Error(run.message || "任务未完成");
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("任务轮询超时，请稍后按 run_id 查询");
}

$("province").addEventListener("change", () => loadNodes().catch((error) => { $("notice").textContent = error.message; setStatus("API 请求失败", "error"); }));
$("node").addEventListener("change", () => syncDateRange().catch((error) => { $("notice").textContent = error.message; setStatus("API 请求失败", "error"); }));
$("market").addEventListener("change", () => syncDateRange().catch((error) => { $("notice").textContent = error.message; setStatus("API 请求失败", "error"); }));
$("refresh").addEventListener("click", refresh);
$("submitFinancial").addEventListener("click", submitFinancial);
$("powerMw").addEventListener("input", updateDurationHint);
$("capacityMwh").addEventListener("input", updateDurationHint);
document.querySelectorAll("[data-view]").forEach((item) => item.addEventListener("click", () => activateView(item.dataset.view)));
activateView("overviewView");
loadNodes().then(refresh).catch((error) => { $("notice").textContent = `无法连接 API：${error.message}`; setStatus("API 未连接", "error"); });
