# 发布门禁 API

`GET /api/v1/system/launch-gate` 汇总上线前检查：手机号 / 邮箱 / 微信身份服务、PostgreSQL、Redis、1.6.6 财务模板、生产控制开关和租户隔离状态。API token 只作为联调 fallback 显示为提示，不再作为正式用户认证门禁。结果分为 `staging-ready` 或 `blocked`；租户隔离在当前版本明确标记为 `warn`，不会被误判为生产就绪。系统管理页可直接刷新并查看每项说明。

生产控制必须保持 `BANBOOS2_CONTROL_MODE=disabled`。该接口只做门禁检查，不会开启控制权限，也不替代预发布备份恢复、权限和硬件在环验收。
