# 组合结果看板与归档

## 已实现

- `GET /api/v1/runs/{run_id}/portfolio-dashboard`：仅接受成功的 `portfolio-optimization` 任务，返回投资、NPV、IRR、选中项目数、来源快照、算法版本及省份汇总。
- Web 组合筛选页在任务完成后展示结果指标卡、按省份汇总表和现金流口径说明。
- `GET /api/v1/runs/{run_id}/archive`：生成 ZIP 归档到 `BANBOOS2_ARCHIVE_DIR`（默认 `var/archives`），包含任务结果、看板 JSON、候选输入快照、说明和 SHA256 manifest。
- 候选快照历史索引改为事务化重建；重建时先校验内容寻址哈希和候选结构，空目录也能安全查询。

## 口径边界

看板沿用组合优化结果的现金流口径。候选节点的年化套利估算是历史价差初筛指标，不等同于扣除运维、税费和融资后的财务净现金流。当前归档是本地可验证归档，尚未声称具备 S3/OSS 等长期对象存储能力。

## 验收

2026-09-29：全量 `139 passed, 3 warnings`；定向组合/API/归档测试 `7 passed, 2 warnings`；隔离 API + Web 页面人工检查确认结果看板可见，浏览器错误日志为空。
