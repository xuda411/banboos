# 初步上线检查

当前版本达到“可部署联调、可灰度验证”条件，尚未达到开放真实控制权限的条件。

## 上线前命令

```powershell
Copy-Item .env.example .env
# 编辑 .env，替换数据库密码、API token 和 CORS 域名
docker compose -f deploy/docker-compose.prod.yml up -d postgres redis
docker compose -f deploy/docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f deploy/docker-compose.prod.yml up -d api worker
```

## 必检项

- `GET /health` 返回 `status=ok`。
- `GET /readyz` 返回 `status=ready`，Redis 检查为 `ok`。
- 生产环境 `BANBOOS2_API_TOKEN` 至少 32 位；未携带 token 的 API 请求返回 401。
- `BANBOOS2_CORS_ORIGINS` 只填写实际 Web 域名，不使用 `*`。
- 数据库迁移完成后再启动 Worker；先用 `noop` 和 `price-summary` 做灰度任务。
- 备份 PostgreSQL 和 Redis 持久卷，并记录当前 Git 提交与 Alembic revision。
- 真实电站继续保持只读；调度建议、测试执行、生产执行必须另行通过验证门槛。

生产编排文件为 [docker-compose.prod.yml](../deploy/docker-compose.prod.yml)，配置模板为 [.env.example](../.env.example)。
