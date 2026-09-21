from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ImportPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str = Field(min_length=1, max_length=240)
    market: str
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=10000)


class ImportPreviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview_id: str
    source_name: str
    market: str
    status: str
    row_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    errors: list[str] = Field(default_factory=list)
    source_mode: str = "import-preview"


class ImportCommitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview_id: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    confirm: bool = False


class ImportCommitResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview_id: str
    audit_id: str
    status: str
    applied: bool
    accepted_count: int = Field(ge=0)
    control_mode: str = "disabled"
