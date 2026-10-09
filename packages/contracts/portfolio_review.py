from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PortfolioReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["submit", "approve", "reject", "archive"]
    actor: str = Field(min_length=1, max_length=120, pattern=r"\S")
    note: str = Field(default="", max_length=1000)
    expected_status: str | None = Field(default=None, max_length=20)


class PortfolioReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: Literal["draft", "pending", "approved", "rejected", "archived"]
    actor: str | None = None
    note: str = ""
    updated_at: str | None = None
    history: list[dict] = Field(default_factory=list)
