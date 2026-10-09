# T-001 数据清洗多来源冲突修复回执

## 验收

- [x] 原始快照/生产数据不变：新增 `price_conflicts` 隔离表，仅写入 staging；每条冲突保留 source row、source file、payload SHA-256、canonical row、选择规则和处理状态。
- [x] identical duplicate、multiple_source、rejected、无 Canonical 记录四类隔离测试已加入 `tests/unit/test_price_conflicts.py`。
- [x] `/api/v1/price/summary`、`/api/v1/quality/summary`、`/api/v1/price/aggregates` 返回 `data_status`、冲突数和人工复核标记；冲突不会抛未捕获通用错误。
- [x] 节点概览/曲线页面显示冲突数量、人工复核动作或 Canonical 缺失动作。
- [x] 全量 pytest、ruff、node --check、git diff --check 已通过。

## 文件

- `E:\Banboos2.0\packages\application\legacy_migration.py`
- `E:\Banboos2.0\packages\infrastructure\staging_sqlite.py`
- `E:\Banboos2.0\packages\application\readonly_service.py`
- `E:\Banboos2.0\packages\contracts\readonly.py`
- `E:\Banboos2.0\apps\web\index.html`
- `E:\Banboos2.0\apps\web\app.js`
- `E:\Banboos2.0\tests\unit\test_price_conflicts.py`

## 验证输出

- `E:\Banboos2.0\.venv\Scripts\python.exe -m pytest -q` → `142 passed, 3 warnings`。
- `E:\Banboos2.0\.venv\Scripts\ruff.exe check ...` → `All checks passed!`。
- `node --check apps/web/app.js` → exit code 0。
- `git diff --check` → exit code 0（仅 CRLF 转换提示）。

## 数据统计

生产只读 staging `E:\Banboos2.0\var\migrations\legacy-full-20260923.sqlite3`：staging_nodes `5409`、raw `3946141`、quality complete `3936952`、duplicate `9162`、multiple_source `22`、rejected `5`、canonical `3936952`。清洗副本 `E:\Banboos2.0\var\data-quality\legacy-price-clean-20261003.sqlite3`：price_data `3936953`、duplicate registry `9188`。节点目录 5409 与 API 可用 5372 的差异为 37 个目录节点没有任何 price_data 行；目录保留节点身份，API 仅暴露有价格记录的节点。

## 遗留风险与建议

`multiple_source` 保留最低 source row 作为临时 canonical 以维持曲线可读，但状态为 `manual_review_required`，不得视为业务确认。清洗副本中的 9188 条重复登记仍是历史审计数据，未删除或覆盖。

**建议：ACCEPT**（代码与隔离测试完成；22 条多来源冲突需业务人员后续复核）。
