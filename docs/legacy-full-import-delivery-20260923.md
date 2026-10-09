# 1.6.6 全量节点数据导入与交付前验证

验证日期：2026-09-23  
验证状态：**通过（staging-readonly）**

## 导入范围

- 源库：`E:\晔旭辉能源测算工具\price_analysis_system\data\price_analysis.db`
- 源库 SHA-256：`3e775a48eb1506f7fa7e65f0faedcc117160f1fa03c65e45d88699e2cbd533dd`
- 只读快照：`var/legacy-snapshots/20260916-024117-b245f40d/manifest.json`
- 2.0 staging：`var/migrations/legacy-full-20260923.sqlite3`
- 导入批次：`85d6877d-5e9b-44a9-aed0-9b6f485b9642`

原库和既有回放库未被改写。2.0 staging 使用 Raw、Quality、Canonical 三层结构，保留所有源行；曲线查询使用每个节点、日期、市场的最低源行号作为稳定代表。`日前`、`实时`是唯一市场类型，`OK`、`missing` 等历史检查值仅作为来源/质量信息保留。

## 数量对账

| 项目 | 1.6.6 源库 | 2.0 staging | 结果 |
| --- | ---: | ---: | --- |
| 节点总数 | 5,409 | 5,409 | 一致 |
| 有电价记录的节点 | 5,372 | 5,372 | 一致 |
| Raw/Quality 电价行 | 3,946,141 | 3,946,141 | 一致 |
| 完整有效行 | 3,946,136 | 3,946,136（`is_complete=1`） | 一致 |
| Canonical 完整曲线 | 3,936,952 个键 | 3,936,952 | 一致 |
| 缺失点行 | 5 | 5（拒绝，不补值） | 一致 |

市场范围也逐项一致：实时 2,050,495 行、5,371 个节点，覆盖 2025-01-01 至 2026-09-30；日前 1,895,646 行、5,253 个节点，覆盖 2025-01-01 至 2026-08-31。Canonical 中实时 2,041,936 条、日前 1,895,016 条；重复源行按 `duplicate`/`multiple_source` 留在质量层。

## 交付前回归

在 `http://127.0.0.1:8012` 以 `BANBOOS2_STAGING_DB` 接入全量 staging，并以只读快照提供旧库管理信息：

- `/health`、`/readyz`：HTTP 200；`/api/v1/meta`：`staging-readonly`。
- 节点列表：5,372 个可查询节点（另有 37 个节点没有电价行，仍保存在 staging 节点目录）。
- 日前/实时价格范围、汇总和质量摘要：HTTP 200；质量样本完整率 100%。
- 2 小时、4 小时价差聚合：两类市场均 HTTP 200，滑动窗口均可计算。
- 价格明细导出、聚合导出：两类市场均 HTTP 200，返回有效 XLSX ZIP。
- `import-logs`、`field-mappings`、`province-investment`、`geo-mappings` 管理查询：HTTP 200，来源标记为 `legacy-readonly`。
- 启动门禁：`staging-ready`；生产控制：`disabled`。
- 26 条 Raw 行和 100 条 Canonical 曲线做逐点抽样，载荷、源行号和 96 点均值全部一致。

完整机器结果保存在 [legacy-full-20260923-report.json](../var/migrations/legacy-full-20260923-report.json)。

后续 Web 人工测试统一使用 E 盘全量数据，不再自动生成正向夹具：

```powershell
& .\scripts\start_full_database_check.ps1
```

该脚本将节点、电价、质量和聚合指向 `var/migrations/legacy-full-20260923.sqlite3`，将旧库管理信息指向经过审计的 `var/data-quality/legacy-price-clean-20261003.sqlite3`，财务模板指向 E 盘模板副本，并强制关闭 demo/fixture 回退。访问地址为 `http://127.0.0.1:5173/?apiPort=8012`。

启动后使用以下命令执行全量 Web 检查：

```powershell
& .\scripts\verify_full_database_check.ps1 `
  -Report E:\Banboos2.0\var\manual-check\full-database-test-20261003.json
```

本轮检查通过：API/就绪状态正常，节点接口返回 5,372 个有电价节点，抽取湖北、山西、广东节点分别验证日前/实时、2 小时/4 小时聚合、质量覆盖和两个 XLSX 导出接口。

## 交付边界

本次交付接入的是隔离 staging 只读库，未启用用户写入、实时 EMS 控制或生产数据库。原始数据库仍作为冻结基线；上线前还需按部署环境配置 PostgreSQL、Redis、短信/邮箱/微信身份服务及租户隔离，再将同一批次通过正式 ETL 导入生产数据库。
