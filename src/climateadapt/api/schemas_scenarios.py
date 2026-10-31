"""Versioned scenario API contracts (P11).

Every response carries ``version`` (currently 1) so the React frontend can
detect schema drift. The detail response separates deterministic results
(``bundle``), ``ranking``, the validated-or-fallback ``report``, and the
auditable ``trace``; limitations and provenance live inside the report and the
bundle entries, exactly where P05/P08/P09 put them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from climateadapt.agent.schemas import AgentScenario
from climateadapt.agent.trace import RunTrace
from climateadapt.llm.report import Report
from climateadapt.recommend.schema import RecommendationResponse
from climateadapt.schemas_era5 import EnvironmentalBundleResponse

SCENARIO_API_VERSION = 1
"""Response contract version. Bump deliberately; the frontend gates on it."""

ScenarioStatus = Literal["queued", "running", "complete", "partial", "failed"]


class ScenarioCreated(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = SCENARIO_API_VERSION
    scenario_id: str
    job_id: str
    status: ScenarioStatus
    status_url: str
    scenario_url: str


class ScenarioSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = SCENARIO_API_VERSION
    scenario_id: str
    job_id: str
    status: ScenarioStatus
    created_at: datetime
    updated_at: datetime
    latitude: float
    longitude: float
    target_end_month: str
    query: str


class ScenarioList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = SCENARIO_API_VERSION
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    items: list[ScenarioSummary]


class ScenarioDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = SCENARIO_API_VERSION
    scenario_id: str
    job_id: str
    status: ScenarioStatus
    created_at: datetime
    updated_at: datetime
    scenario: AgentScenario
    bundle: EnvironmentalBundleResponse | None
    ranking: RecommendationResponse | None
    report: Report | None
    trace: RunTrace | None
    problems: list[str]
    warnings: list[str]
