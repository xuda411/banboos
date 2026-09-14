# Web 只读端

这是第一阶段的无构建依赖工作台，用于验证 API 契约和信息架构。页面支持节点、电价、气象只读摘要、运营摘要，并可提交财务测算任务、轮询执行状态和下载完成后的 XLSX 报表。历史电价曲线由 `GET /api/v1/price/curves` 提供，当前 demo 数据源为空时页面不会生成伪造曲线。启动 API 后，可用任意静态文件服务器打开此目录：

```powershell
python -m http.server 5173 --directory E:\Banboos2.0\apps\web
```

浏览器访问 `http://127.0.0.1:5173`。后续进入正式 Web 开发时，将保持 `/api/v1` 契约不变，迁移到 React + TypeScript + ECharts。
