# 1.6.6 XLSM 原生重算阶段报告

日期：2026-09-29  
工作目录：`E:\Banboos2.0`  
固定样本：60 MW / 120 MWh，25 年，贷款比例 70%，第 11 年换电池，输出增值税 13%。

## 已完成

1. 通过只读探测发现本机 Microsoft Excel：
   `C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE`。
2. 新增原生重算服务函数 `recalculate_xlsm`。它复制 XLSM 到临时目标，使用隐藏 Excel COM 执行 `CalculateFullRebuild()`，保存缓存后关闭 Excel；源模板不会被覆盖。
3. 财务模板复核 API 在引擎可用时自动执行上述重算；无引擎时保留静态缓存检查并明确返回 `native_recalculation_engine` 状态。
4. `desktop_template` 导出映射补齐了 EOL 的日历曲线、循环曲线、取小曲线和年度平均曲线；电量基数写入首年 EOL 后由模板年度 EOL 公式继续计算。
5. 新增 `scripts/compare_native_xlsm.py`，可对已重算的 XLSM 与任务快照重复生成 JSON 对账结果。
6. 新增显式 `eol_method=native_xlsm` 兼容模式。该模式按原版工作簿的折旧重置、末年残值、含税/不含税利润、税费和项目/资本金现金流公式计算；原有 `desktop_template` 模式继续保留 1.6.6 程序基线。

## 原生复核结果

机器文件：

- [重算后的 XLSM](../var/parity/20260929T074248Z-96d32f47/desktop-template-eol-test2.recalculated.xlsm)
- [重算命令结果](../var/parity/20260929T074248Z-96d32f47/native-recalc-eol2.json)
- [逐单元格复核](../var/parity/20260929T074248Z-96d32f47/native-reconciliation.json)
- [原版公式口径重算 XLSM](../var/parity/20260929T074248Z-96d32f47/native-xlsm-test.recalculated.xlsm)
- [原版公式口径逐单元格复核](../var/parity/20260929T074248Z-96d32f47/native-xlsm-reconciliation.json)

旧的 `desktop_template` 服务器结果与模板重算结果为 **279 项一致、81 项差异、0 项待重算**，差异来自两套历史财务口径。

切换到显式 `native_xlsm` 模式后，固定样本复核结果为 **360 项一致、0 项差异、0 项待重算**，包括 IRR、NPV、首年项目/资本金现金流、换电池年度折旧和全周期年度明细。

首年曲线已从原先的模板样本值修正为：

```text
服务器首年能量收益 = 年度收益 × first_year_eol × EOL!D9
```

固定样本的首年电量收益已与服务器结果一致（1,624.7970 万元）。`native_xlsm` 模式同时把模板第 11 年起的换电池折旧重置和末年残值纳入服务端计算。

## 下一轮修复清单

1. 将 `native_xlsm` 接入网页财务参数选择和导出任务快照，明确用户选择的财务口径。
2. 完成模板宏、数据表、数组公式在 Excel 和 WPS 的交叉打开检查，并保留引擎、版本和文件哈希。
3. 为两种财务口径分别生成产品文档和验收样本，避免把程序基线与原版表格公式混用。

`desktop_template` 程序基线仍保留其历史差异并在报告中标记；`native_xlsm` 固定样本已通过 Excel 原生复核。跨引擎复核完成前，发布门禁仍不把 XLSM 结果扩展为 WPS 等价证明，生产控制功能也不进入上线验收。

当前机器只检测到 Excel，未检测到 WPS 或 LibreOffice；因此本轮“跨引擎”仍是待执行项，不能把 Excel 单引擎结果扩展为 WPS 等价证明。
