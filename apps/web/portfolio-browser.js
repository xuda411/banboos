/* Selection is keyed by immutable snapshot + node ID, never by visible row index. */
window.PortfolioBrowser = (() => {
  const $ = (id) => document.getElementById(id);
  let api, onOpen, onSelection, onImport;
  let snapshot = null, epoch = 0, offset = 0, historyOffset = 0;
  const selected = new Map();
  const state = (text) => { $("candidateBrowserState").textContent = text; };
  const selectionChanged = () => {
    $("candidateSelectionCount").textContent = `已选 ${selected.size} / 50 个节点（跨页保留）`;
    $("candidateImport").disabled = !selected.size;
    onSelection(selected.size);
  };
  async function loadPage(nextOffset = 0, opening = false) {
    if (!snapshot) return;
    const ticket = ++epoch;
    $("candidatePrev").disabled = true; $("candidateNext").disabled = true;
    $("candidateRows").replaceChildren();
    state("正在加载候选…");
    try {
      const page = await api(`/api/v1/portfolio/candidates/${snapshot}/page`, {
        offset: nextOffset, limit: 20, province: $("candidateProvince").value,
        q: $("candidateQuery").value.trim(),
      });
      if (ticket !== epoch) return;
      offset = nextOffset;
      if (opening) {
        $("candidateProvince").replaceChildren(new Option("全部省份", ""),
          ...page.provinces.map((name) => new Option(name, name)));
        onOpen(page.parameters, page.total);
      }
      for (const item of page.items) {
        const row = document.createElement("tr"); const cell = document.createElement("td");
        const check = document.createElement("input"); check.type = "checkbox";
        check.checked = selected.has(item.node_id); check.setAttribute("aria-label", `选择 ${item.name}`);
        check.addEventListener("change", () => {
          if (check.checked && selected.size >= 50) {
            check.checked = false; state("一次最多选择50个节点，请取消部分选择后重试。"); return;
          }
          if (check.checked) selected.set(item.node_id, item); else selected.delete(item.node_id);
          selectionChanged();
        });
        cell.append(check); row.append(cell);
        for (const value of [item.name, item.province || "未配置", item.valid_days,
          item.baseline_policy === "latest_complete_year" ? "最近完整年度" : "全部有效日",
          item.spread_yuan_per_mwh.toFixed(2), item.annual_revenue_wan.toFixed(2)]) {
          const td = document.createElement("td"); td.textContent = value; row.append(td);
        }
        $("candidateRows").append(row);
      }
      state(page.filtered_total ? `第 ${Math.floor(offset / 20) + 1} 页 · 筛选 ${page.filtered_total} / 全部 ${page.total} 个节点 · 快照 ${snapshot.slice(0, 12)}` : "此筛选没有候选，请调整省份或关键词。");
      $("candidatePrev").disabled = offset === 0;
      $("candidateNext").disabled = offset + 20 >= page.filtered_total;
    } catch (error) { if (ticket === epoch) state(`加载失败：${error.message}。可点击筛选重试。`); }
  }
  async function open(id) {
    snapshot = id; selected.clear(); selectionChanged();
    $("candidateProvince").value = ""; $("candidateQuery").value = "";
    await loadPage(0, true);
  }
  async function history(nextOffset = 0) {
    $("candidateHistoryPrev").disabled = true; $("candidateHistoryNext").disabled = true;
    try {
      const result = await api("/api/v1/portfolio/candidates/snapshots", { offset: nextOffset, limit: 20 });
      historyOffset = nextOffset;
      $("candidateHistory").replaceChildren(new Option(`选择历史快照（共${result.total}份）`, ""),
        ...result.items.map((item) => new Option(`${item.market} · ${item.start_date} 至 ${item.end_date} · ${item.candidate_count}节点 · ${item.snapshot_id.slice(0, 8)}`, item.snapshot_id)));
      $("candidateHistoryPrev").disabled = historyOffset === 0;
      $("candidateHistoryNext").disabled = historyOffset + 20 >= result.total;
    } catch (error) { state(`历史快照加载失败：${error.message}`); }
  }
  function init(options) {
    ({ api, onOpen, onSelection, onImport } = options);
    $("candidateApply").onclick = () => loadPage(0);
    $("candidatePrev").onclick = () => loadPage(Math.max(0, offset - 20));
    $("candidateNext").onclick = () => loadPage(offset + 20);
    $("candidateHistoryRefresh").onclick = () => history();
    $("candidateHistoryPrev").onclick = () => history(Math.max(0, historyOffset - 20));
    $("candidateHistoryNext").onclick = () => history(historyOffset + 20);
    $("candidateHistory").onchange = (event) => { if (event.target.value) open(event.target.value); };
    $("candidateClear").onclick = () => { selected.clear(); selectionChanged(); loadPage(offset); };
    $("candidateImport").onclick = () => onImport([...selected.values()]);
    selectionChanged();
  }
  return { init, open, history, selectedIds: () => [...selected.keys()] };
})();
