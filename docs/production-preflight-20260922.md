# 预发布门禁阶段

本阶段把上一份人工测试报告中的上线前要求固化为可执行预检。预检只验证配置边界，不把环境变量存在误判成短信、微信 OAuth 或硬件已经联通。

## 检查内容

- PostgreSQL 和 Redis：生产必须声明连接地址；开发环境继续允许本地运行时。
- 手机、邮箱、微信身份服务：生产必须声明供应商配置。
- 认证模式：生产必须使用 `BANBOOS2_AUTH_MODE=identity`，禁止把 API token 当作正式账号登录。
- 租户隔离：生产必须设置 `BANBOOS2_TENANT_ENFORCEMENT=strict`。
- CORS、财务模板和生产控制：生产域名必须明确，1.6.6 模板必须可用，生产控制必须保持关闭。

## 执行方式

```powershell
Set-Location E:\Banboos2.0
Copy-Item .env.example .env
# 编辑 .env，填入真实数据库、Redis、短信、邮件、微信和 Web 域名
& .venv\Scripts\python.exe scripts\preflight_production.py --strict
```

接口 `GET /api/v1/system/preflight` 与系统管理页使用同一套检查逻辑。脚本和接口均不会发送验证码、访问设备或修改业务数据；外部身份服务和生产控制仍需后续联调及硬件在环验收。
