# 原版 XLSM 模板导出

Banboos 2.0 现在支持在财务任务完成后导出 1.6.6 原版模板的副本：

```text
GET /api/v1/runs/{run_id}/export?format=xlsm
```

服务启动前设置 `BANBOOS2_FINANCIAL_TEMPLATE` 为模板文件路径，例如：

```powershell
$env:BANBOOS2_FINANCIAL_TEMPLATE = 'E:\Banboos2.0\var\templates\独立储能项目经济性测算工具.xlsm'
```

模板必须是 `.xlsm`。导出流程先复制模板，再写入 `参数设定` 工作表的输入单元格；不会覆盖源文件。输出文件会保留宏工程，并增加 `Banboos2.0快照` 工作表记录任务 ID、模型版本、功率容量和服务器侧财务指标。

模板中金额输入沿用原表的“万元”单位，服务器结果仍以“元”保存；电能量、容量和辅助服务收入分别写入 D51、D50、D52。模板的原生公式、数据表和宏需要用 Excel/WPS 打开并保存后重算，服务器无法在没有 Office 计算引擎的环境中替代这一步。服务器侧权威结果仍以同一任务的标准 XLSX 导出和 `重算复核` 页为准。

`format=xlsx` 仍是默认导出格式；未配置模板时请求 `format=xlsm` 会返回 503，并提示配置项。
