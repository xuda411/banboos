"""XLSX reports for successful task snapshots and bounded readonly queries."""
from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from packages.application.financial_export import GREEN, LIGHT_GREEN, _fit_columns, _header, _title
from packages.domain.lp_reconciliation import reconcile_lp

SUPPORTED_TASKS = {"financial", "price-analysis", "investment-scenario", "strict-dispatch", "lp-analysis", "sensitivity", "portfolio-optimization"}


def table(workbook, title, headers, rows, formats=None):
    sheet = workbook.create_sheet(title)
    _title(sheet, title, len(headers))
    _header(sheet, 4, headers)
    for row in rows:
        sheet.append(row)
    for cells in sheet.iter_rows(min_row=5):
        for cell in cells:
            # Untrusted labels, filenames and task messages are text, never formulas.
            if isinstance(cell.value, str):
                cell.data_type = "s"
            cell.font = Font(name="Microsoft YaHei", size=11, color="173B35")
            cell.fill = PatternFill("solid", fgColor=LIGHT_GREEN if cell.row % 2 else "FFFFFF")
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            if isinstance(cell.value, (int, float)):
                cell.number_format = (formats or {}).get(cell.column, "#,##0.00;[Red](#,##0.00);0.00")
        sheet.row_dimensions[cells[0].row].height = 30
    sheet.freeze_panes = "B5"
    sheet.auto_filter.ref = f"A4:{get_column_letter(len(headers))}{max(4, sheet.max_row)}"
    _fit_columns(sheet)
    return sheet


def finish(workbook):
    for sheet in workbook:
        sheet.sheet_view.showGridLines = False
        sheet.print_title_rows = "1:4"
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
        sheet.page_setup.fitToWidth, sheet.page_setup.fitToHeight = 1, 0
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.print_area = f"A1:{get_column_letter(sheet.max_column)}{sheet.max_row}"
        sheet.row_dimensions[1].height = 32
        sheet.row_dimensions[2].height = 32
        sheet.row_dimensions[4].height = 40
        sheet.oddFooter.center.text = "Banboos 2.0 · 第 &P 页 / 共 &N 页"
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def workbook_with_source(metadata):
    workbook = Workbook()
    workbook.remove(workbook.active)
    normalized = dict(metadata)
    normalized.setdefault("导出格式版本", "banboos-export-2026-09-21")
    rows = [[str(key), value if not isinstance(value, (dict, list)) else str(value)]
            for key, value in normalized.items()]
    table(workbook, "导出说明", ["项目", "内容"], rows)
    workbook["导出说明"].column_dimensions["B"].width = 90
    return workbook


