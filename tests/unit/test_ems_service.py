from datetime import UTC, datetime, timedelta
from uuid import uuid4

from packages.application.ems_service import EMSService
from packages.contracts.ems import EMSDecisionPlanCreate, EMSDecisionPoint, EMSFeedbackRequest


def _request():
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    return EMSDecisionPlanCreate(
        station_id="demo-station", valid_from=start, valid_to=start + timedelta(hours=1),
        points=[
            EMSDecisionPoint(event_time=start, power_mw=-20, price_yuan_per_mwh=180, mode="charge"),
            EMSDecisionPoint(event_time=start + timedelta(minutes=15), power_mw=0, price_yuan_per_mwh=320, mode="idle"),
            EMSDecisionPoint(event_time=start + timedelta(minutes=30), power_mw=30, price_yuan_per_mwh=520, mode="discharge"),
        ],
    )


def test_simulation_plan_approval_dispatch_and_dashboard(tmp_path, monkeypatch):
    monkeypatch.setenv("BANBOOS2_CONTROL_MODE", "simulation")
    service = EMSService(tmp_path / "ems.sqlite3")
    plan = service.create_plan(_request())
    assert plan.status == "draft"
    plan = service.approve_plan(plan.plan_id)
    assert plan.status == "approved"
    plan = service.dispatch_plan(plan.plan_id)
    assert plan.status == "sent"
    assert plan.delivery_status == "simulated"
    dashboard = service.dashboard("demo-station")
    assert dashboard.plan.plan_id == plan.plan_id
    assert dashboard.feedback_count == 3
    assert dashboard.latest_feedback.operating_state == "simulated"
    assert dashboard.power_deviation_mw is not None


def test_disabled_control_never_sends_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("BANBOOS2_CONTROL_MODE", "disabled")
    service = EMSService(tmp_path / "ems.sqlite3")
    plan = service.approve_plan(service.create_plan(_request()).plan_id)
    result = service.dispatch_plan(plan.plan_id)
    assert result.status == "approved"
    assert result.delivery_status == "blocked-control-disabled"
    assert service.dashboard("demo-station").feedback_count == 0


def test_feedback_is_idempotent(tmp_path):
    service = EMSService(tmp_path / "ems.sqlite3")
    message_id = str(uuid4())
    request = EMSFeedbackRequest(
        station_id="demo-station", event_time=datetime.now(UTC), actual_power_mw=3,
        soc_pct=50, operating_state="idle", raw_message_id=message_id,
    )
    service.ingest_feedback(request)
    service.ingest_feedback(request)
    assert service.dashboard("demo-station").feedback_count == 1
