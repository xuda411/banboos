"""Excel formulas independently rebuild cashflows from the exported task inputs."""
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from packages.domain.financial_model import MODEL_VERSION, FinancialParameters


def write_formula_audit(workbook, result, title, header):
    """Keep historic snapshots intact; expose a recalculable audit for the corrected model."""
    if result.get("model_version") != MODEL_VERSION or not result.get("input_parameters"):
        return
    required = set(FinancialParameters.__dataclass_fields__) - {"replace_year"}
    if not required.issubset(result["input_parameters"]):
        return  # Old or incomplete inputs cannot support a trustworthy independent reconstruction.
    parameters = workbook["测算参数"]
    refs = {parameters.cell(row, 4).value: f"'测算参数'!$B${row}"
            for row in range(5, parameters.max_row + 1)}
    sheet = workbook.create_sheet("公式复核")
    title(sheet, "逐年现金流公式复核", 15)
    sheet.cell(2, 1, "本页由测算参数重算；项目概览及其余明细保留任务快照。差额不为零时请在软件重新测算。年限变更须重新导出。")
    headers = ["年度", "EOL", "总收入（元）", "运维成本（元）", "折旧（元）",
               "换电池投资（元）", "贷款利息（元）", "偿还本金（元）", "剩余贷款（元）",
               "项目所得税（元）", "资本金所得税（元）", "项目现金流（元）",
               "资本金现金流（元）", "项目快照差额（元）", "资本金快照差额（元）"]
    header(sheet, 4, headers)
    p = refs.__getitem__
    initial = f"({p('capacity_mwh')}*1000000*{p('capex_yuan_per_wh')})"
    loan = f"({initial}*{p('loan_ratio')})"
    total = f"({initial}+{loan}*{p('construction_loan_rate')}*{p('construction_years')})"
    years = p("operation_years")
    replace_year, replace_capex = p("replace_year"), p("replace_capex_yuan")
    for row in range(5, len(result["yearly"]) + 5):
        year = row - 4
        previous = loan if year == 1 else f"I{row - 1}"
        formulas = {
            "A": str(year),
            "B": f"{p('first_year_eol')}+({p('final_eol')}-{p('first_year_eol')})*(A{row}-1)/MAX(1,{years}-1)",
            "C": f"({p('annual_revenue_yuan')}+{p('capacity_fee_yuan')}+{p('subsidy_yuan')})*B{row}+{p('capacity_lease_yuan')}+{p('primary_frequency_yuan')}+{p('secondary_frequency_yuan')}",
            "D": f"{total}*{p('om_rate')}*(1+{p('om_growth')})^(A{row}-1)",
            "E": f"{initial}*(1-{p('residual_rate')})/{years}+IF(AND({replace_year}>0,A{row}>={replace_year}),{replace_capex}*(1-{p('residual_rate')})/MAX(1,{years}-{replace_year}+1),0)",
            "F": f"IF(A{row}={replace_year},{replace_capex},0)",
            "G": f"IF(A{row}<={p('loan_years')},{previous}*{p('loan_rate')},0)",
            "H": f"IF(A{row}={years},{previous},IF(A{row}<={p('loan_years')},{loan}/{p('loan_years')},0))",
            "I": f"MAX(0,{previous}-H{row})",
            "J": f"MAX(0,(C{row}-D{row}-E{row})*{p('income_tax_rate')})",
            "K": f"MAX(0,(C{row}-D{row}-E{row}-G{row})*{p('income_tax_rate')})",
            "L": f"C{row}-D{row}-J{row}-F{row}",
            "M": f"C{row}-D{row}-F{row}-G{row}-H{row}-K{row}",
            "N": f"L{row}-'年度现金流'!N{row}",
            "O": f"M{row}-'年度现金流'!O{row}",
        }
        for column, formula in formulas.items():
            cell = sheet[f"{column}{row}"]
            cell.value = year if column == "A" else f"={formula}"
            cell.font = Font(name="Microsoft YaHei", size=10, color="0B6B53" if "'" in formula else "173B35")
            cell.number_format = "0.00%" if column == "B" else "#,##0.00;[Red](#,##0.00);0.00"
        sheet[f"A{row}"].number_format = '0" 年"'
    sheet.auto_filter.ref = f"A4:{get_column_letter(len(headers))}{sheet.max_row}"
    sheet.conditional_formatting.add(f"N5:O{sheet.max_row}", CellIsRule(
        operator="notBetween", formula=["-0.01", "0.01"],
        fill=PatternFill("solid", fgColor="FCE4D6")))
