# T-003 价格冲突复核与 RBAC 交付回执

日期：2026-10-09  
范围：旧 staging 冲突发现、只读复核、RBAC、租户隔离、应用意图门禁和 Web 状态。

## 已完成

- 从 immutable staging/cleaning 数据发现 `multiple_source` 冲突，并区分 `duplicate`、`multiple_source`、`no_canonical`。
- 生成包含候选来源 ID、payload hash、canonical 来源、selection rule 的稳定 `evidence_id`。
- 复核事件写入 sidecar SQLite append-only 表，记录 reviewer、tenant、request id、版本和理由；canonical SQLite 永不写入。
- 增加 `confirm_canonical`、`reject_candidate`、`defer`、`reopen` 的版本与幂等校验。
- 增加 `POST /api/v1/quality/conflicts/{source_row_id}/apply`，只创建 `pending_apply` intent，必须通过 approved、evidence、revision、tenant 和 RBAC 门禁，`applied=false`。
- GET 使用 `read` 权限；POST review/apply 使用 `maintain_data` 权限；未知角色 fail closed；服务端身份覆盖客户端 actor；租户不匹配返回 403。
- Web 显示审核状态、证据、应用状态和只读提示，明确提示不会改写 Canonical。

## 变更文件

- `apps/api/main.py`
- `apps/web/app.js`
- `apps/web/index.html`
- `apps/web/styles.css`
- `packages/contracts/price_conflicts.py`
- `packages/application/price_conflict_review.py`
- `packages/application/readonly_service.py`
- `packages/infrastructure/legacy_sqlite.py`
- `packages/infrastructure/staging_sqlite.py`
- `tests/contract/test_price_conflict_api.py`
- `tests/unit/test_price_conflict_review.py`
- `tests/unit/test_price_conflicts.py`

## 验证

- `pytest -q`：150 passed，3 warnings。
- `ruff check packages tests apps/api/main.py --fix`：通过。
- `node --check apps/web/app.js`：通过。
- `git diff --check`：通过；仅有既有 CRLF 提示。
- Impeccable detector 已运行；报告的是页面既有对比度、字号、栅格背景和边框阴影建议，未阻断本次功能交付。
- 真实数据 smoke：`legacy-price-clean-20261003.sqlite3` + `legacy-full-20260923.sqlite3`，GET 返回 `200`，实际冲突为 `multiple_source`；列表和详情 `evidence_id` 一致；operations_analyst 复核返回 `200 deferred`。
- contract tests 覆盖 finance/auditor 403、未知角色 fail closed、租户边界、无会话 401、apply `pending_apply/applied=false`、重复幂等和 forged actor。
- 原始数据库 `E:\Banboos2.0\var\migrations\legacy-full-20260923.sqlite3` 只读检查：大小 8,632,442,880 bytes，mtime 未被改变；临时 sidecar smoke 文件已清理。

## 结论

T-003 完成，建议 ACCEPT 并进入下一阶段。应用 worker 尚未接入实际 Canonical 写入，当前阶段只产生可审计的待应用意图。
