# 电价日/月/年统计链路

本阶段新增只读接口 `GET /api/v1/price/aggregates`，用于把真实节点的完整 96 点曲线转换为可复核的日、月、年统计。接口与连续均价差财务基准共用同一套窗口规则：

- `market` 只接受 `日前` 或 `实时`，两个市场不会混合；
- 仅使用完整且有限的 96 点日曲线，缺点或非有限值计入 `excluded_records`；
- 同一日期的重复来源先按来源求低/高连续窗口，再对日期等权平均；
- `duration_hours` 支持 15 分钟整数倍，网页默认 2 小时，也可切换 4 小时；
- `monthly` 和 `annual` 同时返回均价、低价窗口、高价窗口、价差、有效日数和极值；
- 响应保留 `source_mode`、有效日期范围、重复来源日数，便于与迁移批次和节点分析结果对账。
- 响应同时返回 `missing_dates` 和 `multiple_source_dates`，缺日包括范围内没有完整有效曲线的日期；网页可导出月度/年度统计 CSV。

接口只读当前隔离 staging/legacy 数据，不会写入数据库，也不会创建任务快照。节点分析的财务联动仍使用 `annual_window_average` 的最近完整年度优先、否则全部有效日回退规则；该接口用于曲线页面的统计展示和导出前核查，不替代财务任务。

## 验证

`tests/unit/test_price_aggregates.py` 覆盖重复来源、无效日、月份/年度分组和窗口校验；`tests/contract/test_api_bootstrap.py` 覆盖 demo 模式的响应契约。当前测试套件为 94 passed，Ruff 与浏览器脚本语法检查通过。