def export_task_xlsx(run):
    if run.kind not in SUPPORTED_TASKS - {"financial"} or run.status != "succeeded" or not run.result:
        raise ValueError("任务未完成或不支持导出")
    data = run.result
    workbook = workbook_with_source({"任务 ID": run.run_id, "任务类型": run.kind,
        "完成时间 UTC": str(run.completed_at), "导出时间 UTC": datetime.now(UTC).isoformat(),
        "上游任务": data.get("source_run_id"), "输入快照": data.get("snapshot_id"),
        "算法或模型版本": data.get("algorithm_version", data.get("model_version", data.get("method"))),
        "口径": "已完成任务的结果快照；缺失值留空，0 表示真实零值；修改参数须重新计算。"})
    table(workbook, "任务参数", ["参数", "值"], [[key, value if not isinstance(value, (dict, list)) else str(value)]
          for key, value in run.parameters.items()])
    table(workbook, "结果摘要", ["指标（字段名含单位）", "数值"],
          [[key, value] for key, value in data.items() if not isinstance(value, (list, dict))])
    if run.kind == "strict-dispatch":
        keys = ["run_date", "net_revenue_yuan", "charge_energy_mwh", "discharge_energy_mwh", "cycles", "shutdown", "solver_gap"]
        table(workbook, "逐日调度", ["日期", "净收益（元）", "充电量（MWh）", "放电量（MWh）", "循环次数", "停机", "求解间隙"],
              [[day.get(key) for key in keys] for day in data["days"]], {7: "0.00%"})
    elif run.kind == "lp-analysis":
        keys = ["run_date", "net_revenue_yuan", "charge_energy_mwh", "discharge_energy_mwh", "surcharge_cost_yuan",
                "refund_revenue_yuan", "hurdle_cost_yuan", "degradation_cost_yuan", "cycles",
                "spread_max_yuan_per_mwh", "spread_avg_yuan_per_mwh", "shutdown", "solver_gap"]
        table(workbook, "LP逐日结果", ["日期", "净收益（元）", "充电量（MWh）", "放电量（MWh）",
              "充电附加成本（元）", "放电返还（元）", "门槛成本（元）", "衰减成本（元）", "循环次数",
              "最大价差（元/MWh）", "平均价差（元/MWh）", "停机", "求解间隙"],
              [[day.get(key) for key in keys] for day in data["days"]], {13: "0.00%"})
        trajectory_rows = []
        for day in data["days"]:
            for slot, values in enumerate(zip(day["prices_yuan_per_mwh"], day["charge_mw"], day["discharge_mw"], day["soc"]), 1):
                price, charge, discharge, soc = values
                trajectory_rows.append([day["run_date"], slot, f"{(slot - 1) // 4:02d}:{(slot - 1) % 4 * 15:02d}", price, charge, discharge, soc])
        table(workbook, "LP时段轨迹", ["日期", "序号", "时段终点", "电价（元/MWh）", "充电功率（MW）", "放电功率（MW）", "区间末SOC"], trajectory_rows)
        month_keys = ["month", "days", "revenue_total_yuan", "revenue_avg_yuan", "discharge_energy_total_mwh", "cycles_avg", "spread_max_yuan_per_mwh", "spread_avg_yuan_per_mwh"]
        table(workbook, "LP月度汇总", ["月份", "有效日", "净收益合计（元）", "日均净收益（元）", "放电量合计（MWh）", "平均循环", "最大价差", "平均价差"],
              [[row.get(key) for key in month_keys] for row in data["monthly"]])
        year_keys = ["year", "days", "revenue_total_yuan", "revenue_avg_daily_yuan", "discharge_energy_total_mwh", "cycles_avg", "spread_max_yuan_per_mwh", "spread_avg_yuan_per_mwh"]
        table(workbook, "LP年度汇总", ["年度", "有效日", "净收益合计（元）", "日均净收益（元）", "放电量合计（MWh）", "平均循环", "最大价差", "平均价差"],
              [[row.get(key) for key in year_keys] for row in data["annual"]])
        if data.get("comparison"):
            comparison_keys = ["run_date", "lp_revenue_yuan", "simple_revenue_yuan", "improvement_yuan", "improvement_pct", "lp_discharge_energy_mwh", "simple_discharge_energy_mwh", "lp_cycles"]
            table(workbook, "LP与窗口基准", ["日期", "LP净收益（元）", "窗口基准（元）", "提升（元）", "提升比例（%）", "LP放电量（MWh）", "基准放电量（MWh）", "LP循环"],
                  [[row.get(key) for key in comparison_keys] for row in data["comparison"]])
        if data.get("sensitivity"):
            sensitivity_keys = ["c_rate", "power_mw", "capacity_mwh", "total_revenue_yuan", "avg_daily_revenue_yuan", "annual_revenue_yuan", "avg_cycles", "capex_yuan"]
            table(workbook, "LP C率敏感性", ["C率", "功率（MW）", "容量（MWh）", "总净收益（元）", "日均净收益（元）", "年化净收益（元）", "平均循环", "投资额（元）"],
                  [[row.get(key) for key in sensitivity_keys] for row in data["sensitivity"]], {1: "0.00%"})
        audit = reconcile_lp(data)
        table(workbook, "LP对账", ["检查项", "状态", "实际值", "期望值", "差值", "容差"],
              [[check["name"], check["status"], check["actual"], check["expected"], check["delta"], check["tolerance"]]
               for check in audit["checks"]])
    elif run.kind == "price-analysis":
        baselines = data.get("window_baselines") or [{
            "duration_hours": data.get("duration_hours"),
            "start_date": data.get("start_date"), "end_date": data.get("end_date"),
            "valid_days": data.get("valid_days"), "available_days": data.get("available_days"),
            "excluded_records": data.get("excluded_records"),
            "multiple_source_days": data.get("multiple_source_days"),
            "baseline_policy": data.get("baseline_policy"),
            "charge_price_yuan_per_mwh": data.get("charge_price_yuan_per_mwh"),
            "discharge_price_yuan_per_mwh": data.get("discharge_price_yuan_per_mwh"),
            "spread_yuan_per_mwh": data.get("spread_yuan_per_mwh"),
            "monthly": data.get("monthly", []),
        }]
        by_duration = {round(float(item.get("duration_hours")), 4): item for item in baselines
                       if item.get("duration_hours") is not None}
        months = sorted({row.get("month") for item in baselines for row in item.get("monthly", []) if row.get("month")})
        rows = []
        for month in months:
            values = [month]
            for duration in (2.0, 4.0):
                row = next((candidate for candidate in by_duration.get(duration, {}).get("monthly", [])
                            if candidate.get("month") == month), {})
                values.extend([row.get("valid_days"), row.get("charge_price_yuan_per_mwh"),
                               row.get("discharge_price_yuan_per_mwh"), row.get("spread_yuan_per_mwh")])
            selected = next((candidate for candidate in data.get("monthly", []) if candidate.get("month") == month), {})
            values.append(selected.get("spread_yuan_per_mwh"))
            rows.append(values)
        table(workbook, "月度价差",
              ["月份", "2h有效日", "2h低价均价（元/MWh）", "2h高价均价（元/MWh）", "2h价差（元/MWh）",
               "4h有效日", "4h低价均价（元/MWh）", "4h高价均价（元/MWh）", "4h价差（元/MWh）",
               "项目时长价差（元/MWh）"], rows,
              {2: "0", 3: "#,##0.00", 4: "#,##0.00", 5: "#,##0.00", 6: "0", 7: "#,##0.00",
               8: "#,##0.00", 9: "#,##0.00", 10: "#,##0.00"})
        table(workbook, "年度基准",
              ["储能时长（小时）", "基准策略", "开始日期", "结束日期", "有效日", "可用日",
               "低价窗口均价（元/MWh）", "高价窗口均价（元/MWh）", "价差（元/MWh）", "重复来源日", "排除记录"],
              [[item.get("duration_hours"), item.get("baseline_policy"), item.get("start_date"), item.get("end_date"),
                item.get("valid_days"), item.get("available_days"), item.get("charge_price_yuan_per_mwh"),
                item.get("discharge_price_yuan_per_mwh"), item.get("spread_yuan_per_mwh"),
                item.get("multiple_source_days"), item.get("excluded_records")] for item in baselines],
              {1: "0.00", 5: "0", 6: "0", 7: "#,##0.00", 8: "#,##0.00", 9: "#,##0.00", 10: "0", 11: "0"})
        table(workbook, "滑动窗口口径", ["系统时长", "连续点数", "计算规则"], [
            ["2 小时", 8, "每条完整96点曲线遍历连续8点，取最低/最高窗口算术均价，价差按有效日等权平均"],
            ["4 小时", 16, "每条完整96点曲线遍历连续16点，取最低/最高窗口算术均价，价差按有效日等权平均"],
        ], {1: "0"})
    elif run.kind == "investment-scenario":
        keys = ["scenario_name", "source_run_id", "source_snapshot_id", "node_id", "market",
                "start_date", "end_date", "power_mw", "capacity_mwh", "duration_hours",
                "baseline_spread_yuan_per_mwh", "average_daily_revenue_yuan", "annual_cycles",
                "utilization", "spread_factor", "retention_rate", "annual_revenue_yuan",
                "formula", "algorithm_version"]
        table(workbook, "投资情景", ["字段", "值"], [[key, data.get(key)] for key in keys])
    elif run.kind == "portfolio-optimization":
        project_keys = ["name", "capacity_mwh", "unit_investment_yuan_wh", "annual_revenue_wan"]
        headers = ["项目", "容量（MWh）", "单位投资（元/Wh）", "年净现金流（万元）"]
        table(workbook, "全部候选项目", headers,
              [[p.get(key) for key in project_keys] for p in run.parameters["projects"]])
        table(workbook, "选中项目", headers + ["投资（万元）", "NPV（万元）"],
              [[p.get(key) for key in project_keys + ["investment_wan", "npv_wan"]]
               for p in data["selected_projects"]])
        task_parameters = run.parameters
        portfolio_audit = table(workbook, "组合复核", ["检查项", "值", "单位", "说明"], [
            ["优化目标", data.get("objective", task_parameters.get("objective")), "", "组合筛选目标"],
            ["预算上限", task_parameters.get("budget_limit_wan"), "万元", "为空表示不设置预算上限"],
            ["年净现金流目标", task_parameters.get("revenue_target_wan"), "万元", "最小投资目标使用"],
            ["折现率", task_parameters.get("discount_rate"), "%", "NPV 计算折现率"],
            ["运营年限", task_parameters.get("operation_years"), "年", "组合现金流周期"],
            ["选中项目数", len(data.get("selected_projects", [])), "个", "满足约束的项目数"],
            ["总投资", data.get("total_investment_wan"), "万元", "组合结果"],
            ["总 NPV", data.get("total_npv_wan"), "万元", "组合结果"],
            ["组合 IRR", data.get("portfolio_irr"), "%", "无有效根时留空"],
            ["结果状态", data.get("outcome"), "", data.get("message", "")],
            ["现金流口径", data.get("cashflow_note"), "", "结果说明"],
        ], {2: "#,##0.00"})
        portfolio_audit["B8"].number_format = "0.00%"
        portfolio_audit["B13"].number_format = "0.00%"
    else:
        keys = ["change_rate", "full_irr", "full_npv_yuan", "payback_year", "first_year_net_profit_yuan"]
        table(workbook, "敏感性分析", ["相对变动率", "项目 IRR", "项目 NPV（元）", "静态回收期（年）", "首年净利润（元）"],
              [[point.get(key) for key in keys] for point in data["points"]], {1: "0.0%", 2: "0.00%"})
    return finish(workbook)


