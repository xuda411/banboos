/* Display-only typical day; never submitted to telemetry or financial APIs. */
(function () {
  function createDay() {
    const rows = [];
    let energy = 90;
    const efficiency = 0.95;
    for (let i = 0; i <= 96; i++) {
      const hour = i / 4;
      const solar = hour > 6 && hour < 18
        ? 108 * Math.sin(Math.PI * (hour - 6) / 12) ** 1.65 * (1 - 0.13 * Math.exp(-(((hour - 13.25) / 0.6) ** 2))) : 0;
      let power = hour >= 1 && hour < 4 ? -30 : hour >= 7 && hour < 9 ? 42
        : hour >= 11 && hour < 14 ? -34 : hour >= 18 && hour < 21 ? 46 : 0;
      if (i === 96) power = 0;
      // Power is the average for the next 15 minutes; SOC is at this timestamp.
      power = power >= 0 ? Math.min(power, Math.max(0, (energy - 20) * efficiency / 0.25))
        : -Math.min(-power, Math.max(0, (180 - energy) / efficiency / 0.25));
      rows.push({ hour, time: `${String(Math.floor(hour)).padStart(2, "0")}:${i % 4 ? String(i % 4 * 15) : "00"}`,
        solar, power, soc: energy / 2 });
      if (i < 96) energy += power < 0 ? -power * 0.25 * efficiency : -power * 0.25 / efficiency;
    }
    return rows;
  }
  if (typeof module !== "undefined") module.exports = { createDay };
  if (typeof document === "undefined") return;
  const host = document.getElementById("pulsePlot");
  if (!host) return;
  const rows = createDay();
  const slider = document.getElementById("pulseTime");
  const readout = document.getElementById("pulseReadout");
  let selected = 52;
  let width = 600;
  const height = 240, top = 28, bottom = 206, left = 42, right = 36;
  const x = hour => left + hour / 24 * (width - left - right);
  const y = power => bottom - (power + 60) / 180 * (bottom - top);
  const sy = soc => bottom - soc / 100 * (bottom - top);
  const point = (row, key) => `${x(row.hour).toFixed(2)},${(key === "soc" ? sy(row.soc) : y(row[key])).toFixed(2)}`;
  function select(index) {
    selected = Math.max(0, Math.min(96, index));
    const row = rows[selected];
    slider.value = selected;
    const mode = row.power < -0.05 ? "充电" : row.power > 0.05 ? "放电" : "待机";
    readout.innerHTML = `<span><b>${row.time}</b> · ${mode}</span><span>光伏 <b>${row.solar.toFixed(1)}</b> MW</span><span>储能 <b>${row.power.toFixed(1)}</b> MW</span><span>SOC <b>${row.soc.toFixed(1)}</b>%</span>`;
    slider.setAttribute("aria-valuetext", `${row.time}，${mode}，光伏 ${row.solar.toFixed(1)} 兆瓦，储能 ${row.power.toFixed(1)} 兆瓦，SOC ${row.soc.toFixed(1)}%`);
    host.querySelector(".pulse-cursor").setAttribute("x1", x(row.hour));
    host.querySelector(".pulse-cursor").setAttribute("x2", x(row.hour));
    ["solar", "power", "soc"].forEach(key => {
      const dot = host.querySelector(`[data-point="${key}"]`);
      dot.setAttribute("cx", x(row.hour)); dot.setAttribute("cy", key === "soc" ? sy(row.soc) : y(row[key]));
    });
  }
  function draw() {
    width = Math.max(270, Math.round(host.getBoundingClientRect().width));
    const solarPoints = rows.map(row => point(row, "solar")).join(" ");
    const powerPoints = rows.flatMap((row, i) => i ? [`${x(row.hour)},${y(rows[i - 1].power)}`, point(row, "power")] : [point(row, "power")]).join(" ");
    host.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="模拟典型日曲线：午间光伏出力升高，储能分时充放电；右轴为 SOC。下方时间滑块可查看全部数值。">
      <defs><linearGradient id="pulseSolarFill" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#bb8626" stop-opacity=".16"/><stop offset="1" stop-color="#bb8626" stop-opacity=".01"/></linearGradient></defs>
      ${[-60, 0, 60, 120].map(value => `<line x1="${left}" x2="${width - right}" y1="${y(value)}" y2="${y(value)}" class="${value === 0 ? "pulse-zero" : "pulse-gridline"}"/><text x="${left - 8}" y="${y(value) + 4}" text-anchor="end">${value}</text>`).join("")}
      ${[0, 50, 100].map(value => `<text x="${width - right + 8}" y="${sy(value) + 4}">${value}</text>`).join("")}
      ${[0, 6, 12, 18, 24].map(hour => `<text x="${x(hour)}" y="229" text-anchor="middle">${String(hour).padStart(2, "0")}:00</text>`).join("")}
      <text x="${left}" y="14">功率 / MW</text><text x="${width - right}" y="14" text-anchor="end">SOC / %</text>
      <polygon points="${x(0)},${y(0)} ${solarPoints} ${x(24)},${y(0)}" fill="url(#pulseSolarFill)"/>
      <polyline points="${solarPoints}" class="pulse-solar"/>
      <polyline points="${powerPoints}" class="pulse-storage"/>
      <polyline points="${rows.map(row => point(row, "soc")).join(" ")}" class="pulse-soc"/>
      <line class="pulse-cursor" y1="${top}" y2="${bottom}"/>
      ${["solar", "power", "soc"].map(key => `<circle data-point="${key}" r="4" class="pulse-dot-${key}"/>`).join("")}
    </svg>`;
    select(selected);
  }
  slider.addEventListener("input", () => select(Number(slider.value)));
  host.addEventListener("pointermove", event => {
    if (event.pointerType === "touch") return;
    select(Math.round((event.clientX - host.getBoundingClientRect().left - left) / (width - left - right) * 96));
  });
  host.addEventListener("click", event => select(Math.round((event.clientX - host.getBoundingClientRect().left - left) / (width - left - right) * 96)));
  new ResizeObserver(() => { if (host.getBoundingClientRect().width) draw(); }).observe(host);
  draw();
})();
