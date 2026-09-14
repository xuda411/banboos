"""Task submission contract shared by API clients and workers."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1, max_length=80)
    parameters: dict = Field(default_factory=dict)
