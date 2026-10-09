from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PriceConflict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_row_id: int = Field(gt=0)
    node_id: int = Field(gt=0)
    run_date: date
    market: str
    conflict_type: str
    payload_sha256: str
    source_file: str | None = None
    canonical_source_row_id: int | None = None
    selection_rule: str
    processing_state: str
    decision_reason: str | None = None
    evidence_id: str = ""
    revision: int = 0
    applied: bool = False
    apply_status: str = "not_requested"
    apply_intent_id: str | None = None
    candidates: list[dict] = Field(default_factory=list)
    candidate_source_ids: list[int] = Field(default_factory=list)
    candidate_hashes: list[str] = Field(default_factory=list)
    events: list[dict] = Field(default_factory=list)
    review_status: str = "pending"
    review_actor: str | None = None
    review_note: str | None = None
    reviewed_at: datetime | None = None


class PriceConflictReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["confirm_canonical", "reject_candidate", "defer", "reopen"]
    actor: str = Field(min_length=1, max_length=120)
    note: str = Field(min_length=1, max_length=1000)
    evidence_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=120)

    @field_validator("actor", "note", "idempotency_key")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("reviewer and decision reason must not be blank")
        return value.strip()


class PriceConflictApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_revision: int = Field(ge=1)
    note: str = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=120)

    @field_validator("note", "idempotency_key")
    @classmethod
    def nonblank_apply(cls, value):
        if not value.strip():
            raise ValueError("decision reason and idempotency key must not be blank")
        return value.strip()


class PriceConflictApplyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_id: str
    source_row_id: int
    evidence_id: str
    review_status: str
    apply_status: str
    applied: bool = False
    actor: str
    tenant_id: str
    request_id: str
    decision_reason: str
    created_at: datetime
