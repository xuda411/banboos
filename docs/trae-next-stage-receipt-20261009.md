# 下一阶段开发回执：冲突复核与重复登记审计

## 已完成

- 增加 `PriceConflictReviewStore` 侧车数据库，记录 `confirm_canonical`、`reject_candidate`、`defer` 决策与操作者、备注、时间；不修改原始快照、staging 或生产库。
- 新增 `GET /api/v1/quality/conflicts` 与 `POST /api/v1/quality/conflicts/{source_row_id}/review`，将 22 条 `multiple_source` 暴露为可复核队列。
- 新增 `GET /api/v1/quality/duplicate-audit`，只读读取清洗副本 `price_duplicate_registry`，保留 9188 条登记的来源和处置理由。
- 节点分析页面增加来源冲突队列，可确认 Canonical 或退回候选来源；复核结果写入隔离审计副本。

## 验证

- `E:\Banboos2.0\.venv\Scripts\python.exe -m pytest -q` → `143 passed, 3 warnings`。
- `E:\Banboos2.0\.venv\Scripts\ruff.exe check packages tests apps/api/main.py` → `All checks passed!`。
- `node --check apps/web/app.js` → 通过。
- `git diff --check` → 通过（仅既有 CRLF 提示）。

## 风险

复核决策目前是 sidecar 审计状态，不会自动改写 Canonical 曲线；正式业务采纳仍需人工确认和后续受控发布流程。
