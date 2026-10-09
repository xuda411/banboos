# Banboos 2.0 全线开发进度与测试报告

本报告以 2026-10-09 当前源码、隔离自动化测试、只读 staging 数据库和本机 API 检查为依据。完整版本位于 [协调工作区报告](C:/Users/Laptop/Documents/Trae/progress-test-report-20261009.md)。

## 结论

当前版本已达到开发测试通过和脱敏数据预发布演示水平：**141 项测试通过、3 条警告；Ruff、pip check、4 个 Web JavaScript 文件语法检查、Git 差异检查、离线迁移与任务恢复均通过；完整 staging Web/API 检查通过。**

生产商业交付仍被身份服务、租户强制隔离、PostgreSQL/Redis 权威链路、可靠队列、HTTPS 反向代理、XLSM 跨引擎重算、备份恢复和真实 EMS 接入阻断，生产控制保持关闭。

## 核心当前证据

- staging：5,409 节点；Raw 3,946,141；Canonical 3,936,952；Quality 中完整 3,936,952、重复 9,162、`multiple_source` 22、拒绝 5。
- API 只读检查：健康/就绪通过；5,372 个可用节点、5 个省份；抽样三节点两市场的 2 小时/4 小时聚合覆盖率 100%；价格及聚合 XLSX 返回 200。
- 50 MW/200 MWh 连续窗口取 16 点，100 MW/200 MWh 取 8 点；合成曲线回放价差 750 元/MWh。
- 调度入口实际使用 `scipy.optimize.milp` 的严格互斥历史回放，非纯 LP，也不是未来收益预测；两种功率配置的独立轨迹校验通过。
- Web 静态 Impeccable 检测 12 条信号，静态质量评分 13/20；低对比度和小字号需 UI 专项修复。

## 当前阻断

生产严格预检明确阻断 PostgreSQL、Redis、身份提供方、身份哈希密钥、明确 CORS、XLSM 发布门禁和严格租户模式。Redis 队列仍采用 `BLPOP`，尚无 ACK/重试/死信的生产证据。导入数据的 22 个多来源质量记录还需逐组裁决和可解释呈现。

证据目录：`E:\Banboos2.0\outputs\progress-audit-20261009\run-111115`。

注：完整数据库启动脚本在 Windows PowerShell 5 的 UTF-8 无 BOM 解析下出现字符串解析错误；使用项目环境提供的 `pwsh.exe` 后检查正常完成，脚本兼容性仍应修复。
