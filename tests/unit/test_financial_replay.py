from copy import deepcopy

import pytest

from packages.application.financial_replay import replay_financial_baselines


def baseline(hours=2):
    values = dict(valid_days=365, charge_price_yuan_per_mwh=100,
                  discharge_price_yuan_per_mwh=800)
    return dict(node_id=7, market="实时", hours=hours, matched=True,
                comparison_scope="full_history", source=values, staging=deepcopy(values))


def test_replay_compares_cashflows_and_keeps_custom_size_duration():
    report = replay_financial_baselines([baseline(2), baseline(4)], capacity_mwh=120)
    assert report["status"] == "matched"
    assert [c["inputs"]["source"]["power_mw"] for c in report["cases"]] == [60, 30]
    case = report["cases"][0]
    assert case["inputs"]["source"]["annual_revenue_yuan"] == (800 * .92 - 100) * 120 * 365
    assert case["results"]["source"]["yearly"] == case["results"]["staging"]["yearly"]
    assert len(case["results"]["source"]["yearly"]) == 25


def test_replay_detects_changed_price_even_with_matched_flag():
    value = baseline()
    value["staging"]["discharge_price_yuan_per_mwh"] += 1
    result = replay_financial_baselines([value])
    assert result["status"] == "difference"
    assert "yearly" in result["cases"][0]["changed_fields"]
    assert "full_npv_yuan" in result["cases"][0]["changed_fields"]


@pytest.mark.parametrize("change", [
    {"comparison_scope": "date_sample"}, {"source": {"error": "no data"}},
    {"source": {"valid_days": 1, "charge_price_yuan_per_mwh": float("nan"),
                "discharge_price_yuan_per_mwh": 100}},
])
def test_unavailable_or_sampled_inputs_never_pass(change):
    value = baseline() | change
    report = replay_financial_baselines([value])
    assert report["status"] == "difference"
    assert report["cases"][0]["status"] == "unavailable"
    assert replay_financial_baselines([])["status"] == "difference"
