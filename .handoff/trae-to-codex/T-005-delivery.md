# 交付回执 T-005

- 任务：电价与气象图表键盘点位查看、焦点反馈统一、图表字体配置统一
- 执行者：Trae
- 指令书：`.handoff/codex-to-trae/T-005-directive.md`
- 代码基线：`481561f377d0719c6ed436c4c89525d6d38cc2c5`
- 指令提交：`9f5aeb972ff75add53d4843b8de2943f7df3f9ba`
- 实现提交：`7770e7312b2c0615c26a9c2a3978ca21609a7b41`
- 日期：2026-10-09

## 修改文件（均在白名单内）

| 文件 | 行号（修改后） | 内容 |
|---|---|---|
| `E:\Banboos2.0\apps\web\app.js` | L560-563 | 新增键盘游标与 live region 文本缓存状态 |
| | L630-633 | drawCurves 空数据/全非有限值时清空 geometry 并隐藏旧提示 |
| | L690-754 | hideCurveHover/hideCurveKeyboard/presentCurvePoint/showCurveHover/onCurveChartKeydown |
| | L820-821 | loadCurves 开始即失效旧 geometry、键盘状态与提示 |
| | L825 | 加载成功重置键盘状态 |
| | L827 | 切换曲线日重置键盘状态 |
| | L840 | 加载失败 drawCurves([]) 并清空入口 |
| | L848-850 | drawWeather 空序列清空 geometry 并隐藏旧提示 |
| | L855、L1076 | 两处字体统一为 `font.sizeAxis` + `font.family` |
| | L859-904 | hideWeatherHover/hideWeatherKeyboard/presentWeatherPoint/showWeatherHover/onWeatherChartKeydown |
| | L919 | 气象加载成功隐藏旧提示并重置键盘状态 |
| | L921 | 气象加载失败 drawWeather([]) 并清空入口 |
| | L1536-1537、L1554-1555 | keydown/blur 事件注册（监听挂在 canvas，无全局拦截）|
| `E:\Banboos2.0\apps\web\index.html` | L96、L108 | 两个 aria-describedby 提示追加键盘说明；另修复一处历史遗留的字面量 `` `n ``（script 标签间） |
| `E:\Banboos2.0\apps\web\styles.css` | L239-240 | dispatch canvas 纳入焦点轮廓；新增 `a[href]:focus-visible`（复用既有 token，未新增色值） |

只读参考文件（chart-config.js、ui-components.js、report-ui.js）未修改。`apps/api/`、`packages/`、`legacy/`、1.6.6 文件零改动，未新增依赖。

## 验收标准逐项证据

### A1 字体配置 — PASS
- app.js 全文搜索完整字面量 `11px Microsoft YaHei`：**0 命中**（实测 Select-String）。
- L855、L1076 均为 `` context.font = `${window.BanboosChartConfig.font.sizeAxis} ${window.BanboosChartConfig.font.family}`; ``
- 未改配置值、序列、单位、业务计算。

### A2 电价键盘查看 — PASS（真实浏览器实测）
fixture：2 条 96 点曲线，第 0 天 prices[10]=null，源标记 `fixture-validation-only`。实测（合成 KeyboardEvent，真实焦点）：
- 首次 ArrowRight：`00:15（第 1/96 点） 电价：300.00 元/MWh`，含节点/日期/市场/来源（节点无 select 选项时回退 `节点 NODE-T-001`，与鼠标同一展示路径）。
- 第 11 点（null）：`电价：—（暂无数据）`，不显示 0.00。
- Home：第 1/96；End：`00:00（第 96/96 点） 339.65`；End 后 Left：`23:45（第 95/96 点） 331.34`。
- 连按 200 次 Left/Right：稳定停在第 1/96 与第 96/96，不越界。
- Escape 与 blur：#curveHover hidden=true 且文本清空。
- 鼠标 mousemove（绘图区 50%/40%）：`11:45（第 47/96 点） 338.66 元/MWh`，保持可用。
- 连续 10 次方向键期间新增 /api 请求数 = **0**（performance resource 计数差）。
- 切换曲线日重置键盘游标；加载失败后 geometry.curves.length=0，再按方向键提示不出现（见 lifecycle）。

### A3 气象键盘查看 — PASS
fixture 三点序列（正常值 / 全 0 / 全 null）：
- 首点 Right：`2026-01-01 辐照度：245.6 W/m² 风速：3.2 m/s 光伏 12.34 MW 风电 5.67 MW`，单位保持。
- End（null 行）：四项均 `—`，无 NaN、无 0。
- Home 回首点；第二点真实零值正确显示 `0.0 / 0.00`（零与缺失区分）。
- 单点序列 drawWeather([r0])：End 显示首点，不抛错。
- 零序列 drawWeather([])：#weatherHover hidden=true，方向键无内容、无异常。
- 导航基于 `geometry.series.length`，未假设 96 点；未改聚合与功率估算。

### A4 描述与生命周期 — PASS
- `#curveChart`、`#weatherChart` 的 aria-describedby 分别指向 `#curveChartHint`/`#weatherChartHint`，提示文本含"←/→ 逐点查看，Home/End 跳转首末点，Esc 关闭提示"。
- 复用既有 #curveHover/#weatherHover（role=status, aria-live=polite）；同一点重复按键 innerHTML 不重写（缓存比对），内容变化才更新；隐藏时清空文本。
- Tab/Shift+Tab 真实按键：canvas → 下一可聚焦元素（fixture 状态为 powerMw，outline 3px）→ Shift+Tab 回到 curveChart（outline 3px）。
- 三个 canvas 的 role=img、aria-label、tabindex=0 保留；无正数 tabindex；方向键监听只挂 canvas 并仅拦截已处理键，无全局拦截。
- 生命周期：loadCurves 开始即置 `_curveGeometry={curves:[]}` 并隐藏提示；失败（实测请求 127.0.0.1:8000 连接失败）后 `geomCurves=0`、hoverHidden=true，聚焦按方向键仍 hidden。气象开始/空/失败同构处理（`_weatherGeometry={series:[]}`、成功/失败均隐藏旧提示）。

