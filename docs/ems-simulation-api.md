# EMS 模拟运营接口

本阶段提供 EMS 接入和下发的稳定 API 契约，默认运行在 `BANBOOS2_EMS_MODE=simulation`。模拟下发会生成确定性的 EMS 回传，用于联调功率、报价、SOC、偏差和看板；不会连接真实设备，也不会改变生产控制开关。

## 决策计划流程

```text
POST /api/v1/ems/decision-plans
        ↓ draft
POST /api/v1/ems/decision-plans/{plan_id}/approve
        ↓ approved
POST /api/v1/ems/decision-plans/{plan_id}/dispatch
        ↓ sent + simulated feedback
GET  /api/v1/ems/dashboard?station_id=demo-station
```

计划点包含 `event_time`、`power_mw`、`price_yuan_per_mwh` 和 `mode`。充电功率为负、放电功率为正，待机功率必须为零。时间点必须升序，价格和功率在服务端做边界校验。

## EMS 回传

EMS 或模拟器通过 `POST /api/v1/ems/feedback` 回传 `actual_power_mw`、`soc_pct`、实际价格、运行状态、质量码和唯一 `raw_message_id`。重复报文不会重复计数。

`GET /api/v1/ems/dashboard` 返回最近计划、最近回传、目标功率/价格、功率偏差、价格偏差、回传数量和延迟状态。

当 `BANBOOS2_CONTROL_MODE=disabled` 时，下发接口只返回 `blocked-control-disabled`，不生成模拟回传；这保证生产控制关闭时不会产生虚假的执行结果。测试联调可使用 `BANBOOS2_CONTROL_MODE=simulation`，生产接入再将 `BANBOOS2_EMS_MODE` 替换为真实适配器实现。
