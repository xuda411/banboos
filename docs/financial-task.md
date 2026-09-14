# 财务测算任务

`financial` Worker 任务使用纯领域现金流模型，不读取 Qt 控件，也不生成 Excel 专属公式。输入金额统一为元，容量为 MWh，投资单价为元/Wh。

任务可以直接传入 `annual_revenue_yuan`，也可以传入 `source_run_id`，由 Worker 读取已成功的 `strict-dispatch` 结果中的 `annualized_net_revenue_yuan`。后者保证价差调度与财务测算来自同一条可回放任务链路。

模型目前包含：单位投资、运营年限、EOL 线性衰减、运维费率及增长、残值率、所得税、折现率、项目现金流、NPV、唯一 IRR 和静态回收期。每个结果都保留 `source_run_id`、`model_version`、年度现金流和功率/容量时长。

示例请求：

```json
{
  "kind": "financial",
  "parameters": {
    "power_mw": 100,
    "capacity_mwh": 200,
    "source_run_id": "<已成功的strict-dispatch run_id>"
  }
}
```

当前版本用于服务器化计算链路和结果核对；完整 Excel 模板排版、融资现金流、增值税留抵和多收入项将在财务模型对账通过后逐项加入，避免把简化结果直接当作正式投决表。
