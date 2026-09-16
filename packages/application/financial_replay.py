"""Check migration invariance with the shared financial model, not desktop parity."""
from dataclasses import asdict
from math import isfinite

from packages.domain.financial_model import FinancialParameters, calculate_financials


def replay_financial_baselines(baselines: list[dict], capacity_mwh: float = 200,
                               efficiency: float = 0.92, cycles_per_year: int = 365) -> dict:
    if not isfinite(capacity_mwh) or capacity_mwh <= 0:
        raise ValueError("回放容量必须为有限正数")
    if not isfinite(efficiency) or not 0 < efficiency <= 1:
        raise ValueError("回放效率必须在 (0, 1] 内")
    if type(cycles_per_year) is not int or not 1 <= cycles_per_year <= 1000:
        raise ValueError("年循环必须为 1–1000 的整数")
    cases = []
    for baseline in baselines:
        case = {key: baseline.get(key) for key in ("node_id", "market", "hours")}
        try:
            if baseline.get("comparison_scope") != "full_history":
                raise ValueError("日期抽样不能作为年度财务基准")
            if baseline.get("hours") not in (2, 4):
                raise ValueError("回放仅接受 2h 或 4h 基准")
            outputs, inputs = {}, {}
            for side in ("source", "staging"):
                values = baseline[side]
                if values.get("error") or values.get("valid_days", 0) <= 0:
                    raise ValueError(f"{side} 无有效年度基准")
                low = float(values["charge_price_yuan_per_mwh"])
                high = float(values["discharge_price_yuan_per_mwh"])
                if not all(isfinite(v) for v in (low, high)):
                    raise ValueError("充放电均价必须为有限数值")
                revenue = max(0, high * efficiency - low) * capacity_mwh * cycles_per_year
                parameters = FinancialParameters(power_mw=capacity_mwh / baseline["hours"],
                    capacity_mwh=capacity_mwh, annual_revenue_yuan=revenue)
                inputs[side] = asdict(parameters)
                outputs[side] = calculate_financials(parameters)
            changed = sorted(k for k in outputs["source"]
                             if outputs["source"][k] != outputs["staging"].get(k))
            case.update(status="matched" if not changed and baseline.get("matched") else "difference",
                        changed_fields=changed, inputs=inputs, results=outputs)
        except (ValueError, KeyError, TypeError) as error:
            case.update(status="unavailable", error=str(error))
        cases.append(case)
    return {"status": "matched" if cases and all(c["status"] == "matched" for c in cases)
            else "difference", "purpose": "migration_invariance_shared_model",
            "assumptions": {"capacity_mwh": capacity_mwh, "round_trip_efficiency": efficiency,
                            "cycles_per_year": cycles_per_year}, "cases": cases}
