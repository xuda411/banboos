# 原版 XLSM 模板导出

Banboos 2.0 现在支持在财务任务完成后导出 1.6.6 原版模板的副本：

```text
GET /api/v1/runs/{run_id}/export?format=xlsm
```

服务启动前设置 `BANBOOS2_FINANCIAL_TEMPLATE` 为模板文件路径，例如：

```powershell
$env:BANBOOS2_FINANCIAL_TEMPLATE = 'E:\Banboos2.0\var\templates\独立储能项目经济性测算工具.xlsm'
```

模板必须是 `.xlsm`。导出流程先复制模板，再写入原版财务链路实际读取的输入单元格；不会覆盖源文件。若源文件包含 VBA 工程，导出会保留该工程；当前 1.6.6 模板副本实际未包含 `vbaProject.bin`。输出文件会增加 `Banboos2.0快照`、`原版对账` 和 `输入映射记录` 工作表，分别记录任务追溯、已知公式差异和每个被覆盖的单元格。

模板中金额输入沿用原表的“万元”单位，服务器结果仍以“元”保存；电能量、容量和辅助服务收入分别进入 D51、容量类/参数设定和辅助服务类的收入链路。服务器没有详细电价、调频里程和 EPC 分项时会清零模板示例值，并把年度聚合收入覆盖到对应收入节点，避免示例数据混入结果。模板的原生公式、数据表和数组公式需要用 Excel/WPS 打开并保存后重算，服务器无法在没有 Office 计算引擎的环境中替代这一步。`原版对账` 会明确标出当前规则差异，不能把缓存值或公式文本当作等价证明。服务器侧权威结果仍以同一任务的标准 XLSX 导出和 `重算复核` 页为准。

`format=xlsx` 仍是默认导出格式；未配置模板时请求 `format=xlsm` 会返回 503，并提示配置项。

财务任务完成后还可调用 `GET /api/v1/runs/{run_id}/financial-template-reconciliation`。服务会生成临时模板副本，读取 D3/D4/D22/D24、财务指标年度现金流、IRR/NPV 等关键单元格的缓存值，并与同一任务的服务器快照逐项比较；临时文件自动清理。报告会区分 `MATCH`、`DIFFERENCE` 和 `PENDING`，其中 `PENDING` 表示需要用 Excel/WPS 打开并保存后再复核，不会被误报为通过。
