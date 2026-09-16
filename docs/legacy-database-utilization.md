# 1.6.6 数据库利用与管理方案

## 定位

`E:\晔旭辉能源测算工具\price_analysis_system\data\price_analysis.db` 是 1.6.6 的历史业务基线，不应作为 2.0 线上业务库直接读写。当前文件约 3.96 GB，包含 `nodes`、`price_data`、`node_meteorology_data`、`import_logs`、`field_mappings`、`breakpoint_data`、`node_geo_mapping`、`province_investment` 和版本表等。

2.0 对它采取“三种用途、三条边界”：

1. **历史回放源**：按节点、日前/实时、日期范围回放历史电价，校验连续均价差、调度和财务输入。
2. **迁移样本源**：通过离线 ETL 抽取到 Raw、Quality、Canonical 层，供 PostgreSQL/TimescaleDB 使用。
3. **运营基线参照**：查询节点目录、来源文件、导入批次和历史质量，帮助确认新接入数据是否发生漂移。

禁止把旧库当成 Web 用户的写库、任务队列或实时遥测库；禁止在原文件上执行清洗、去重、补值或删除。

## 推荐数据流

```text
1.6.6 原库（冻结）
  └─ 文件校验 + 只读快照
      ├─ 历史回放适配器（短期）
      └─ 离线 ETL
          ├─ Raw：原始行和源文件指纹
          ├─ Quality：缺失、非有限值、重复、冲突和人工复核
          ├─ Canonical：标准节点、日期、时区、日前/实时、96 点电价
          └─ Aggregate/Result：月、年、LP、财务和报告
```

2.0 当前已经通过 `BANBOOS2_LEGACY_DB` 指向**隔离副本**，以 SQLite `mode=ro` 打开，并拒绝直接读取 1.6.6 默认 `data\price_analysis.db`。没有配置隔离副本时保持 demo 模式，避免误读旧生产数据。

## 建议的数据库管理方式

### 1. 先做可恢复的源库快照

每次迁移先复制到 `E:\Banboos2.0\var\legacy-snapshots\YYYYMMDD\`，记录 SHA-256、文件大小、SQLite integrity_check、源库版本、迁移脚本版本和操作者。快照只读保存，迁移失败直接丢弃工作副本，不碰 1.6.6 源文件。

### 2. 建立导入批次登记

将 1.6.6 的 `import_logs`、`source_file`、导入时间和文件哈希映射到 2.0 的 `ingest_batch`；每条 Canonical 记录保留 `source_id`、`source_row_id`、`snapshot_id`、`quality_snapshot_id` 和 `run_id`。这样能够回答“这条电价来自哪个文件、哪次迁移、经过什么规则”。

### 3. 电价表按时间和市场管理

`price_data` 中的 `case_type` 只映射为 2.0 的“日前”或“实时”；`OK`、`missing` 等只作为质量字段，不能成为市场类型。96 个 15 分钟点必须经过有限值、完整日、重复日期和日期范围检查。2.0 财务联动继续使用不少于完整年度的年度均值，不足时回退全部有效天数。

### 4. 大表不要长期留在 SQLite 查询链路

SQLite 适合隔离回放和一次性迁移，不适合未来多用户、实时接入和并发导出。正式部署建议：PostgreSQL 保存节点、配置、任务、审计和标准事实；TimescaleDB 保存气象/遥测；对象存储保存原始文件、快照和大报表。2.0 的本地 SQLite 只保留开发运行时、边缘断网缓存和测试数据。

### 5. 旧库管理表分批接入 2.0

下一步按优先级接入：

- `nodes`：节点目录和省份筛选（已有）；
- `import_logs`、`field_mappings`、`breakpoint_data`：导入任务、字段映射、断点续传和失败重试；
- `node_geo_mapping`：地理坐标和气象节点匹配；
- `province_investment`：省级预设参数，明确标记为预设而非实时市场事实；
- `data_access_log`、质量结果：审计查询和数据质量面板。

接入顺序应是只读查询 → 离线迁移 → 结果对账 → 才允许新增数据写入 2.0；不提供旧库在线写接口。

## 迁移验收门槛

每个节点和两种市场至少完成：记录数、完整日数、首末日期、96 点均值/最小值/最大值、年度价差均值和财务首年收益的逐项对账。任何差异必须生成差异报告，保留旧结果和新结果，不直接覆盖。

当前实现基础：`packages/infrastructure/legacy_sqlite.py`、`packages/application/readonly_service.py`、`docs/ADR/0003-legacy-replay-only.md`。下一阶段应新增快照/哈希/批次迁移命令，以及旧库管理表的只读 API。

## 快照工具

使用以下命令对隔离副本生成可验证快照；不要把 1.6.6 默认生产库直接配置为 2.0 的写库：

```powershell
Set-Location E:\Banboos2.0
& .venv\Scripts\python.exe scripts\snapshot_legacy_db.py `
  E:\path\to\isolated\price_analysis.db `
  --destination E:\Banboos2.0\var\legacy-snapshots
```

命令会输出 `manifest.json`，包含源路径、快照路径、文件大小、SHA-256、SQLite `integrity_check`、表行数和迁移版本。复制中断或完整性检查失败时会清理临时目录，不产生可误用的快照。

### 管理表只读接口

系统管理页通过以下接口查看隔离旧库的管理元数据：

- `GET /api/v1/legacy/import-logs`
- `GET /api/v1/legacy/field-mappings`
- `GET /api/v1/legacy/breakpoints`
- `GET /api/v1/legacy/geo-mappings`
- `GET /api/v1/legacy/province-investment`
- `GET /api/v1/legacy/access-log`

接口只使用固定表和字段白名单，默认最多返回 200 条；未配置隔离旧库时返回 `source_mode=demo` 和空列表。它们不接受写请求，不执行数据清洗，也不改变 1.6.6 文件。
