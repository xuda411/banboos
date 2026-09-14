# 第二阶段基础交付

本阶段把第一阶段的只读服务推进到可持久化、可追溯的服务器基础。

## 交付内容

- 新增 `/api/v1/quality/summary`，统计总记录、完整记录、缺失单元格、非有限值和完整率。
- 任务提交支持 `Idempotency-Key`，重复请求返回同一 `run_id`，避免网络重试产生重复任务。
- 建立 PostgreSQL SQLAlchemy 模型：租户、站点、遥测点、分析任务。
- 建立 Alembic 首次迁移，支持通过 `BANBOOS2_DATABASE_URL` 配置数据库。
- 保持数据库惰性连接；不启动 PostgreSQL 时，API 仍可安全运行在 demo 模式。
- Web 工作台增加电价完整率指标，直接暴露数据质量状态。

## 数据库迁移

```powershell
Set-Location E:\Banboos2.0
$env:BANBOOS2_DATABASE_URL = "postgresql+asyncpg://banboos:banboos-dev-only@127.0.0.1:5432/banboos2"
& .venv\Scripts\python.exe -m alembic upgrade head
```

迁移 SQL 已通过 `alembic upgrade head --sql` 验证。当前未自动连接或修改任何生产数据库。

## 验证

- `pytest -q`：6 passed
- `ruff check apps packages tests migrations`：通过
- Alembic 离线 SQL：成功生成租户、站点、遥测和任务表

下一步是接入 Redis 任务执行器，并把内存 `RunRegistry` 替换为 PostgreSQL 任务记录加 Redis 队列；API 契约保持不变。
