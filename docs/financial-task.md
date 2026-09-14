# 财务测算任务

`financial` Worker 任务使用纯领域现金流模型，不读取 Qt 控件，也不生成 Excel 专属公式。输入金额统一为元，容量为 MWh，投资单价为元/Wh。

任务可以直接传入 `annual_revenue_yuan`，也可以传入 `source_run_id`，由 Worker 读取已成功的 `strict-dispatch` 结果中的 `annualized_net_revenue_yuan`。后者保证价差调度与财务测算来自同一条可回放任务链路。

模型目前包含：单位投资、运营年限、EOL 线性衰减、运维费率及增长、容量租赁、容量电费、补贴、一次/二次调频、残值率、所得税、折现率、贷款比例/期限/利率、建设期利息、换电池投资、项目和资本金现金流、NPV、唯一 IRR 和静态回收期。每个结果都保留 `source_run_id`、`model_version`、年度现金流和功率/容量时长。

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

完成任务后可以通过 `GET /api/v1/runs/{run_id}/export` 下载结构化 XLSX 报表。导出接口只接受已成功的 `financial` 任务，文件包含“项目概览”“测算参数”“年度现金流”“融资明细”四个工作表，并保留源任务 ID、模型版本、输入参数、年度收入拆分、融资明细和现金流字段，便于复核与二次加工。服务端默认将文件原子写入 `var/exports`，可用 `BANBOOS2_EXPORT_DIR` 指定 E 盘上的专用目录。

该报表是服务器版的可追溯输出基线；与既有 xlsm 模板的逐单元格排版对账仍作为下一步迭代，正式投决前应完成模板字段映射和财务口径复核。
