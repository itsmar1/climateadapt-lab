"""Offline tests for the scenario API and SQLite persistence. No network."""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from climateadapt.agent import workflow
from climateadapt.agent.schemas import AgentDeps
from climateadapt.agent.tools import RetrievalToolResult
from climateadapt.api.dependencies import (
    UnavailableProvider,
    get_agent_deps,
    get_job_store,
    get_llm_provider,
    get_scenario_store,
)
from climateadapt.api.jobs import JobStore
from climateadapt.api.main import create_app
from climateadapt.api.scenarios import run_scenario_job
from climateadapt.api.store import SCHEMA_VERSION, SqliteScenarioStore
from climateadapt.config import get_settings
from climateadapt.data.errors import OutsideCoverageError
from climateadapt.llm.provider import FakeProvider
from climateadapt.rag.models import RetrievedChunk
from climateadapt.recommend.schema import RecommendationResponse
from climateadapt.schemas_era5 import EnvironmentalBundleResponse
from recommend_helpers import make_catalog
from report_helpers import (
    make_llm_bundle,
    make_llm_chunks,
    make_llm_context,
    make_llm_manifest,
    make_llm_pages,
    make_llm_ranking,
    valid_report_dict,
)

TERMINAL = ("complete", "partial", "failed")


def scenario_payload(**overrides):
    body = {
        "latitude": 30.43,
        "longitude": -9.61,
        "target_end_month": "2024-03",
        "timescale_months": 3,
        "reference_start_year": 1991,
        "reference_end_year": 2020,
        "min_reference_years": 30,
        "land_fallback_max_km": 15.0,
        "query": "deficit irrigation scheduling",
        "top_k": 5,
        "exclude_reference": True,
        "crop": "wheat",
        "has_water_source": True,
        "has_irrigation_equipment": True,
        "production_system": "irrigated",
        "season": "2024-03",
    }
    body.update(overrides)
    return body


def poll_scenario(client, scenario_id, timeout=60.0):
    deadline = time.monotonic() + timeout
    while True:
        response = client.get(f"/v1/scenarios/{scenario_id}")
        assert response.status_code == 200
        detail = response.json()
        if detail["status"] in TERMINAL:
            return detail
        assert time.monotonic() < deadline, "scenario never reached a terminal state"
        time.sleep(0.05)


@pytest.fixture
def scenario_api(tmp_path, monkeypatch):
    """Build stubbed scenario apps: synthetic tools, scripted provider, tmp SQLite."""
    chunks = make_llm_chunks()
    retrieved = chunks[:2]
    resources = []

    def build(
        script=None,
        fail_bundle=False,
        fail_ranking=False,
        db_name="scenarios.sqlite3",
        max_jobs=1000,
        provider=None,
    ):
        def fake_bundle(*args, **kwargs):
            if fail_bundle:
                raise OutsideCoverageError("68N is outside CHIRPS coverage.")
            return EnvironmentalBundleResponse.model_validate(make_llm_bundle())

        def fake_ranking(*args, **kwargs):
            if fail_ranking:
                raise KeyError("ghost-doc")
            return RecommendationResponse.model_validate(make_llm_ranking())

        hits = [
            RetrievedChunk(
                chunk=chunk, score=1.0 - 0.1 * rank, rank=rank + 1,
                component_ranks={"bm25": rank + 1},
                component_scores={"bm25": 1.0 - 0.1 * rank},
            )
            for rank, chunk in enumerate(retrieved)
        ]

        monkeypatch.setattr(workflow, "get_environmental_bundle", fake_bundle)
        monkeypatch.setattr(workflow, "rank_adaptation_options", fake_ranking)
        monkeypatch.setattr(
            workflow, "retrieve_evidence",
            lambda *a, **k: RetrievalToolResult(query="q", retriever="bm25", hits=hits),
        )
        ctx = make_llm_context(chunks=retrieved)
        drafts = script if script is not None else [
            json.dumps(valid_report_dict(ctx)) for _ in range(6)
        ]
        if provider is None:
            # Build a scripted provider without touching the network.
            from climateadapt.llm.provider import LLMResponse

            provider = FakeProvider(
                [
                    LLMResponse(content=item, finish_reason="stop", latency_ms=0.0,
                                attempts=1)
                    if isinstance(item, str)
                    else item
                    for item in drafts
                ]
            )
        deps = AgentDeps(
            chirps=None,
            era5=None,
            chunks=chunks,
            manifest=make_llm_manifest(),
            pages_by_doc=make_llm_pages(),
            catalog=make_catalog(),
        )
        jobs = JobStore(max_jobs=max_jobs)
        db = SqliteScenarioStore(tmp_path / db_name)
        resources.extend([jobs, db])
        app = create_app()
        app.dependency_overrides[get_agent_deps] = lambda: deps
        app.dependency_overrides[get_llm_provider] = lambda: provider
        app.dependency_overrides[get_job_store] = lambda: jobs
        app.dependency_overrides[get_scenario_store] = lambda: db
        return TestClient(app), provider, db, jobs, deps

    yield build
    for resource in resources:
        if isinstance(resource, JobStore):
            resource.shutdown()
        else:
            resource.close()


