"""Append-only sidecar decisions, scoped to immutable source evidence."""
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from packages.contracts.price_conflicts import PriceConflictApplyRequest, PriceConflictReviewRequest


class ReviewConflict(ValueError):
    pass


class PriceConflictReviewStore:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv("BANBOOS2_CONFLICT_REVIEW_DB", "var/data-quality/price-conflict-review.sqlite3"))

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("""CREATE TABLE IF NOT EXISTS quality_review_events_v2 (
            id INTEGER PRIMARY KEY, evidence_id TEXT NOT NULL, revision INTEGER NOT NULL,
            request_key TEXT NOT NULL UNIQUE, request_json TEXT NOT NULL,
            status TEXT NOT NULL, reviewer TEXT NOT NULL, decision_reason TEXT NOT NULL,
            reviewed_at TEXT NOT NULL, evidence_json TEXT NOT NULL,
            UNIQUE(evidence_id,revision))""")
        columns = {row[1] for row in db.execute("PRAGMA table_info(quality_review_events_v2)")}
        for name in ("tenant_id", "request_id"):
            if name not in columns:
                db.execute(f"ALTER TABLE quality_review_events_v2 ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
        db.execute("""CREATE TABLE IF NOT EXISTS quality_apply_intents (
            intent_id TEXT PRIMARY KEY, source_row_id INTEGER NOT NULL, evidence_id TEXT NOT NULL,
            expected_revision INTEGER NOT NULL, request_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL, applied INTEGER NOT NULL DEFAULT 0, actor TEXT NOT NULL,
            tenant_id TEXT NOT NULL, request_id TEXT NOT NULL, decision_reason TEXT NOT NULL,
            created_at TEXT NOT NULL, evidence_json TEXT NOT NULL)""")
        db.commit()
        return db

    def overlay(self, conflict, tenant_id=None):
        tenant_id = tenant_id or os.getenv("BANBOOS2_TENANT_ID", "staging-tenant")
        with closing(self._connect()) as db:
            rows = db.execute("SELECT * FROM quality_review_events_v2 WHERE evidence_id=? AND tenant_id=? ORDER BY revision", (conflict.evidence_id, tenant_id)).fetchall()
        events = [dict(revision=r["revision"], status=r["status"], reviewer=r["reviewer"],
                       decision_reason=r["decision_reason"], reviewed_at=r["reviewed_at"],
                       tenant_id=r["tenant_id"], request_id=r["request_id"]) for r in rows]
        if not events:
            last = None
        else:
            last = events[-1]
        updates = {}
        if events:
            updates.update(dict(review_status=last["status"], revision=last["revision"],
                review_actor=last["reviewer"], review_note=last["decision_reason"],
                reviewed_at=datetime.fromisoformat(last["reviewed_at"]), events=events))
        with closing(self._connect()) as db:
            intent = db.execute("SELECT intent_id,status,applied,expected_revision FROM quality_apply_intents WHERE evidence_id=? AND tenant_id=? ORDER BY created_at DESC LIMIT 1", (conflict.evidence_id, tenant_id)).fetchone()
        if intent:
            updates.update(apply_status=(intent["status"] if last and last["status"] == "approved" and last["revision"] == intent["expected_revision"] else "stale"), apply_intent_id=intent["intent_id"], applied=False)
        if not updates:
            return conflict
        return conflict.model_copy(update=updates)

    def review(self, conflict, request: PriceConflictReviewRequest, tenant_id: str = "staging-tenant",
               request_id: str = "local-review"):
        if conflict.evidence_id != request.evidence_id:
            raise ReviewConflict("EVIDENCE_CHANGED: 来源证据已变化，请重新读取详情")
        status = {"confirm_canonical": "approved", "reject_candidate": "rejected",
                  "defer": "deferred", "reopen": "pending"}[request.action]
        if status == "approved" and conflict.canonical_source_row_id is None:
            raise ReviewConflict("NO_CANONICAL: 没有可确认的临时 Canonical")
        encoded = json.dumps(request.model_dump(), sort_keys=True, ensure_ascii=False)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT request_json,evidence_id,tenant_id FROM quality_review_events_v2 WHERE request_key=?", (request.idempotency_key,)).fetchone()
            if previous:
                if previous["request_json"] != encoded or previous["evidence_id"] != conflict.evidence_id or previous["tenant_id"] != tenant_id:
                    raise ReviewConflict("IDEMPOTENCY_CONFLICT: 幂等键已用于其他请求")
            else:
                foreign = db.execute("SELECT 1 FROM quality_review_events_v2 WHERE evidence_id=? AND tenant_id!=?", (conflict.evidence_id, tenant_id)).fetchone()
                if foreign:
                    raise ReviewConflict("TENANT_CONFLICT: 审计归属租户不匹配")
                revision = db.execute("SELECT COALESCE(MAX(revision),0) FROM quality_review_events_v2 WHERE evidence_id=? AND tenant_id=?", (conflict.evidence_id, tenant_id)).fetchone()[0]
                if request.expected_revision != revision:
                    raise ReviewConflict("STALE_REVIEW: 复核版本已变化，请刷新")
                db.execute("INSERT INTO quality_review_events_v2(evidence_id,revision,request_key,request_json,status,reviewer,decision_reason,reviewed_at,evidence_json,tenant_id,request_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (conflict.evidence_id, revision+1, request.idempotency_key, encoded, status,
                     request.actor, request.note, datetime.now(UTC).isoformat(), conflict.model_dump_json(), tenant_id, request_id))
        return self.overlay(conflict, tenant_id)

    def apply_intent(self, conflict, request: PriceConflictApplyRequest, actor: str,
                     tenant_id: str, request_id: str):
        if conflict.evidence_id != request.evidence_id:
            raise ReviewConflict("EVIDENCE_CHANGED: 来源证据已变化，请重新读取详情")
        now = datetime.now(UTC).isoformat()
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT status,revision FROM quality_review_events_v2 WHERE evidence_id=? AND tenant_id=? ORDER BY revision DESC LIMIT 1", (conflict.evidence_id, tenant_id)).fetchone()
            if not current or current["status"] != "approved":
                raise ReviewConflict("REVIEW_NOT_APPROVED: 只有 approved 复核结果可以申请应用")
            if current["revision"] != request.expected_revision:
                raise ReviewConflict("STALE_REVIEW: 复核版本已变化，请刷新")
            existing = db.execute("SELECT * FROM quality_apply_intents WHERE request_key=?", (request.idempotency_key,)).fetchone()
            if existing:
                if (existing["evidence_id"] != request.evidence_id or existing["actor"] != actor
                        or existing["tenant_id"] != tenant_id or existing["decision_reason"] != request.note
                        or existing["expected_revision"] != request.expected_revision
                        or existing["source_row_id"] != conflict.source_row_id):
                    raise ReviewConflict("IDEMPOTENCY_CONFLICT: 应用幂等键已用于其他请求")
                return dict(intent_id=existing["intent_id"], source_row_id=existing["source_row_id"],
                            evidence_id=existing["evidence_id"], review_status="approved",
                            apply_status=existing["status"], applied=bool(existing["applied"]),
                            actor=existing["actor"], tenant_id=existing["tenant_id"],
                            request_id=existing["request_id"], decision_reason=existing["decision_reason"],
                            created_at=datetime.fromisoformat(existing["created_at"]))
            intent_id = uuid4().hex
            db.execute("INSERT INTO quality_apply_intents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (intent_id, conflict.source_row_id, request.evidence_id, request.expected_revision,
                        request.idempotency_key, "pending_apply", 0, actor, tenant_id, request_id,
                        request.note, now, conflict.model_dump_json()))
        return dict(intent_id=intent_id, source_row_id=conflict.source_row_id,
                    evidence_id=request.evidence_id, review_status="approved",
                    apply_status="pending_apply", applied=False, actor=actor,
                    tenant_id=tenant_id, request_id=request_id, decision_reason=request.note,
                    created_at=datetime.fromisoformat(now))


def evidence_key(metadata, row, candidates):
    row_core = {key: row.get(key) for key in ("source_row_id", "node_id", "run_date", "market",
                                               "payload_sha256", "canonical_source_row_id", "selection_rule")}
    candidate_core = [{key: item.get(key) for key in ("source_row_id", "payload_sha256")}
                      for item in candidates]
    payload = json.dumps([str(metadata), row_core, candidate_core], sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()