def export_price_xlsx(curves, metadata):
    if not curves:
        raise ValueError("当前范围没有完整电价曲线，无法导出")
    workbook = workbook_with_source(metadata | {"实际天数": len(curves), "单位": "元/MWh",
        "口径": "仅包含完整日，每日 96 点；导出时重新读取，日数上限与查询相同。",
        "导出时间 UTC": datetime.now(UTC).isoformat()})
    rows = []
    for curve in curves:
        for slot, value in enumerate(curve.prices, 1):
            rows.append([curve.run_date, f"{slot // 4:02d}:{slot % 4 * 15:02d}", value, curve.source_mode])
    sheet = table(workbook, "电价时段明细", ["交易日期", "时段终点", "电价（元/MWh）", "来源模式"], rows)
    for cell in sheet["A"][4:]:
        cell.number_format = "yyyy-mm-dd"
    table(workbook, "每日统计", ["日期", "点数", "平均价（元/MWh）", "最低价（元/MWh）", "最高价（元/MWh）"],
          [[c.run_date, 96, sum(c.prices) / 96, min(c.prices), max(c.prices)] for c in curves], {1: "yyyy-mm-dd", 2: "0"})
    # One real Excel chart, selected first day; all days remain in the detail sheet.
    chart_sheet = table(workbook, "首日曲线", ["时段终点", "电价（元/MWh）"], [row[1:3] for row in rows[:96]])
    chart = LineChart()
    chart.title = f"{curves[0].run_date} · {curves[0].market}"
    chart.y_axis.title = "元/MWh"
    chart.add_data(Reference(chart_sheet, min_col=2, min_row=4, max_row=100), titles_from_data=True)
    chart.set_categories(Reference(chart_sheet, min_col=1, min_row=5, max_row=100))
    chart.series[0].graphicalProperties.line.solidFill = GREEN
    chart.width, chart.height = 26, 12
    chart_sheet.add_chart(chart, "D5")
    chart_sheet.cell(30, 16, "首日曲线；其余日期见电价时段明细。")
    return finish(workbook)