def test_lifecycle_create_poll_retrieve_and_list(scenario_api):
    client, _, _, _, _ = scenario_api()

    created = client.post("/v1/scenarios", json=scenario_payload())
    assert created.status_code == 202
    body = created.json()
    assert body["version"] == 1
    scenario_id, job_id = body["scenario_id"], body["job_id"]
    assert body["status"] == "queued"
    assert body["scenario_url"] == f"/v1/scenarios/{scenario_id}"
    assert body["status_url"] == f"/v1/jobs/{job_id}"

    detail = poll_scenario(client, scenario_id)
    assert detail["status"] == "complete"
    assert detail["version"] == 1
    assert [e["indicator"] for e in detail["bundle"]["entries"]] == [
        "chirps_spi", "era5_temperature_anomaly",
    ]
    assert [o["intervention_id"] for o in detail["ranking"]["ranked"]] == ["test-drip"]
    assert detail["report"]["fallback"] is False
    assert [s["name"] for s in detail["trace"]["stages"]] == [
        "validate_inputs", "bundle", "retrieval", "ranking",
        "draft", "validate", "finalize",
    ]
    assert detail["problems"] == []
    assert detail["scenario"]["query"] == "deficit irrigation scheduling"

    job = client.get(f"/v1/jobs/{job_id}")
    assert job.json()["status"] == "succeeded"
    assert job.json()["result"] == {"scenario_id": scenario_id, "status": "complete"}

    listing = client.get("/v1/scenarios")
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["scenario_id"] == scenario_id


def test_failed_run_is_stored_with_errors(scenario_api):
    client, _, _, _, _ = scenario_api(fail_bundle=True)

    created = client.post("/v1/scenarios", json=scenario_payload())
    detail = poll_scenario(client, created.json()["scenario_id"])

    assert detail["status"] == "failed"
    assert detail["report"] is None
    assert detail["bundle"] is None
    assert detail["ranking"] is None
    assert detail["trace"] is not None  # the trace explains the failure
    assert any(p.startswith("[outside_coverage]") for p in detail["problems"])

    job = client.get(f"/v1/jobs/{created.json()['job_id']}")
    assert job.json()["status"] == "succeeded"  # the job ran; the run failed
    assert job.json()["result"]["status"] == "failed"


def test_ranking_failure_is_stored_as_failed(scenario_api):
    client, _, _, _, _ = scenario_api(fail_ranking=True)

    created = client.post("/v1/scenarios", json=scenario_payload())
    detail = poll_scenario(client, created.json()["scenario_id"])

    assert detail["status"] == "failed"
    assert detail["bundle"] is not None  # deterministic outputs kept
    assert detail["ranking"] is None
    assert any(p.startswith("[ranking-error]") for p in detail["problems"])


