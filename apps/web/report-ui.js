/* Export controls bind to the loaded query, never to subsequently edited inputs. */
window.ReportUI = (() => {
  const states = new Map();
  const $ = (id) => document.getElementById(id);
  const configs = {
    curve: { view: "curveView", controls: ["curveNode", "curveMarket", "curveStart", "curveEnd", "curveLimit", "curveAggregateDuration"], buttons: ["exportCurves", "exportCurveAggregate", "exportCurveAggregateXlsx", "exportCurvePng", "exportCurveXlsx"] },
    weather: { view: "weatherView", controls: ["weatherNode", "weatherType", "weatherStart", "weatherEnd", "weatherGranularity"], buttons: ["exportWeatherPng", "exportWeatherXlsx"] },
  };
  function notice(key, message) {
    let element = $(`${key}ExportMessage`);
    if (!element) {
      element = document.createElement("p"); element.id = `${key}ExportMessage`;
      element.className = "export-message"; element.setAttribute("role", "status");
      $(configs[key]?.view || key).append(element);
    }
    element.textContent = message;
  }
  function invalidate(key, message = "条件已修改，请重新加载后导出。") {
    const epoch = (states.get(key)?.epoch || 0) + 1;
    states.set(key, { epoch, ready: false });
    configs[key].buttons.forEach((id) => { $(id).disabled = true; });
    notice(key, message);
    return epoch;
  }
  function begin(key, query, label) {
    const epoch = invalidate(key, "正在加载，完成后可导出。");
    states.set(key, { epoch, ready: false, query: { ...query }, label });
    return epoch;
  }
  function current(key, epoch) { return states.get(key)?.epoch === epoch; }
  function complete(key, epoch, count, source) {
    if (!current(key, epoch)) return false;
    Object.assign(states.get(key), { ready: count > 0, source, loadedAt: new Date().toLocaleString("zh-CN") });
    configs[key].buttons.forEach((id) => { $(id).disabled = !count; });
    notice(key, count ? "PNG 保存当前图表；Excel 按本次加载条件重新读取原始明细（含日数/条数上限）。" : "没有有效数据，不能导出。");
    return true;
  }
  function save(blob, name) {
    const url = URL.createObjectURL(blob); const link = document.createElement("a");
    link.href = url; link.download = name.replace(/[\\/:*?"<>|]/g, "_"); document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  }
  async function xlsx(url, name, button, key) {
    button.disabled = true; notice(key, "正在生成 Excel…");
    try {
      const response = await fetch(url);
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === "string" ? body.detail : `导出请求失败（HTTP ${response.status}）`);
      }
      if (!response.headers.get("Content-Type")?.includes("spreadsheetml")) throw new Error("服务未返回 Excel 文件，请重试。");
      const blob = await response.blob(); const magic = new Uint8Array(await blob.slice(0, 2).arrayBuffer());
      if (magic[0] !== 80 || magic[1] !== 75) throw new Error("Excel 文件内容异常，请重试。");
      save(blob, name); notice(key, "文件已交给浏览器下载，请在下载列表查看。");
    } catch (error) { notice(key, `导出失败：${error.message}`); }
    finally { button.disabled = configs[key] ? !states.get(key)?.ready : false; }
  }
  async function download(url, name, button, messageTarget) {
    button.disabled = true;
    const target = messageTarget ? $(`${messageTarget}ExportMessage`) : null;
    if (target) target.textContent = "正在生成 Excel…";
    try {
      const response = await fetch(url);
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === "string" ? body.detail : `导出请求失败（HTTP ${response.status}）`);
      }
      if (!response.headers.get("Content-Type")?.includes("spreadsheetml")) throw new Error("服务未返回 Excel 文件，请重试。");
      const blob = await response.blob(); const magic = new Uint8Array(await blob.slice(0, 2).arrayBuffer());
      if (magic[0] !== 80 || magic[1] !== 75) throw new Error("Excel 文件内容异常，请重试。");
      save(blob, name); if (target) target.textContent = "Excel 已交给浏览器下载。";
    } catch (error) { if (target) target.textContent = `导出失败：${error.message}`; }
    finally { button.disabled = false; }
  }  async function exportQuery(key, button, base) {
    const state = states.get(key); if (!state?.ready) return;
    const path = key === "curve" ? "price" : "weather";
    await xlsx(`${base}/api/v1/${path}/export?${new URLSearchParams(state.query)}`, `${state.label}-${path}.xlsx`, button, key);
  }
  function wrap(context, value, width) {
    const lines = []; let line = "";
    for (const char of String(value)) {
      if (char === "\n" || context.measureText(line + char).width > width) { lines.push(line); line = char === "\n" ? "" : char; }
      else line += char;
    }
    if (line) lines.push(line); return lines;
  }
  async function png(key, canvasId, title) {
    const state = states.get(key); if (!state?.ready) return;
    try {
      await document.fonts.ready;
      const source = $(canvasId); const width = Math.max(800, source.width / 2 + 64);
      const canvas = document.createElement("canvas"); const context = canvas.getContext("2d");
      context.font = '16px "Microsoft YaHei", sans-serif';
      const meta = wrap(context, `${state.label}\n${title}\n${state.source}\n数据加载时间：${state.loadedAt} · PNG 为当前图表快照`, width - 64);
      const top = 94 + meta.length * 24; const imageHeight = (width - 64) * source.height / source.width;
      canvas.width = width * 2; canvas.height = (top + imageHeight + 48) * 2;
      context.scale(2, 2); context.fillStyle = "#ffffff"; context.fillRect(0, 0, width, canvas.height / 2);
      context.fillStyle = "#173b35"; context.font = 'bold 26px "Microsoft YaHei", sans-serif';
      context.fillText(key === "curve" ? "历史电价曲线 · 元/MWh" : "气象与预计功率", 32, 46);
      context.font = '16px "Microsoft YaHei", sans-serif';
      meta.forEach((line, i) => context.fillText(line, 32, 80 + i * 24));
      context.drawImage(source, 32, top, width - 64, imageHeight);
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
      if (!blob) throw new Error("图片生成失败");
      save(blob, `${state.label}-${key}.png`); notice(key, "PNG 已交给浏览器下载，包含标题、来源与加载时间。");
    } catch (error) { notice(key, `图片导出失败：${error.message}`); }
  }
  function run(key, runId, label, base) {
    let box = $(`${key}RunExport`);
    if (!box) { box = document.createElement("div"); box.id = `${key}RunExport`; box.className = "run-export"; $(key).append(box); }
    box.replaceChildren(); const button = document.createElement("button"); button.type = "button"; button.textContent = `下载${label} Excel`;
    const caption = document.createElement("span"); caption.textContent = `结果任务：${runId}`;
    button.addEventListener("click", () => xlsx(`${base}/api/v1/runs/${runId}/export`, `${label}-${runId}.xlsx`, button, key));
    box.append(button, caption); box.hidden = false;
  }
  function clearRun(key) { const box = $(`${key}RunExport`); if (box) box.hidden = true; }
  function init() {
    Object.entries(configs).forEach(([key, config]) => {
      config.controls.forEach((id) => $(id).addEventListener("input", () => invalidate(key)));
      config.controls.forEach((id) => $(id).addEventListener("change", () => invalidate(key)));
    });
  }
  return { begin, current, complete, invalidate, init, exportQuery, png, run, clearRun, xlsx };
})();
