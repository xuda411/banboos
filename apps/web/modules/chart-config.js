/**
 * Banboos Chart Config — 统一图表配置层
 * 集中管理所有 Canvas / SVG 图表的系列色、网格、坐标轴、悬浮提示、字体。
 * 所有图表绘制必须从此模块读取配置，禁止硬编码色值。
 */
(function (global) {
  "use strict";

  const BanboosChartConfig = {
    font: {
      family: '"Microsoft YaHei", system-ui, sans-serif',
      sizeAxis: "11px",
      sizeTitle: "13px",
      sizeTooltip: "12px",
      numeric: "tabular-nums",
    },

    grid: {
      color: "#dfe5e2",
      colorSoft: "#e1e8e4",
      colorFaint: "#e2eae5",
      lineWidth: 1,
      dash: "3 5",
    },

    axes: {
      lineColor: "#a8bbb0",
      tickColor: "#5f7068",
      tickColorMuted: "#53665d",
      cursorColor: "#71877a",
      cursorBamboo: "rgba(23,107,80,.35)",
      cursorDash: "3 3",
    },

    series: {
      bamboo: "#176b50",
      bambooSoft: "#9fc5b1",

      weather: {
        ghi: "#d9a441",
        pv: "#f07832",
        wind: "#3c8b72",
        windPower: "#6d55b5",
      },

      dispatch: {
        target: "#a7731a",
        storage: "#176b50",
        soc: "#526f99",
        charge: "#d29b2f",
        discharge: "#c6554d",
      },

      spread: {
        price: "#176b50",
        soc: "#5e62ad",
      },
    },

    legend: {
      textColor: "#3d5449",
      textColorMuted: "#53665d",
      badgeText: "#78561c",
      badgeBg: "#faf3e4",
    },

    statusDot: {
      ok: "#47aa71",
      warning: "#c89b42",
      muted: "#765918",
    },

    tooltip: {
      fill: "#ffffff",
      stroke: "#176b50",
      text: "#243a30",
      lineWidth: 2,
      radius: 7,
      padding: 9,
    },
  };

  global.BanboosChartConfig = BanboosChartConfig;
})(window);
