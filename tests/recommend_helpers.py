"""Builders for recommend tests. All data is synthetic and offline."""

from __future__ import annotations

from climateadapt.rag.manifest import Manifest
from climateadapt.recommend.schema import (
    Intervention,
    InterventionCatalog,
    ScenarioContext,
)
from climateadapt.schemas_era5 import (
    ALL_BUNDLE_INDICATORS,
    BundleIndicatorResult,
    EnvironmentalBundleResponse,
)
from test_rag_manifest import valid_doc


def make_manifest(*doc_ids: str) -> Manifest:
    """Manifest with one minimal valid document per id (default: one test doc)."""
    ids = doc_ids or ("test-doc-one",)
    return Manifest.model_validate(
        {
            "manifest_version": 1,
            "description": "synthetic test manifest",
            "documents": [valid_doc(doc_id=doc_id) for doc_id in ids],
        }
    )


def make_entry(**overrides) -> Intervention:
    """Valid supported entry (irrigation, wheat, one evidence link)."""
    entry = {
        "intervention_id": "test-drip",
        "name": "Test drip",
        "category": "irrigation",
        "description": "A synthetic irrigation entry for offline tests.",
        "applicability": {
            "crop_types": ["wheat"],
            "requires_water_source": True,
            "production_systems": ["irrigated"],
            "soil_types": ["loam"],
            "climate_regimes": ["semi-arid"],
            "farm_scales": ["smallholder"],
        },
        "benefit": "unknown",
        "benefit_evidence": [],
        "cost": "unknown",
        "cost_evidence": [],
        "risk": "unknown",
        "risk_evidence": [],
        "evidence_status": "supported",
        "evidence_links": [
            {"doc_id": "test-doc-one", "pdf_page": 3, "reference": "Test locator"}
        ],
        "expected_sources": [],
        "needs_evidence_note": None,
        "relevant_indicators": ["chirps_spi"],
    }
    entry.update(overrides)
    return Intervention.model_validate(entry)


def make_catalog(*entries: Intervention) -> InterventionCatalog:
    """Catalog from entries (default: one valid entry)."""
    return InterventionCatalog.model_validate(
        {
            "catalog_version": 1,
            "description": "Synthetic test catalog for offline tests.",
            "interventions": [
                (entry.model_dump() if entries else make_entry().model_dump())
                for entry in (entries or (None,))
            ],
        }
    )


def make_scenario(**overrides) -> ScenarioContext:
    """Scenario with everything known and matching the default entry."""
    scenario = {
        "crop": "wheat",
        "has_water_source": True,
        "has_irrigation_equipment": True,
        "production_system": "irrigated",
        "season": "2024-03",
        "latitude": 30.43,
        "longitude": -9.61,
    }
    scenario.update(overrides)
    return ScenarioContext.model_validate(scenario)


def make_bundle(statuses: dict[str, str] | None = None) -> EnvironmentalBundleResponse:
    """Bundle with one entry per indicator (default: all 'ok')."""
    statuses = statuses or {}
    return EnvironmentalBundleResponse.model_validate(
        {
            "indicator": "environmental_bundle",
            "latitude": 30.43,
            "longitude": -9.61,
            "target_end_month": "2024-03",
            "timescale_months": 3,
            "reference_start_year": 1991,
            "reference_end_year": 2020,
            "entries": [
                BundleIndicatorResult(
                    indicator=name,
                    status=statuses.get(name, "ok"),  # type: ignore[arg-type]
                    requested_latitude=30.43,
                    requested_longitude=-9.61,
                ).model_dump()
                for name in ALL_BUNDLE_INDICATORS
            ],
        }
    )