### A5 焦点可见 — PASS
getComputedStyle 实测（keyboard modality）：

| 目标 | outline |
|---|---|
| #curveChart | 3px / solid |
| #loadCurves 按钮 | 3px / solid |
| #curveStart 输入 | 3px / solid |
| #curveNode 下拉 | 3px / solid |
| #downloadReport 链接（fixture 赋 href） | 3px / solid |
| #dispatchChart（fixture 展开隐藏容器） | 3px / solid |

- 仅用既有 `rgba(var(--brand-bamboo-rgb), …)`，未新增色值；未全局移除 outline。
- 1440×900：键盘浮层在绘图区内（tooltipInPlot=true，left=56 / rightMargin=674 / top=24）。
- 390 宽度模拟：canvas 实测宽 210px，轮廓 3px，浮层 left/right/top 均在界内（hoverRightOK / hoverLeftOK / hoverTopOK 均 true）。
- **测试条件声明**：下载链接仅在任务完成后由应用赋 blob href，本次以 fixture href 验证；调度 canvas 位于隐藏结果区，验证时临时展开容器。390 宽度为 `main.page` 容器约束模拟（自动化工具无法真实调整浏览器视口），非真实设备视口读数。

### A6 回归与边界 — PASS
- `node --check E:\Banboos2.0\apps\web\app.js` → exit 0（Node v24.20.0，为满足本条验收在本机安装；未改前端依赖清单，项目无 package.json）。
- `git -C E:\Banboos2.0 diff --check`（基线对比）→ exit 0。
- 真实 Chromium 执行 A2–A5，控制台 11 条：9 条 net::ERR_CONNECTION_REFUSED（无后端环境，预期：auth/health/meta/nodes/readyz/runs/price 接口）；2 条 SyntaxError 为更早人工试跑脚本在浏览器上下文日志中的残留，console.clear() 与新页面后未再复现，harness 自身 errors=[]。
- LoadingGuard、ReportUI epoch/hash 保护未触碰；键盘导航不产生 API 请求（实测差值 0）。
- 改动仅落在 3 个白名单文件 + 本轮交付/证据/STATE 文件。验证用临时脚本 `apps/web/_t005_harness.js` 已删除，未入库、未进提交。

## 浏览器与 fixture 条件

- 静态服务：`python -m http.server 8765`（仅 apps/web），无后端；API 失败属预期。
- fixture 仅用于验证，通过页面内脚本注入（曲线 2 日含 null、气象 3 行含 0/null/单点/空序列），未写入应用默认数据、数据库或业务代码，未修改任何源文件。
- 证据截图（`.handoff/evidence/T-005/`）：curve-keyboard-1440.png（96 点游标+浮层）、focus-ring-1440.png（焦点轮廓）、mobile-390.png（390 容器模拟）。
- 未做真实屏幕阅读器（NVDA/VoiceOver）播报验收，仅验证 DOM/aria 与 live region 文本，如实声明。

## 未完成项与风险

1. **未做真实屏幕阅读器实测**；aria 属性与 live region 已就位，建议后续人工用 NVDA 复核。
2. **390 为容器模拟而非真实视口**；建议有条件时用设备模式/真机补一次。
3. **观测（非本轮范围，供 Codex 决策）**：drawWeather 的折线绘制 `Number(row[key])` 对 null 同样按 0 参与连线（既有行为）；本轮按指令只修了点位文本的 null 展示，未改曲线绘制路径。
4. 浏览器工具上下文日志中残留 2 条早期 SyntaxError，非当前代码产生（页面无 JS 异常，harness errors=[]）。
