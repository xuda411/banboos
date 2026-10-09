# 指令书 T-005

- 目标：补齐电价与气象图表的键盘点位查看能力，统一焦点反馈和两处图表字体配置，保持业务结果及请求契约不变。
- 规模：M
- 优先级：P1
- 发布者：Codex（规划者 / 评审者）；执行者：真实 Trae 工具。
- 基线：`481561f377d0719c6ed436c4c89525d6d38cc2c5`（代码）；开工前 pull 最新 main 并确认 STATE 为 T-005 / WAITING_TRAE。
- 涉及文件（业务文件写入白名单，仅以下三项）：
  - `E:\Banboos2.0\apps\web\app.js`
  - `E:\Banboos2.0\apps\web\index.html`
  - `E:\Banboos2.0\apps\web\styles.css`
- 只读参考：`E:\Banboos2.0\apps\web\modules\chart-config.js`、`E:\Banboos2.0\apps\web\modules\ui-components.js`、`E:\Banboos2.0\apps\web\report-ui.js`。
- 交付文件：`E:\Banboos2.0\.handoff\trae-to-codex\T-005-delivery.md`；状态文件：`E:\Banboos2.0\.handoff\STATE.md`。必要截图或浏览器验证记录只放 `E:\Banboos2.0\.handoff\evidence\T-005\`。

## 已核实的现状

以下行号均对应上述基线，交付时请提供修改后的行号。

- `E:\Banboos2.0\apps\web\index.html:96`、`:102`、`:108` 的三个主要 canvas 已有 `role="img"`、名称和 `tabindex="0"`，不重复添加。
- `E:\Banboos2.0\apps\web\app.js:1444`、`:1460` 只给电价、气象图表注册了鼠标悬浮；对应点位信息读取位于 `:690` 和 `:814`，没有键盘入口。
- `E:\Banboos2.0\apps\web\styles.css:238`、`:239` 的显式焦点样式未覆盖下载链接和调度 canvas，现有半透明轮廓需验证可见性。
- `E:\Banboos2.0\apps\web\app.js:808`、`:986` 残留完整的 `11px Microsoft YaHei` 字面量。配置字段已存在于 `E:\Banboos2.0\apps\web\modules\chart-config.js:10`。
- `E:\Banboos2.0\apps\web\app.js:626`、`:802` 在空数据时提前返回，而 geometry 缓存可能保留；本轮新增键盘入口不能读取上一轮数据。

## 验收标准（逐项交付证据，共 6 条）

- [ ] **A1 字体配置**：上述两处字体赋值同时引用 `BanboosChartConfig.font.sizeAxis` 和 `.family`；在 `E:\Banboos2.0\apps\web\app.js` 搜索完整字面量 `11px Microsoft YaHei` 为零命中。不得修改配置值、图表序列、单位或业务计算。
- [ ] **A2 电价键盘查看**：图表获得焦点后，首次方向键进入首个点位，之后 Left/Right 每次移动一个点位，Home/End 到首/末点位；96 点边界不越界。文本包含与鼠标相同的当前曲线日期、时点、市场、来源和电价，沿用已有时间及数值格式。切换日期后读取新曲线；空值显示“—”或“暂无数据”，不可因数值转换显示为 0。鼠标查看保持可用。
- [ ] **A3 气象键盘查看**：同样支持 Left/Right/Home/End，基于当前已展示的聚合序列长度导航，不假设 96 点；文本保持时间、辐照度、风速、预计光伏/风电功率及原单位。分别验证 0、1、多点及包含 null 的序列，不能越界、抛错、产生 NaN 或把缺失值显示为 0；不修改聚合算法或功率估算。
- [ ] **A4 描述与生命周期**：电价、气象图表各有可通过 `aria-describedby` 找到的键盘操作说明；复用现有 `curveHover` / `weatherHover` 的 polite 状态区域呈现当前点位，避免同一点反复重写播报文本。Escape/失焦关闭提示并清除游标，Tab/Shift+Tab 正常离开；开始重新加载、空结果或请求失败后，键盘与鼠标入口均不能重新显示旧数据。保留三个 canvas 的有效名称、角色，禁止全局拦截方向键或使用正数 tabindex。
- [ ] **A5 焦点可见**：三个 canvas、可见的 `a[href]` 下载链接、按钮及表单控件在键盘聚焦时均有清晰的 `:focus-visible` 轮廓；使用已有 token，不新增色值、不全局移除 outline。真实浏览器验证 Tab/Shift+Tab 顺序及焦点不被裁切，在 1440×900、390×844 两种视口记录结果；若下载链接需 fixture 显示，明确标注测试条件。
- [ ] **A6 回归与边界**：`node --check E:\Banboos2.0\apps\web\app.js` 与 `git -C E:\Banboos2.0 diff --check` 均退出 0；真实浏览器执行 A2–A5 并记录步骤、断言、控制台错误及结果。核对 LoadingGuard、原有导出禁用/参数失效保护未被移除，键盘导航不额外发送 API 请求。相对基线的改动只能落在本指令白名单及本轮交付/证据/STATE 文件；红线目录和依赖清单差异为零。

## 技术约束

- 必须使用：原生 HTML / JS / CSS、现有 `BanboosChartConfig`、现有图表绘制与点位提示结构。将鼠标和键盘的点位展示复用到同一路径，避免两套数值格式长期分叉。
- 允许的 JS 改动仅限字体赋值、点位展示/键盘事件、图表 UI 缓存和提示失效处理；null 的展示判断属于本轮显示修复。不得改过滤、聚合、均值、收益、LP、财务、API payload 或轮询算法。
- 本轮调度图表只补焦点反馈和字体配置，不新增调度点位浏览功能。
- 禁止修改 `E:\Banboos2.0\apps\api\`、`E:\Banboos2.0\packages\`、`E:\Banboos2.0\legacy\`、任何 1.6.6 相关文件；禁止新增前端依赖、构建工具、网络字体或框架；禁止大范围格式化 `app.js` / `index.html`。
- 不改“今日要事”、登录流程、业务数值或导出报表实现；这些不是本轮任务。
- 浏览器 fixture/请求拦截只用于验证，应与真实接口结果明确区分，不写入应用默认数据、数据库或业务代码。无可用浏览器时如实写“未验证”，不得仅凭静态检查声称通过。
- 开工先读 `E:\Banboos2.0\AGENTS.md` 及其中要求的开发约束。代码新增注释使用英文；交接文档使用中文。

## 推荐验证顺序

1. 先记录基线及工作区状态，在已有静态页面与可用 API 环境核对目标图表。
2. 依次验证正常数据、首尾边界、单点/空值、切换日期/重载、失败后不可读取旧值。
3. 在浏览器检查 DOM 名称/描述、当前 live region 文本、活动元素、键盘焦点样式、网络请求数及控制台；这不等同于已通过真实屏幕阅读器验收，未做的项目须声明。
4. 运行语法及差异检查；检查最终文件清单后写交付回执。无需运行或修改后端测试来凑数。

## 交接动作

1. Trae 先 pull，读取 `E:\Banboos2.0\.handoff\STATE.md`；确认当前轮次和执行权后，一句话回读目标再实现。不可自行编写下一指令书或评审。
2. 写 `E:\Banboos2.0\.handoff\trae-to-codex\T-005-delivery.md`：逐项列出 A1–A6、修改文件绝对路径与行号、基线与实现 commit、自测命令/退出码/输出摘要、浏览器与 fixture 条件、未完成项及风险。可先单独提交实现，再在交付提交中引用实现 SHA，避免自引用最终提交号。
3. 更新 STATE：当前轮次 T-005、当前轮到 CODEX、状态 WAITING_REVIEW、更新者 TRAE、实际更新时间、连续 REVISE 计数保持不变。Trae 不得写 ACCEPT。
4. 按白名单逐文件暂存并检查暂存区，commit 后 push 到 origin/main。不使用 `git add -A`；现有 `E:\Banboos2.0\.handoff\scripts\handoff-sync.ps1` 的 push 分支会暂存整个工作区，本轮不用它提交。失败时保留现场，禁止 force push、reset --hard 或自动 stash 他人改动。
5. Codex 收到 WAITING_REVIEW 后 pull，逐个打开实际改动文件核查 A1–A6，再写 `E:\Banboos2.0\.handoff\review\T-005-review.md`。ACCEPT 后如有 P0/P1 待办，同一提交发布 T-006 并把 STATE 交给 TRAE；连续两轮 REVISE 后仍不通过则 BLOCKED。

## 下一轮预告（不是本轮执行授权）

T-006 候选为“今日要事”绑定当前会话的真实前端加载/任务状态。现有静态“运营数据已接入”不能代表 API 或数据已接入；下一轮必须区分初始、加载、成功、空数据和失败，沿用现有接口与任务结果，不新增业务计算。具体白名单及验收标准由 Codex 在 T-005 ACCEPT 后下达。
