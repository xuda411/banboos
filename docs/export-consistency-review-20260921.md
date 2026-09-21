# Banboos 2.0 Excel 导出与 1.6.6 模板复核

复核日期：2026-09-21  
复核环境：E 盘 Banboos2.0，真实 staging 只读库 + 1.6.6 原版 XLSM 模板

## 本次修正

- 所有服务器端 XLSX 都写入 `导出格式版本 = banboos-export-2026-09-21`、来源模式、统计范围和业务口径。
- 新增节点价差月度/年度统计 Excel：同时保留有效日、窗口均价、价差、重复来源日和缺失日期。
- 新增运营站点层级汇总 Excel：分省份和月份输出节点数、有效节点、有效日、数据点和加权平均价差。
- 新增真实节点候选项目 Excel：保留快照 ID、算法版本、节点来源、年净现金流，并增加容量/功率时长校验。
- 组合优化 Excel 增加“组合复核”页，集中呈现预算、目标、折现率、运营年限、选中数量、总投资、NPV、IRR 和结果状态。
- 财务结构化 XLSX 新增“导出说明”页，保留“财务模板、模板复核、重算复核、模板映射、公式复核”等原有复核页。
- 原版 XLSM 仍以 1.6.6 模板为母版写入，核心工作表和输入单元格映射不改版；服务器不会执行原版宏，需用 Excel/WPS 打开后重算。
- 前端新增三类 Excel 下载入口，日期、市场、窗口等条件变更后会先禁用下载，重新加载后再导出，避免下载内容与当前页面不一致。

## 实际验证

下列文件由当前运行服务和真实 staging 数据生成：

- [price-aggregates-check.xlsx](../var/exports/price-aggregates-check.xlsx)
- [operations-check.xlsx](../var/exports/operations-check.xlsx)
- [portfolio-check.xlsx](../var/exports/portfolio-check.xlsx)
- [financial-check.xlsx](../var/exports/financial-check.xlsx)
- [financial-check.xlsm](../var/exports/financial-check.xlsm)

自动审计结果：

- 5 类导出均可被 Excel 工作簿解析，工作表存在且有数据。
- 所有新增 XLSX 均有统一导出版本、冻结窗格、自动筛选和打印区域。
- 财务 XLSX 的模板复现公式、关键复核页和年度现金流保留。
- 原版 XLSM 的 `参数设定 `、`容量类`、`电量类 `、`辅助服务类`、`EOL`、`财务指标` 工作表保留，输入映射单元格存在。
- 机器审计：0 个失败、0 个警告。原始 JSON 见 [excel-export-audit-20260921.json](../var/migrations/excel-export-audit-20260921.json)。

## 口径边界

Excel 导出只负责呈现已完成任务或已加载查询的结果快照，不会在导出时悄悄替换数据源。财务 XLSX 的公式可在 Excel 中重算；XLSM 的宏和 Excel 专属缓存仍需在 Excel/WPS 中打开并保存后复核，服务器端不会把“未重算”标成公式一致。

## 质量门禁

本次代码变更通过：

- `pytest -q`：105 passed，2 个依赖弃用提示。
- `ruff check packages apps tests scripts`：通过。
- `node --check apps/web/app.js`：通过。
- `node --check apps/web/report-ui.js`：通过。