def test_persistence_across_app_restarts(scenario_api):
    client, _, db, _, _ = scenario_api(db_name="restart.sqlite3")
    created = client.post("/v1/scenarios", json=scenario_payload())
    scenario_id = created.json()["scenario_id"]
    assert poll_scenario(client, scenario_id)["status"] == "complete"
    db.close()

    client2, _, _, _, _ = scenario_api(db_name="restart.sqlite3")
    detail = client2.get(f"/v1/scenarios/{scenario_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "complete"
    assert detail.json()["report"]["fallback"] is False
    assert client2.get("/v1/scenarios").json()["total"] == 1


def test_validation_errors_use_the_shared_shape_without_echo(scenario_api):
    client, _, _, _, _ = scenario_api()

    response = client.post(
        "/v1/scenarios",
        json=scenario_payload(latitude="north", target_end_month="2024-13"),
    )
    assert response.status_code == 422
    body = response.json()
    assert all(set(item) == {"loc", "msg", "type"} for item in body["detail"])
    assert "north" not in response.text


def test_history_pagination_newest_first(scenario_api):
    client, _, _, _, _ = scenario_api()
    ids = []
    for _ in range(3):
        created = client.post("/v1/scenarios", json=scenario_payload())
        ids.append(created.json()["scenario_id"])
    for scenario_id in ids:
        assert poll_scenario(client, scenario_id)["status"] == "complete"

    page1 = client.get("/v1/scenarios", params={"limit": 2, "offset": 0}).json()
    assert page1["total"] == 3
    assert [item["scenario_id"] for item in page1["items"]] == [ids[2], ids[1]]
    page2 = client.get("/v1/scenarios", params={"limit": 2, "offset": 2}).json()
    assert [item["scenario_id"] for item in page2["items"]] == [ids[0]]
    assert client.get("/v1/scenarios", params={"limit": 0}).status_code == 422


def test_delete_removes_and_unknown_ids_404(scenario_api):
    client, _, _, _, _ = scenario_api()
    created = client.post("/v1/scenarios", json=scenario_payload())
    scenario_id = created.json()["scenario_id"]
    assert poll_scenario(client, scenario_id)["status"] == "complete"

    assert client.delete(f"/v1/scenarios/{scenario_id}").status_code == 204
    assert client.get(f"/v1/scenarios/{scenario_id}").status_code == 404
    assert client.get("/v1/scenarios").json()["total"] == 0

    missing = client.get("/v1/scenarios/does-not-exist")
    assert missing.status_code == 404
    assert missing.json() == {
        "detail": [{"loc": [], "msg": "Unknown scenario id.", "type": "scenario_not_found"}]
    }
    assert client.delete("/v1/scenarios/does-not-exist").status_code == 404


def test_worker_skips_a_deleted_scenario(scenario_api):
    _, provider, db, _, deps = scenario_api()

    assert (
        run_scenario_job("ghost-id", store=db, deps=deps, provider=provider)(
            lambda completed, total: None
        )
        == {"scenario_id": "ghost-id", "status": "deleted"}
    )


def test_unavailable_provider_yields_a_labelled_partial(scenario_api):
    client, _, _, _, _ = scenario_api(provider=UnavailableProvider())

    created = client.post("/v1/scenarios", json=scenario_payload())
    detail = poll_scenario(client, created.json()["scenario_id"])

    assert detail["status"] == "partial"
    assert detail["report"]["fallback"] is True
    assert any(p.startswith("[provider-auth]") for p in detail["problems"])


def test_cors_preflight_allows_delete_on_scenarios(scenario_api):
    client, _, _, _, _ = scenario_api()

    response = client.options(
        "/v1/scenarios/abc",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "DELETE",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_oversized_body_returns_413(scenario_api, monkeypatch):
    monkeypatch.setenv("CLIMATEADAPT_API_MAX_BODY_BYTES", "1024")
    get_settings.cache_clear()
    try:
        client, _, _, _, _ = scenario_api()
        response = client.post(
            "/v1/scenarios", json=scenario_payload(query="q", pad="y" * 2000)
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 413
    assert response.json() == {
        "detail": [
            {
                "loc": [],
                "msg": "Request body exceeds 1024 bytes.",
                "type": "request_too_large",
            }
        ]
    }


def test_full_store_returns_503_and_rolls_back_the_row(scenario_api):
    import threading

    client, _, _, jobs, _ = scenario_api(max_jobs=1)
    release = threading.Event()

    def gated(progress):
        assert release.wait(timeout=30.0)
        return {"ok": True}

    jobs.submit("blocker", 1, gated)
    try:
        response = client.post("/v1/scenarios", json=scenario_payload())
        assert response.status_code == 503
        assert response.json()["detail"][0]["type"] == "server_busy"
        assert client.get("/v1/scenarios").json()["total"] == 0
    finally:
        release.set()


def test_store_schema_version_and_terminal_guard(tmp_path):
    db = SqliteScenarioStore(tmp_path / "v.sqlite3")
    try:
        assert db.schema_version == SCHEMA_VERSION == 1
        db.create("s1", "j1", {"a": 1})
        with pytest.raises(ValueError, match="terminal status"):
            db.save_result(
                "s1", status="running", bundle=None, ranking=None,
                report=None, trace=None, problems=[], warnings=[],
            )
        assert db.exists("s1") is True
        assert db.exists("nope") is False
    finally:
        db.close()


def test_scenario_routes_are_in_the_openapi_contract(scenario_api):
    client, _, _, _, _ = scenario_api()

    paths = client.get("/openapi.json").json()["paths"]
    assert "/v1/scenarios" in paths
    assert set(paths["/v1/scenarios"]) >= {"post", "get"}
    assert "/v1/scenarios/{scenario_id}" in paths
    assert set(paths["/v1/scenarios/{scenario_id}"]) >= {"get", "delete"}
