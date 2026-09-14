# Banboos 2.0

服务器部署、Web 协同与真实电站运营平台。

## 项目状态

当前为服务器基础开发阶段，尚未连接生产电站，也不会覆盖 Banboos 1.6.6。稳定桌面基线位于：

`E:\晔旭辉能源测算工具\price_analysis_system`

迁移只允许使用隔离副本和回放数据。

## 目录

```text
apps/api/        FastAPI 接口应用
apps/web/        Web 前端应用
apps/edge/       现场边缘网关
apps/worker/     异步任务执行器
packages/domain/ 领域模型和规则
packages/application/ 用例编排
packages/contracts/ API、事件和结果契约
packages/infrastructure/ 数据库、存储和外部接口适配
deploy/          本地与服务器部署文件
docs/            架构、ADR 和迁移记录
tests/           单元、契约和集成测试
legacy/          1.6.6 迁移说明，不存放生产数据库
```

## 已完成阶段

- 第一阶段：FastAPI 只读接口、Web 只读端、1.6.6 隔离数据回放和电站模拟器。
- 第二阶段基础：数据质量摘要、任务幂等键、PostgreSQL 模型和 Alembic 首次迁移。
- 第三阶段：任务生命周期、Redis/内存队列适配、Worker 入口和取消/失败状态。
- 上线基础：生产认证开关、就绪探针、请求追踪、容器镜像和 API/Worker 编排。
- 业务调度：严格互斥历史调度、输入快照、结果回放和功率/容量时长校验。
- 财务测算：现金流、EOL、税费、NPV、IRR、回收期、调度结果链路和结构化 XLSX 报表导出。
- Web 联调：节点日期自动校准、财务任务提交、进度轮询和结果下载。

交付记录见 [第一阶段](docs/phase-1-delivery.md)、[第二阶段基础](docs/phase-2-foundation.md)、[第三阶段任务执行链路](docs/phase-3-task-execution.md)、[严格调度](docs/strict-dispatch.md)、[财务测算](docs/financial-task.md) 和 [初步上线检查](docs/launch-readiness.md)。

完整约束见 [Banboos 2.0 开发宪法](DEVELOPMENT_CONSTITUTION.md)。
