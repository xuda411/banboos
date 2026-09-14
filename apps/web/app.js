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

function setStatus(text, kind = "muted") {
  $("apiState").textContent = text;
  $("apiState").className = `status status-${kind}`;
}

async function loadNodes() {
  const body = await get("/api/v1/nodes", { province: $("province").value });
  $("node").replaceChildren(...body.items.map((item) => new Option(`${item.name} · ${item.province}`, item.id)));
  if (!body.items.length) $("node").add(new Option("暂无节点", ""));
  setStatus(`API 已连接 · ${body.data_mode}`, "ok");
}

async function refresh() {
  try {
    const nodeId = $("node").value;
    if (!nodeId) throw new Error("请选择节点");
    const price = await get("/api/v1/price/summary", { node_id: nodeId, market: $("market").value, start_date: $("startDate").value, end_date: $("endDate").value });
    const weather = await get("/api/v1/weather/summary", { node_id: nodeId });
    $("validDays").textContent = price.valid_days;
    $("dataPoints").textContent = price.data_points.toLocaleString();
    $("weatherRows").textContent = weather.observations;
    $("priceSource").textContent = price.sources.length ? price.sources.join("、") : "演示/暂无来源文件";
    $("priceRange").textContent = price.first_date ? `${price.first_date} 至 ${price.last_date}` : "所选范围暂无有效日";
    $("weatherSource").textContent = weather.source || "暂无气象观测";
    $("notice").textContent = "只读结果已更新。正式分析、控制指令和生产数据接入将在后续阶段开放。";
  } catch (error) {
    $("notice").textContent = `读取失败：${error.message}`;
    setStatus("API 请求失败", "error");
  }
}

$("province").addEventListener("change", () => loadNodes().catch((error) => { $("notice").textContent = error.message; setStatus("API 请求失败", "error"); }));
$("refresh").addEventListener("click", refresh);
loadNodes().then(refresh).catch((error) => { $("notice").textContent = `无法连接 API：${error.message}`; setStatus("API 未连接", "error"); });
