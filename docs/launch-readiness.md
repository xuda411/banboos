# 初步上线检查

当前版本达到“可部署联调、可灰度验证”条件，尚未达到开放真实控制权限的条件。

## 上线前命令

```powershell
Copy-Item .env.example .env
# 编辑 .env，替换数据库、身份服务和 CORS 域名配置
docker compose -f deploy/docker-compose.prod.yml up -d postgres redis
docker compose -f deploy/docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f deploy/docker-compose.prod.yml up -d api worker
```

## 本地人工检查

没有 Docker 或 Redis 时，可用共享 SQLite 运行时启动 API、Worker 和 Web：

```powershell
Set-Location E:\Banboos2.0
.\scripts\start_manual_check.ps1
```

浏览器打开 `http://127.0.0.1:5173`，提交一个财务测算任务并等待状态变为
`succeeded`，随后点击下载报表。检查结束后执行：

```powershell
.\scripts\stop_manual_check.ps1
```

## 必检项

- `GET /health` 返回 `status=ok`。
- `GET /readyz` 返回 `status=ready`，Redis 检查为 `ok`。
- 生产环境必须配置手机号、邮箱和微信身份服务；API token 仅保留为联调 fallback，不作为正式用户登录。
- `BANBOOS2_CORS_ORIGINS` 只填写实际 Web 域名，不使用 `*`。
- 数据库迁移完成后再启动 Worker；先用 `noop` 和 `price-summary` 做灰度任务。
- 备份 PostgreSQL 和 Redis 持久卷，并记录当前 Git 提交与 Alembic revision。
- 真实电站继续保持只读；调度建议、测试执行、生产执行必须另行通过验证门槛。
- 使用 `GET /api/v1/system/launch-gate` 保存发布门禁快照；出现 `blocked` 或租户隔离 `warn` 时不得开放生产控制。

生产编排文件为 [docker-compose.prod.yml](../deploy/docker-compose.prod.yml)，配置模板为 [.env.example](../.env.example)。
