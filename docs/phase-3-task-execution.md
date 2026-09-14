# 第三阶段任务执行链路

本阶段完成统一任务生命周期，为后续 LP、财务和报告执行器提供稳定入口。

## 任务状态

`queued → running → succeeded / failed / cancelled`

任务带有进度、提示信息和错误码；客户端可使用 `Idempotency-Key` 进行安全重试。

## 队列后端

- 未设置 `BANBOOS2_REDIS_URL`：使用进程内队列，适合本地联调。
- 设置 `BANBOOS2_REDIS_URL`：API 与 Worker 共享 Redis 队列和任务状态，可跨进程运行。

启动 Worker：

```powershell
Set-Location E:\Banboos2.0
$env:BANBOOS2_REDIS_URL = "redis://127.0.0.1:6379/0"
& .venv\Scripts\python.exe -m apps.worker.main
```

当前 Worker 已支持 `noop` 验证任务闭环，以及 `price-summary` 节点电价摘要任务。`price-summary` 会调用同一只读服务并把结果写入任务状态的 `result` 字段，可通过 `run_id` 回放。LP、财务或控制执行器尚未接入，未知任务会明确失败并返回 `EXECUTOR_NOT_IMPLEMENTED`。

## API

- `POST /api/v1/runs?kind=noop`
- `POST /api/v1/runs`，JSON：`{"kind":"price-summary","parameters":{"node_id":1,"market":"实时","start_date":"2026-01-01","end_date":"2026-01-31"}}`
- `POST /api/v1/runs`，JSON：`{"kind":"price-analysis","parameters":{"node_id":1,"market":"实时","start_date":"2026-01-01","end_date":"2026-01-31","power_mw":100,"capacity_mwh":200}}`
- `GET /api/v1/runs/{run_id}`
- `POST /api/v1/runs/{run_id}/cancel`

生产部署仍需在 PostgreSQL 任务记录落库后再开放多 Worker 扩展；本阶段 Redis 状态存储用于联调和故障恢复验证。

`price-analysis` 当前采用可解释的“互斥低价充电/高价放电价差估算”，显式使用 `capacity_mwh / power_mw` 得到时长，并保留输入参数和来源模式。严格调度已迁移为 `strict-dispatch` 领域服务，包含 SOC 守恒、日末复位、充放电互斥、循环上限、效率、门槛成本和可选衰减成本。

严格调度任务会在 `BANBOOS2_SNAPSHOT_DIR` 下保存内容哈希输入快照。可用 `python scripts/replay_dispatch.py <snapshot_id>` 在无数据库环境下重算，核对 `algorithm_version`、有效日数和收益。所有调度结果仍标记为历史回放，不代表预测或实际运营收益。
