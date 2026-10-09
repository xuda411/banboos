/**
 * Banboos UI Components — 统一状态组件库
 * 提供 StatusBadge、EmptyState、LoadingGuard、ExportButton 四个工厂函数。
 * 所有组件均返回原生 DOM 元素，不依赖任何第三方库。
 *
 * 用法：
 *   const badge = window.BanboosUI.StatusBadge("ok", "运行正常");
 *   element.appendChild(badge);
 */
(function (global) {
  "use strict";

  // ── 工具函数 ────────────────────────────────────────────────
  function createEl(tag, className, attrs) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (attrs) {
      for (const key in attrs) {
        if (key === "text") el.textContent = attrs[key];
        else if (key === "html") el.innerHTML = attrs[key];
        else if (key.startsWith("on") && typeof attrs[key] === "function") {
          el.addEventListener(key.slice(2).toLowerCase(), attrs[key]);
        } else {
          el.setAttribute(key, attrs[key]);
        }
      }
    }
    return el;
  }

  // ── 1. StatusBadge 状态徽章 ────────────────────────────────
  /**
   * @param {"ok"|"progress"|"warning"|"danger"|"muted"} variant
   * @param {string} text
   * @param {{pulse?: boolean, role?: string, ariaLive?: string}} [opts]
   * @returns {HTMLSpanElement}
   */
  function StatusBadge(variant, text, opts) {
    opts = opts || {};
    const el = createEl("span", `status status-${variant}`, {
      text: text,
      role: opts.role || "status",
    });
    if (opts.ariaLive) el.setAttribute("aria-live", opts.ariaLive);
    if (opts.pulse) el.setAttribute("data-pulse", "true");
    return el;
  }

  // ── 2. EmptyState 空状态 ───────────────────────────────────
  /**
   * @param {string} action — 下一步动作描述
   * @param {string} [hint] — 补充说明
   * @returns {HTMLDivElement}
   */
  function EmptyState(action, hint) {
    const wrap = createEl("div", "empty-state");
    const actionEl = createEl("div", "", { text: action });
    wrap.appendChild(actionEl);
    if (hint) {
      const hintEl = createEl("small", "", { text: hint });
      hintEl.style.display = "block";
      hintEl.style.marginTop = "6px";
      hintEl.style.color = "var(--neutral-muted-soft)";
      hintEl.style.fontSize = "12px";
      wrap.appendChild(hintEl);
    }
    return wrap;
  }

  // ── 3. LoadingGuard 加载守卫 ───────────────────────────────
  /**
   * 管理一个目标容器的加载/空/错误状态。
   * @param {string} targetId — 目标容器 ID
   * @param {"idle"|"loading"|"empty"|"error"} state
   * @param {{message?: string, errorMessage?: string, emptyAction?: string, emptyHint?: string}} [opts]
   */
  function LoadingGuard(targetId, state, opts) {
    opts = opts || {};
    const target = document.getElementById(targetId);
    if (!target) return;

    // 清除旧的守卫层
    const oldGuard = target.querySelector(".loading-guard-layer");
    if (oldGuard) oldGuard.remove();

    if (state === "loading") {
      const layer = createEl("div", "loading-guard-layer loading-guard-loading", {
        role: "status",
        "aria-live": "polite",
      });
      const spinner = createEl("div", "loading-guard-spinner");
      const msg = createEl("span", "", {
        text: opts.message || "加载中…",
      });
      layer.appendChild(spinner);
      layer.appendChild(msg);
      target.style.position = "relative";
      target.appendChild(layer);
    } else if (state === "empty") {
      const layer = createEl("div", "loading-guard-layer", {
        role: "status",
        "aria-live": "polite",
      });
      layer.appendChild(EmptyState(
        opts.emptyAction || "暂无数据",
        opts.emptyHint || ""
      ));
      target.appendChild(layer);
    } else if (state === "error") {
      const layer = createEl("div", "loading-guard-layer loading-guard-error", {
        role: "alert",
      });
      layer.appendChild(StatusBadge("danger", opts.errorMessage || "加载失败"));
      target.appendChild(layer);
    }
    // idle 状态：什么都不显示
  }

  // ── 4. ExportButton 导出按钮 ────────────────────────────────
  /**
   * 带条件绑定的导出按钮，条件变更时自动失效。
   * @param {{
   *   label: string,
   *   disabled?: boolean,
   *   variant?: "primary"|"secondary",
   *   onClick?: (e: Event) => void,
   *   queryHash?: string,
   *   ariaLabel?: string,
   * }} config
   * @returns {HTMLButtonElement}
   */
  function ExportButton(config) {
    const btn = createEl("button", config.variant === "primary" ? "primary" : "secondary", {
      text: config.label,
      type: "button",
    });
    _setupExportButton(btn, config);
    return btn;
  }

  /**
   * 给已有的 DOM 按钮绑定 ExportButton 行为（条件绑定 + 状态反馈）。
   * 不改变按钮外观和原有 click 事件，只增加 hash 校验和禁用提示。
   * @param {string|HTMLButtonElement} target — 按钮元素或其 ID
   * @param {{
   *   getHash?: () => string,    // 返回当前查询条件的 hash
   *   onInvalid?: string,       // 条件失效时的 tooltip 文案
   * }} config
   */
  function attachExportButton(target, config) {
    const btn = typeof target === "string" ? document.getElementById(target) : target;
    if (!btn || btn.tagName !== "BUTTON") return;
    config = config || {};
    _setupExportButton(btn, {
      disabled: btn.disabled,
      queryHash: btn.getAttribute("data-query-hash") || "",
    });
    btn._banboosExportConfig = config;
  }

  function _setupExportButton(btn, config) {
    if (config.disabled) btn.disabled = true;
    if (config.ariaLabel) btn.setAttribute("aria-label", config.ariaLabel);
    if (config.queryHash) btn.setAttribute("data-query-hash", config.queryHash);
    if (config.onClick) btn.addEventListener("click", config.onClick);

    // 检查绑定的 queryHash 是否匹配，不匹配则禁用
    btn._banboosCheckHash = function (currentHash) {
      const bound = btn.getAttribute("data-query-hash");
      if (bound && currentHash && bound !== currentHash) {
        btn.disabled = true;
        btn.title = btn._banboosExportConfig?.onInvalid || "查询条件已变更，请重新加载后导出";
      }
    };

    // 更新绑定的 hash 并启用按钮
    btn._banboosBindHash = function (hash) {
      btn.setAttribute("data-query-hash", hash);
      btn.disabled = false;
      btn.title = "";
    };
  }

  // ── 导出到全局 ─────────────────────────────────────────────
  global.BanboosUI = {
    StatusBadge: StatusBadge,
    EmptyState: EmptyState,
    LoadingGuard: LoadingGuard,
    ExportButton: ExportButton,
  };
})(window);