def export_weather_xlsx(series, metadata):
    if not series:
        raise ValueError("当前范围没有气象观测，无法导出")
    workbook = workbook_with_source(metadata | {"实际观测数": len(series),
        "口径": "导出原始时间粒度；预计功率来自模型，非电站实测。缺失值留空。",
        "导出时间 UTC": datetime.now(UTC).isoformat()})
    keys = ["data_time", "ghi_w_m2", "wind_speed_m_s", "temp_c", "pv_predict_power_mw", "wind_predict_power_mw", "source", "source_mode", "is_power_simulated"]
    table(workbook, "气象与预计功率", ["数据时间（来源时间）", "辐照度（W/m²）", "风速（m/s）", "温度（℃）", "光伏功率（MW）", "风电功率（MW）", "数据来源", "来源模式", "功率为预计值"],
          [[row.model_dump(mode="json").get(key) for key in keys] for row in series])
    return finish(workbook)


def export_price_aggregate_xlsx(aggregate):
    """Export monthly/annual price-window statistics with coverage evidence."""
    payload = aggregate.model_dump(mode="json") if hasattr(aggregate, "model_dump") else dict(aggregate)
    workbook = workbook_with_source({
        "报表类型": "节点电价月度/年度统计",
        "节点 ID": payload.get("node_id"), "市场": payload.get("market"),
        "统计窗口（小时）": payload.get("duration_hours"),
        "查询开始日期": payload.get("start_date"), "查询结束日期": payload.get("end_date"),
        "来源模式": payload.get("source_mode"), "有效日": payload.get("valid_days"),
        "可用日": payload.get("available_days"), "排除记录": payload.get("excluded_records"),
        "重复来源日": payload.get("multiple_source_days"),
        "口径": "月度和年度统计均按完整 96 点日、连续窗口计算；缺失日期和重复来源日期单独列示。",
    })
    headers = ["周期类型", "周期", "有效日", "均价（元/MWh）", "低价窗口均价（元/MWh）",
               "高价窗口均价（元/MWh）", "价差（元/MWh）", "最低价（元/MWh）",
               "最高价（元/MWh）", "重复来源日"]
    def rows(items, kind):
        return [[kind, item.get("period"), item.get("valid_days"),
                 item.get("average_price_yuan_per_mwh"), item.get("charge_price_yuan_per_mwh"),
                 item.get("discharge_price_yuan_per_mwh"), item.get("spread_yuan_per_mwh"),
                 item.get("min_price_yuan_per_mwh"), item.get("max_price_yuan_per_mwh"),
                 item.get("multiple_source_days")] for item in items or []]
    table(workbook, "月度统计", headers, rows(payload.get("monthly"), "月度"),
          {3: "0", 4: "#,##0.00", 5: "#,##0.00", 6: "#,##0.00", 7: "#,##0.00",
           8: "#,##0.00", 9: "#,##0.00", 10: "0"})
    table(workbook, "年度统计", headers, rows(payload.get("annual"), "年度"),
          {3: "0", 4: "#,##0.00", 5: "#,##0.00", 6: "#,##0.00", 7: "#,##0.00",
           8: "#,##0.00", 9: "#,##0.00", 10: "0"})
    table(workbook, "覆盖审计", ["项目", "日期"],
          [["缺失日期", item] for item in payload.get("missing_dates", [])]
          + [["重复来源日期", item] for item in payload.get("multiple_source_dates", [])])
    return finish(workbook)


