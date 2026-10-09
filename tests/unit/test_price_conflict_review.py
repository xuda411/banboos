from datetime import date

import pytest

from packages.application.price_conflict_review import (
    PriceConflictReviewStore,
    ReviewConflict,
    evidence_key,
)
from packages.contracts.price_conflicts import PriceConflict, PriceConflictReviewRequest


def make_conflict():
    return PriceConflict(source_row_id=9, node_id=1, run_date=date(2026, 1, 1), market="实时",
                         conflict_type="multiple_source", payload_sha256="a" * 64,
                         evidence_id="b" * 64, source_file="second.csv", canonical_source_row_id=8,
                         selection_rule="lowest_source_id_provisional",
                         processing_state="manual_review_required")


def request(action="confirm_canonical", key="request-001", revision=0):
    return PriceConflictReviewRequest(action=action, actor="auditor", note="核对来源后决定",
                                      evidence_id="b" * 64, expected_revision=revision,
                                      idempotency_key=key)


def test_conflict_review_is_append_only_and_idempotent(tmp_path):
    store = PriceConflictReviewStore(tmp_path / "review.sqlite3")
    conflict = make_conflict()
    reviewed = store.review(conflict, request())
    assert reviewed.review_status == "approved"
    assert reviewed.revision == 1
    assert store.review(conflict, request()).revision == 1
    with pytest.raises(ReviewConflict, match="IDEMPOTENCY_CONFLICT"):
        store.review(conflict, request(action="reject_candidate"))


def test_review_rejects_stale_revision_and_changed_evidence(tmp_path):
    store = PriceConflictReviewStore(tmp_path / "review.sqlite3")
    conflict = make_conflict()
    store.review(conflict, request())
    with pytest.raises(ReviewConflict, match="STALE_REVIEW"):
        store.review(conflict, request(key="request-002", revision=0))
    with pytest.raises(ReviewConflict, match="EVIDENCE_CHANGED"):
        store.review(conflict, request(key="request-003").model_copy(update={"evidence_id": "c" * 64}))


def test_review_requires_reason_and_cannot_approve_without_canonical(tmp_path):
    with pytest.raises(ValueError):
        PriceConflictReviewRequest(action="defer", actor="auditor", note="", evidence_id="b" * 64,
                                   expected_revision=0, idempotency_key="request-004")
    store = PriceConflictReviewStore(tmp_path / "review.sqlite3")
    conflict = make_conflict().model_copy(update={"canonical_source_row_id": None})
    with pytest.raises(ReviewConflict, match="NO_CANONICAL"):
        store.review(conflict, request())


def test_evidence_id_changes_when_candidate_hash_set_changes():
    row = make_conflict().model_dump()
    first = evidence_key("dataset-a", row, [{"source_row_id": 8, "payload_sha256": "c" * 64}])
    second = evidence_key("dataset-a", row, [{"source_row_id": 8, "payload_sha256": "d" * 64}])
    assert first != second


def test_apply_gate_idempotency_tenant_and_reopen(tmp_path):
    from packages.contracts.price_conflicts import PriceConflictApplyRequest
    store = PriceConflictReviewStore(tmp_path / "review.sqlite3")
    conflict = make_conflict()
    apply = PriceConflictApplyRequest(evidence_id=conflict.evidence_id, expected_revision=1,
                                     note="stage only", idempotency_key="apply-test-001")
    with pytest.raises(ReviewConflict, match="REVIEW_NOT_APPROVED"):
        store.apply_intent(conflict, apply, "auditor", "staging-tenant", "req-1")
    store.review(conflict, request(), "staging-tenant", "review-request-1")
    first = store.apply_intent(conflict, apply, "auditor", "staging-tenant", "req-2")
    assert first["applied"] is False
    assert store.apply_intent(conflict, apply, "auditor", "staging-tenant", "req-3") == first
    with pytest.raises(ReviewConflict, match="IDEMPOTENCY_CONFLICT"):
        store.apply_intent(conflict, apply.model_copy(update={"note": "changed"}), "auditor", "staging-tenant", "req-4")
    with pytest.raises(ReviewConflict, match="REVIEW_NOT_APPROVED"):
        store.apply_intent(conflict, apply, "auditor", "other-tenant", "req-5")
    assert store.overlay(conflict, "other-tenant").review_status == "pending"
    store.review(conflict, request("reopen", "reopen-test-001", 1))
    assert store.overlay(conflict).apply_status == "stale"
    with pytest.raises(ReviewConflict, match="REVIEW_NOT_APPROVED"):
        store.apply_intent(conflict, apply, "auditor", "staging-tenant", "req-6")
    event = store.overlay(conflict).events[0]
    assert event["tenant_id"] == "staging-tenant"
    assert event["request_id"] == "review-request-1"
