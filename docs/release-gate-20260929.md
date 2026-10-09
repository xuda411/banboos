# 1.6.6 财务 XLSM 发布门禁报告

日期：2026-09-29  
工作目录：`E:\Banboos2.0`  
固定样本：60 MW / 120 MWh，原版公式口径 `native_xlsm`。

本轮把原版模板导出验收整理为可重复的发布门禁：模板结构和样式保留、原生 Excel 重算、缓存值逐单元格对账、宏/数据表/数组公式特征检查，以及跨引擎可用性分别出具状态。门禁不会因为检测不到 WPS 或 LibreOffice 而把 Excel 单引擎结果伪装成跨引擎通过。

## 当前结果

门禁状态：**PENDING_CROSS_ENGINE**。

| 检查项 | 状态 | 结果 |
|---|---|---|
| 模板结构、样式和声明变更 | PASS | `PRESERVED_WITH_DECLARED_CHANGES`，0 个未声明变更，0 个样式变更，0 个结构变更 |
| Excel 原生重算 | PASS | Microsoft Excel COM，`CalculateFullRebuild()` |
| 原版公式缓存值对账 | PASS | 360 项一致，0 项差异，0 项待重算 |
| 宏/数据表/数组公式/外部链接检查 | PASS | 3 个定义名称、3106 个公式、2 个数组公式；当前模板无宏、数据表、外部链接和连接 |
| WPS/LibreOffice 交叉引擎 | PENDING | 当前主机未安装 WPS 或 LibreOffice |

因此当前导出链路已经通过 Excel 原生验收，但发布门禁仍等待至少一个替代引擎完成同一文件的打开、重算和缓存对账。该状态是交付前的明确待办，不影响继续使用 Excel 复核文件。

## 证据文件

- [门禁 JSON](../var/parity/20260929T074248Z-96d32f47/release-gate.json)
- [原生重算 XLSM](../var/parity/20260929T074248Z-96d32f47/release-gate-recalculated.xlsm)
- [待验收 XLSM](../var/parity/20260929T074248Z-96d32f47/native-xlsm-test.xlsm)
- [任务输入快照](../var/parity/20260929T074248Z-96d32f47/native-xlsm-input.json)

## 重复执行

```powershell
Set-Location E:\Banboos2.0
\.venv\Scripts\python.exe scripts\financial_release_gate.py `
  var\templates\独立储能项目经济性测算工具.xlsm `
  var\parity\20260929T074248Z-96d32f47\native-xlsm-test.xlsm `
  --result-json var\parity\20260929T074248Z-96d32f47\native-xlsm-input.json `
  --output var\parity\20260929T074248Z-96d32f47\release-gate.json
```

返回码 `0` 表示 `RELEASE_READY`，返回码 `2` 表示仅剩替代引擎待验收，返回码 `1` 表示模板保留、原生重算或数值对账存在失败。源模板始终只读，重算输出写入独立文件。

## 下一步

1. 在验收机安装 WPS 或 LibreOffice，使用同一 `native-xlsm-test.xlsm` 运行重算和 360 项对账。
2. 将引擎名称、版本、输出哈希和差异报告归档到本目录。
3. 门禁状态已经接入 `scripts/preflight_production.py`；生产环境必须设置 `BANBOOS2_FINANCIAL_RELEASE_GATE=RELEASE_READY`。
4. 交叉引擎通过后，把门禁结果写入该环境变量，再进入登录权限、真实数据和 EMS 只读接入的上线验收。