def export_operations_report_xlsx(report):
    """Export the operations report as a reviewable workbook."""
    payload = report.model_dump(mode="json") if hasattr(report, "model_dump") else dict(report)
    workbook = workbook_with_source({
        "报表类型": "运营站点层级汇总", "市场": payload.get("market"),
        "统计开始日期": payload.get("start_date"), "统计结束日期": payload.get("end_date"),
        "统计窗口（小时）": payload.get("duration_hours"), "来源模式": payload.get("source_mode"),
        "节点数": payload.get("node_count"), "有效节点": payload.get("valid_nodes"),
        "有效日合计": payload.get("total_valid_days"), "数据点合计": payload.get("total_data_points"),
        "口径": "省级汇总保留节点数、有效节点、有效日和 96 点数据量；月度价差为按有效日加权均值。",
    })
    table(workbook, "省级汇总", ["省份", "节点数", "有效节点", "有效日", "数据点"],
          [[row.get("province"), row.get("node_count"), row.get("valid_nodes"),
            row.get("valid_days"), row.get("data_points")] for row in payload.get("provinces", [])],
          {1: "0", 2: "0", 3: "0", 4: "#,##0"})
    table(workbook, "月度价差", ["月份", "节点数", "有效日", "平均价差（元/MWh）"],
          [[row.get("period"), row.get("node_count"), row.get("valid_days"),
            row.get("average_spread_yuan_per_mwh")] for row in payload.get("monthly", [])],
          {1: "0", 2: "0", 3: "#,##0.00"})
    return finish(workbook)


