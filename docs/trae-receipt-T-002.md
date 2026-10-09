# T-002 多来源冲突复核与重复登记审计交付回执

## 完成清单

- [x] 22 条 `multiple_source` 支持列表、详情、临时 Canonical、候选 source row、payload hash、选择规则、证据 ID 和审计状态。
- [x] 复核状态覆盖 `pending/manual_review_required`、`approved`、`rejected`、`deferred`；复核只追加到独立 sidecar，不改写原始/staging/canonical。
- [x] 复核请求要求已验证会话操作者、非空 decision reason、evidence_id、expected_revision 和幂等键；重复请求幂等，版本过期、证据变化、幂等键复用均返回结构化 409。
- [x] 清洗副本 9188 条重复登记提供只读摘要和按节点、市场、日期、来源过滤；记录 kept/source/removed row、payload hashes、source files、same_payload 和 decision_reason。
- [x] Web 节点分析页提供冲突队列、证据详情、Canonical 风险和确认/退回动作；不会把人工复核显示为自动完成。
- [x] rejected 与 no_canonical 分离：同日已有有效 Canonical 的无效候选标记 `rejected`，没有有效 Canonical 才标记 `no_canonical`。

## API

- `GET /api/v1/quality/conflicts`：默认筛选 `multiple_source`，支持 node/market/date/type/offset/limit。
- `GET /api/v1/quality/conflicts/{source_row_id}`：详情及候选证据。
- `POST /api/v1/quality/conflicts/{source_row_id}/review`：只写 sidecar 审计事件。
- `GET /api/v1/quality/duplicate-audit`：只读重复登记摘要/明细过滤。

## 绝对路径文件

- `E:\Banboos2.0\packages\contracts\price_conflicts.py`
- `E:\Banboos2.0\packages\application\price_conflict_review.py`
- `E:\Banboos2.0\packages\application\readonly_service.py`
- `E:\Banboos2.0\packages\infrastructure\staging_sqlite.py`
- `E:\Banboos2.0\packages\infrastructure\legacy_sqlite.py`
- `E:\Banboos2.0\packages\application\legacy_migration.py`
- `E:\Banboos2.0\apps\api\main.py`
- `E:\Banboos2.0\apps\web\app.js`
- `E:\Banboos2.0\apps\web\index.html`
- `E:\Banboos2.0\apps\web\styles.css`
- `E:\Banboos2.0\tests\unit\test_price_conflicts.py`
- `E:\Banboos2.0\tests\unit\test_price_conflict_review.py`
- `E:\Banboos2.0\tests\unit\test_legacy_reader.py`
- `E:\Banboos2.0\tests\contract\test_price_conflict_api.py`

## 验证输出

- `E:\Banboos2.0\.venv\Scripts\python.exe -m pytest -q` → `148 passed, 3 warnings`。
- `E:\Banboos2.0\.venv\Scripts\ruff.exe check packages tests` → `All checks passed!`。
- `node --check apps/web/app.js` → 通过。
- `git diff --check` → 通过（仅既有 CRLF 提示）。
- 真实旧 staging TestClient：`GET .../quality/conflicts?market=实时&limit=100` → `200`、22 条；详情 `200`、证据 ID 一致；合法 defer `200`；重复幂等 `200`；过期 revision `409`；空 reason `422`。
- 首次 smoke 失败原因：列表与详情使用不同数据集身份/候选集合计算 evidence_id，复核返回 `EVIDENCE_CHANGED`；已统一绑定 staging snapshot SHA-256 与完整候选 source row/payload hash，并复测通过。

## 数据统计与不变性

- `E:\Banboos2.0\var\migrations\legacy-full-20260923.sqlite3`：Raw `3946141`、Canonical `3936952`、`multiple_source` `22`。
- `E:\Banboos2.0\var\data-quality\legacy-price-clean-20261003.sqlite3`：`price_duplicate_registry` `9188`。
- 原始 SQLite 和生产只读 staging 未写入；本地测试 sidecar 使用临时目录，工作区未保留 smoke 审计库。

## 评审意见逐项回应

1. 旧 staging 无 `price_conflicts` 时从质量/raw/canonical 回退发现冲突；summary/aggregate 通过同一 Canonical 判断状态。
2. rejected/no_canonical 按同节点、日期、市场的 Canonical 实际存在性区分，并有回归测试。
3. sidecar 事件绑定 dataset snapshot、候选 payload hash 集合；重复、过期和证据变更均有测试。
4. Web 只提交当前已验证会话的 `dev-user`/`token-owner`，普通未授权请求由 API guard 拒绝；不信任前端自填审核人。

## 遗留风险与建议

复核批准仍是审计状态，`applied=false`，不会自动替换 Canonical；正式业务发布需另行审批。建议 **ACCEPT**。
