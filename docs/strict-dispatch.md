# 严格历史调度

`packages/domain/storage_dispatch.py` 是不依赖 UI、API 或数据库的纯 Python 领域实现。它使用 SciPy `milp` 求解 96 个 15 分钟时段的严格互斥模型。

模型约束包括：

- 充电功率与放电功率均不超过 `power_mw`；
- 同一时段不可同时充放电；
- SOC 按充放电效率逐段守恒，且日末恢复到初始 SOC；
- SOC 上下限和每日等效循环上限；
- 充电侧线损、输配电价、系统运行费，放电侧返还和门槛价差；
- `degradation_alpha > 0` 时启用 24 段保守线性化衰减成本。

任务输入限制为最多 31 个完整日，缺失 96 点不插补；无有效日或求解器未收敛时不发布收益结果。每次成功任务写入内容哈希输入快照，Worker 结果包含 `snapshot_id`、`algorithm_version` 和逐日摘要。

功率与容量不锁死为某一组数值，但必须满足正数且由 `capacity_mwh / power_mw` 表示系统时长。例如 100MW/200MWh 为 2 小时，50MW/200MWh 为 4 小时。