def export_portfolio_candidates_xlsx(result):
    """Export immutable candidate inputs and computed outputs with scale checks."""
    payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result)
    workbook = workbook_with_source({
        "报表类型": "真实节点候选项目", "快照 ID": payload.get("snapshot_id"),
        "算法版本": payload.get("algorithm_version"), "市场": payload.get("market"),
        "统计开始日期": payload.get("start_date"), "统计结束日期": payload.get("end_date"),
        "功率（MW）": payload.get("power_mw"), "容量（MWh）": payload.get("capacity_mwh"),
        "系统时长（小时）": payload.get("duration_hours"),
        "往返效率": payload.get("round_trip_efficiency"),
        "口径": "候选收入来自完整日历史价差均值；候选快照只读保存，手工修改不会覆盖原始快照。",
    })
    headers = ["项目", "节点 ID", "省份", "市场", "容量（MWh）", "单位投资（元/Wh）",
               "年净现金流（万元）", "平均价差（元/MWh）", "有效日", "来源模式"]
    table(workbook, "候选项目", headers, [[row.get("name"), row.get("node_id"), row.get("province"),
          row.get("market"), row.get("capacity_mwh"), row.get("unit_investment_yuan_wh"),
          row.get("annual_revenue_wan"), row.get("spread_yuan_per_mwh"), row.get("valid_days"),
          row.get("source_mode")] for row in payload.get("candidates", [])],
          {1: "0", 4: "#,##0.00", 5: "0.0000", 6: "#,##0.00", 7: "#,##0.00", 8: "#,##0"})
    power = payload.get("power_mw") or 0
    capacity = payload.get("capacity_mwh") or 0
    duration = payload.get("duration_hours")
    table(workbook, "规模校验", ["检查项", "值", "状态", "说明"], [
        ["功率（MW）", power, "PASS" if power > 0 else "FAIL", "输入功率必须大于 0"],
        ["容量（MWh）", capacity, "PASS" if capacity > 0 else "FAIL", "输入容量必须大于 0"],
        ["容量/功率（小时）", duration, "PASS" if duration and 0.25 <= duration <= 24 else "FAIL",
         "允许 0.25 至 24 小时；2 小时和 4 小时为常见配置而非锁定值"],
    ], {1: "#,##0.00"})
    return finish(workbook)
