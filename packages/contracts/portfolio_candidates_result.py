from pydantic import BaseModel, ConfigDict, Field

from packages.contracts.portfolio_candidates import PortfolioCandidate


class PortfolioCandidatesResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market: str
    power_mw: float = Field(gt=0)
    capacity_mwh: float = Field(gt=0)
    duration_hours: float = Field(gt=0)
    round_trip_efficiency: float = Field(gt=0, le=1)
    start_date: str
    end_date: str
    snapshot_id: str
    algorithm_version: str
    candidates: list[PortfolioCandidate] = Field(default_factory=list)
    candidate_count: int = Field(default=0, ge=0)
