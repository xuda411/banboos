"""SQLite-backed EMS contract adapter for simulation and future deployment.

The adapter never talks to a device in ``disabled`` control mode. Simulation
dispatch creates deterministic feedback records so the dashboard can be
validated before a real station or EMS credential is available.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from packages.contracts.ems import (
    EMSDashboard,
    EMSDecisionPlan,
    EMSDecisionPlanCreate,
    EMSFeedback,
    EMSFeedbackRequest,
)


class EMSPlanNotFound(KeyError):
    pass


class EMSPlanStateError(ValueError):
    pass


class EMSService:
    def __init__(self, path: str | Path | None = None):
        configured = path or os.getenv("BANBOOS2_EMS_STATE", "var/ems/ems.sqlite3")
        self.path = Path(configured).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                "CREATE TABLE IF NOT EXISTS ems_decision_plans ("
                "plan_id TEXT PRIMARY KEY, station_id TEXT NOT NULL, status TEXT NOT NULL, "
                "delivery_status TEXT NOT NULL, operation_mode TEXT NOT NULL, control_mode TEXT NOT NULL, "
                "created_at TEXT NOT NULL, valid_from TEXT NOT NULL, valid_to TEXT NOT NULL, payload TEXT NOT NULL);"
                "CREATE INDEX IF NOT EXISTS ix_ems_plans_station_created "
                "ON ems_decision_plans(station_id, created_at);"
                "CREATE TABLE IF NOT EXISTS ems_feedback ("
                "raw_message_id TEXT PRIMARY KEY, station_id TEXT NOT NULL, plan_id TEXT, "
                "event_time TEXT NOT NULL, received_at TEXT NOT NULL, payload TEXT NOT NULL);"
                "CREATE INDEX IF NOT EXISTS ix_ems_feedback_station_event "
                "ON ems_feedback(station_id, event_time);"
            )

    def create_plan(self, request: EMSDecisionPlanCreate) -> EMSDecisionPlan:
        plan_id = uuid4()
        created = datetime.now(UTC)
        plan = EMSDecisionPlan(
            plan_id=plan_id, station_id=request.station_id, status="draft",
            delivery_status="awaiting-approval", operation_mode=self.operation_mode,
            control_mode=self.control_mode, created_at=created,
            valid_from=request.valid_from, valid_to=request.valid_to, points=request.points,
            source_run_id=request.source_run_id, algorithm_version=request.algorithm_version,
            note=request.note,
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO ems_decision_plans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(plan_id), plan.station_id, plan.status, plan.delivery_status,
                 plan.operation_mode, plan.control_mode, created.isoformat(),
                 plan.valid_from.isoformat(), plan.valid_to.isoformat(), plan.model_dump_json()),
            )
        return plan

    def get_plan(self, plan_id: UUID) -> EMSDecisionPlan:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM ems_decision_plans WHERE plan_id=?", (str(plan_id),)).fetchone()
        if not row:
            raise EMSPlanNotFound(str(plan_id))
        return EMSDecisionPlan.model_validate_json(row[0])

    def approve_plan(self, plan_id: UUID) -> EMSDecisionPlan:
        plan = self.get_plan(plan_id)
        if plan.status != "draft":
            raise EMSPlanStateError("只有草稿计划可以审批")
        return self._update(plan.model_copy(update={"status": "approved", "delivery_status": "preview-only"}))

    def dispatch_plan(self, plan_id: UUID) -> EMSDecisionPlan:
        plan = self.get_plan(plan_id)
        if plan.status != "approved":
            raise EMSPlanStateError("只有已审批计划可以下发")
        if self.control_mode == "disabled":
            return self._update(plan.model_copy(update={"delivery_status": "blocked-control-disabled"}))
        if self.operation_mode == "simulation":
            sent = self._update(plan.model_copy(update={"status": "sent", "delivery_status": "simulated"}))
            self._simulate_feedback(sent)
            return sent
        return self._update(plan.model_copy(update={"delivery_status": "adapter-not-configured"}))

    def ingest_feedback(self, request: EMSFeedbackRequest) -> EMSFeedback:
        feedback = EMSFeedback(**request.model_dump(), received_at=datetime.now(UTC))
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO ems_feedback VALUES (?, ?, ?, ?, ?, ?)",
                (feedback.raw_message_id, feedback.station_id,
                 str(feedback.plan_id) if feedback.plan_id else None,
                 feedback.event_time.isoformat(), feedback.received_at.isoformat(), feedback.model_dump_json()),
            )
        return feedback

    def dashboard(self, station_id: str) -> EMSDashboard:
        with self._connect() as connection:
            plan_row = connection.execute(
                "SELECT payload FROM ems_decision_plans WHERE station_id=? "
                "ORDER BY created_at DESC LIMIT 1", (station_id,)
            ).fetchone()
            feedback_rows = connection.execute(
                "SELECT payload FROM ems_feedback WHERE station_id=? "
                "ORDER BY event_time DESC LIMIT 200", (station_id,)
            ).fetchall()
        plan = EMSDecisionPlan.model_validate_json(plan_row[0]) if plan_row else None
        feedback = [EMSFeedback.model_validate_json(row[0]) for row in feedback_rows]
        latest = feedback[0] if feedback else None
        target = None
        if latest and plan:
            target = min(plan.points, key=lambda point: abs((point.event_time - latest.event_time).total_seconds()))
        power_deviation = latest.actual_power_mw - target.power_mw if latest and target else None
        price_deviation = None
        if latest and target and latest.actual_price_yuan_per_mwh is not None:
            price_deviation = latest.actual_price_yuan_per_mwh - target.price_yuan_per_mwh
        age = (datetime.now(UTC) - latest.received_at).total_seconds() if latest else None
        return EMSDashboard(
            station_id=station_id, generated_at=datetime.now(UTC), control_mode=self.control_mode,
            operation_mode=self.operation_mode, plan=plan, latest_feedback=latest,
            target_power_mw=target.power_mw if target else None,
            target_price_yuan_per_mwh=target.price_yuan_per_mwh if target else None,
            power_deviation_mw=power_deviation, price_deviation_yuan_per_mwh=price_deviation,
            feedback_count=len(feedback), feedback_status="no-feedback" if not latest else
            "current" if age is not None and age <= 300 else "delayed",
        )

    @property
    def control_mode(self) -> str:
        return os.getenv("BANBOOS2_CONTROL_MODE", "disabled").strip().lower()

    @property
    def operation_mode(self) -> str:
        return "simulation" if os.getenv("BANBOOS2_EMS_MODE", "simulation").strip().lower() != "adapter" else "adapter"

    def _update(self, plan: EMSDecisionPlan) -> EMSDecisionPlan:
        with self._connect() as connection:
            connection.execute(
                "UPDATE ems_decision_plans SET status=?, delivery_status=?, control_mode=?, operation_mode=?, payload=? WHERE plan_id=?",
                (plan.status, plan.delivery_status, plan.control_mode, plan.operation_mode,
                 plan.model_dump_json(), str(plan.plan_id)),
            )
        return plan

    def _simulate_feedback(self, plan: EMSDecisionPlan) -> None:
        soc = 50.0
        for index, point in enumerate(plan.points):
            soc = max(5.0, min(95.0, soc - point.power_mw * 0.0025))
            self.ingest_feedback(EMSFeedbackRequest(
                station_id=plan.station_id, plan_id=plan.plan_id, event_time=point.event_time,
                actual_power_mw=round(point.power_mw * 0.96, 4), soc_pct=round(soc, 4),
                actual_price_yuan_per_mwh=point.price_yuan_per_mwh,
                operating_state="simulated", quality_code="simulated",
                raw_message_id=f"sim:{plan.plan_id}:{index}",
            ))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection


