# 第一阶段交付记录

第一阶段目标是把 Banboos 2.0 建成可启动、可联调、可回放的服务化基础，而不是提前接入真实电站控制。

## 已交付

- FastAPI `/health`、`/api/v1/meta` 和版本化只读接口：节点、日前/实时价格摘要、气象摘要。
- 只读 SQLite 适配器，按完整 96 点日记录统计有效天数和数据点，并拒绝直接读取 1.6.6 的默认生产库。
- Web 只读工作台，可独立静态启动并通过 CORS 调用 API。
- 异步任务状态契约：提交任务返回 `queued`，查询任务返回稳定的 `RunStatus`；执行器留待下一阶段接入。
- 现场边缘模拟器，输出 SOC、功率、温度三类标准化遥测点，不连接任何真实设备。
- 4 个自动化测试覆盖 API 契约、只读数据库、写入保护和遥测结构。

## 启动联调

```powershell
Set-Location E:\Banboos2.0
& .venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
python -m http.server 5173 --directory E:\Banboos2.0\apps\web
```

浏览器打开 `http://127.0.0.1:5173`；接口文档在 `http://127.0.0.1:8000/docs`。

如需回放 1.6.6 数据，只能先制作隔离副本，再设置 `BANBOOS2_LEGACY_DB` 指向副本。没有设置时服务运行在 demo 模式，避免系统误读旧生产数据库。

## 验收结果

`pytest -q`：4 passed；`ruff check apps packages tests`：All checks passed。API 本地烟测验证 health=ok、demo 模式、任务 queued 和 Web Origin CORS 均正常。

下一阶段再接入 PostgreSQL/Alembic 持久化、Redis 任务执行器、正式 React/TypeScript 前端和隔离数据导入流水线。
