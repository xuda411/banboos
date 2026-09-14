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

当前 Worker 已支持 `noop` 验证任务闭环；尚未接入真实 LP、财务或控制执行器，未知任务会明确失败并返回 `EXECUTOR_NOT_IMPLEMENTED`。

## API

- `POST /api/v1/runs?kind=noop`
- `GET /api/v1/runs/{run_id}`
- `POST /api/v1/runs/{run_id}/cancel`

生产部署仍需在 PostgreSQL 任务记录落库后再开放多 Worker 扩展；本阶段 Redis 状态存储用于联调和故障恢复验证。
