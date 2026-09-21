# 隔离数据导入预览与审计

`POST /api/v1/import/preview` 接收来源名称、市场（仅 `日前` 或 `实时`）和行数组。每行必须有正整数 `node_id`、ISO 日期以及 96 个 15 分钟价格点；服务会拒绝 `OK`、`missing` 等质量标签、错误市场、空值、NaN、无穷值和错误点数，并生成内容寻址的预览文件。

只有预览无错误且客户端明确提交 `confirm=true` 时，`POST /api/v1/import/commit` 才会生成不可变审计事件。当前阶段的提交结果为 `validated-only`，只记录导入意图和通过行数，不写入 1.6.6 数据库或生产 staging；写入采用临时文件加原子替换，失败不会留下半个批次。`GET /api/v1/import/audit` 提供最近审计事件，便于后续接入审批、回滚和 PostgreSQL 导入任务。
