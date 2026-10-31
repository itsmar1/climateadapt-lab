"""Scenario worker and row assembly (P11).

``run_scenario_job`` builds the ``JobStore`` callable for one scenario: it
re-reads the stored input, runs the fixed agent pipeline, and persists the
terminal outputs. A scenario deleted mid-run is left deleted (the worker
checks before writing). Results are stored by scenario id; the job result
itself stays a small pointer — full data lives behind the scenario endpoints.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from climateadapt.agent.schemas import AgentConfig, AgentScenario
from climateadapt.agent.workflow import run_agent
from climateadapt.api.schemas_scenarios import ScenarioDetail, ScenarioSummary
from climateadapt.api.store import ScenarioStore

logger = logging.getLogger(__name__)


def _dump(model: Any) -> dict[str, Any] | None:
    return model.model_dump(mode="json") if model is not None else None


def run_scenario_job(
    scenario_id: str,
    *,
    store: ScenarioStore,
    deps: Any,
    provider: Any,
    config: AgentConfig | None = None,
) -> Callable[[Callable[[int, int], None]], dict[str, Any]]:
    """Build the background callable for one scenario run (never raises)."""

    def run(progress: Callable[[int, int], None]) -> dict[str, Any]:
        del progress  # stage-level progress lives on the trace, not the job
        record = store.get(scenario_id)
        if record is None:
            return {"scenario_id": scenario_id, "status": "deleted"}
        scenario = AgentScenario.model_validate(record["scenario"])
        store.mark_running(scenario_id)
        try:
            result = run_agent(scenario, deps, provider, config or AgentConfig())
        except Exception as exc:  # defensive: run_agent is total by design
            logger.exception("Scenario %s crashed outside the pipeline", scenario_id)
            if store.exists(scenario_id):
                store.save_result(
                    scenario_id,
                    status="failed",
                    bundle=None,
                    ranking=None,
                    report=None,
                    trace=None,
                    problems=[f"[internal] Scenario run failed: {exc}"],
                    warnings=[],
                )
            return {"scenario_id": scenario_id, "status": "failed"}
        if not store.exists(scenario_id):
            return {"scenario_id": scenario_id, "status": "deleted"}
        store.save_result(
            scenario_id,
            status=result.status,
            bundle=_dump(result.bundle),
            ranking=_dump(result.ranking),
            report=_dump(result.report),
            trace=_dump(result.trace),
            problems=result.problems,
            warnings=result.warnings,
        )
        return {"scenario_id": scenario_id, "status": result.status}

    return run


def to_summary(row: dict[str, Any]) -> ScenarioSummary:
    scenario = row["scenario"]
    return ScenarioSummary.model_validate(
        {
            "scenario_id": row["scenario_id"],
            "job_id": row["job_id"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "latitude": scenario["latitude"],
            "longitude": scenario["longitude"],
            "target_end_month": scenario["target_end_month"],
            "query": scenario["query"],
        }
    )


def to_detail(row: dict[str, Any]) -> ScenarioDetail:
    return ScenarioDetail.model_validate(
        {
            "scenario_id": row["scenario_id"],
            "job_id": row["job_id"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "scenario": row["scenario"],
            "bundle": row["bundle"],
            "ranking": row["ranking"],
            "report": row["report"],
            "trace": row["trace"],
            "problems": row["problems"],
            "warnings": row["warnings"],
        }
    )
