"""Builders for llm/report tests. All data is synthetic and offline."""

from __future__ import annotations

from climateadapt.llm.report import ToolOutputRegistry, build_registry
from climateadapt.llm.validator import ValidationContext
from climateadapt.rag.chunking import ChunkingParams, chunk_document
from climateadapt.rag.citations import build_citation
from climateadapt.rag.manifest import Manifest
from climateadapt.rag.models import Chunk, Page
from test_rag_manifest import valid_doc


def make_llm_manifest() -> Manifest:
    return Manifest.model_validate(
        {
            "manifest_version": 1,
            "description": "synthetic test manifest",
            "documents": [
                valid_doc(doc_id="test-doc-one"),
                valid_doc(doc_id="test-doc-two", title="Second test document"),
            ],
        }
    )


def make_llm_pages() -> dict[str, list[Page]]:
    return {
        "test-doc-one": [
            Page(page=1, text="alpha beta gamma delta deficit irrigation scheduling " * 20),
            Page(page=2, text="epsilon zeta supplemental water harvesting review " * 20),
        ],
        "test-doc-two": [
            Page(page=1, text="wheat rainfed sowing date mulching varieties trial " * 20),
        ],
    }


def make_llm_chunks(pages_by_doc: dict[str, list[Page]] | None = None) -> list[Chunk]:
    """Chunks cut from the synthetic pages (provenance verifies)."""
    pages_by_doc = pages_by_doc or make_llm_pages()
    chunks: list[Chunk] = []
    params = ChunkingParams(chunk_words=40, overlap_words=5, min_words=5)
    for doc_id, pages in pages_by_doc.items():
        doc_chunks, _ = chunk_document(doc_id, pages, params)
        chunks.extend(doc_chunks)
    assert len(chunks) >= 2
    return chunks


def make_llm_bundle() -> dict:
    return {
        "indicator": "environmental_bundle",
        "latitude": 30.43,
        "longitude": -9.61,
        "target_end_month": "2024-03",
        "timescale_months": 3,
        "reference_start_year": 1991,
        "reference_end_year": 2020,
        "entries": [
            {
                "indicator": "chirps_spi",
                "status": "ok",
                "error_type": None,
                "error_message": None,
                "result": {
                    "data_source": "CHIRPS v3.0",
                    "timescale_months": 3,
                    "target_window_start": "2024-01",
                    "target_window_end": "2024-03",
                    "window_total_mm": 76.87,
                    "spi": -0.517,
                    "cumulative_probability": 0.303,
                    "reference_years_used": 30,
                },
                "requested_latitude": 30.43,
                "requested_longitude": -9.61,
                "grid_point_latitude": 30.425,
                "grid_point_longitude": -9.625,
            },
            {
                "indicator": "era5_temperature_anomaly",
                "status": "failed",
                "error_type": "data_not_available",
                "error_message": "No data for the requested window.",
                "result": None,
                "requested_latitude": 30.43,
                "requested_longitude": -9.61,
                "grid_point_latitude": None,
                "grid_point_longitude": None,
            },
        ],
    }


def make_llm_ranking(link_page: int = 1) -> dict:
    return {
        "catalog_version": 1,
        "scenario": {"crop": "wheat"},
        "ranked": [
            {
                "intervention_id": "test-drip",
                "name": "Test drip",
                "category": "irrigation",
                "score_total": 0.85,
                "score_components": {
                    "evidence_strength": 1.0,
                    "indicator_relevance": 1.0,
                    "constraint_fit": 1.0,
                },
                "score_weights": {},
                "score_inputs": {},
                "unknowns": [],
                "evidence": [
                    {
                        "doc_id": "test-doc-one",
                        "pdf_page": link_page,
                        "reference": "Test locator",
                        "citation": "Test citation.",
                        "landing_url": "https://example.org/doc",
                        "license": "CC-BY-4.0",
                        "license_status": "verified_in_record",
                        "unverified_fields": [],
                    }
                ],
                "benefit": "unknown",
                "cost": "unknown",
                "risk": "unknown",
            }
        ],
        "excluded": [
            {
                "intervention_id": "test-flood",
                "name": "Test flood",
                "category": "irrigation",
                "evidence_status": "supported",
                "reasons": [
                    {"code": "no_water_source", "message": "No water source."},
                ],
            }
        ],
        "warnings": [],
        "limitations": ["Synthetic limitation."],
    }


def make_llm_registry(
    bundle: dict | None = None, ranking: dict | None = None
) -> ToolOutputRegistry:
    return build_registry(bundle or make_llm_bundle(), ranking or make_llm_ranking())


def make_llm_context(
    chunks: list[Chunk] | None = None,
    bundle: dict | None = None,
    ranking: dict | None = None,
) -> ValidationContext:
    chunks = chunks if chunks is not None else make_llm_chunks()
    return ValidationContext(
        registry=make_llm_registry(bundle, ranking),
        chunks={c.chunk_id: c for c in chunks},
        manifest=make_llm_manifest(),
        pages_by_doc=make_llm_pages(),
    )


def evidence_entry(chunk: Chunk, manifest: Manifest | None = None) -> dict:
    citation = build_citation(chunk, (manifest or make_llm_manifest()).get(chunk.doc_id))
    return {
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "citation": citation.formatted,
        "pages": citation.pages,
        "landing_url": citation.landing_url,
        "license": citation.license,
        "license_status": citation.license_status,
    }


def valid_report_dict(ctx: ValidationContext | None = None) -> dict:
    """A model draft that must validate (numbers copied exactly, all ids known)."""
    ctx = ctx or make_llm_context()
    chunk_ids = sorted(ctx.chunks)
    first = ctx.chunks[chunk_ids[0]]
    return {
        "schema_version": 1,
        "generator": "fake:test-model",
        "fallback": False,
        "fallback_note": None,
        "summary": {
            "text": "Analysis for the requested location and window is complete.",
            "evidence_ids": [first.chunk_id],
            "tool_output_ids": ["bundle"],
            "numbers": [],
        },
        "environmental_findings": [
            {
                "text": (
                    "CHIRPS SPI is -0.517 for a window total of 76.87 mm, "
                    "using 30 reference years."
                ),
                "evidence_ids": [],
                "tool_output_ids": ["chirps_spi"],
                "numbers": [
                    {"value": -0.517, "unit": None,
                     "tool_output_id": "chirps_spi", "field": "spi"},
                    {"value": 76.87, "unit": "mm",
                     "tool_output_id": "chirps_spi", "field": "window_total_mm"},
                    {"value": 30.0, "unit": None,
                     "tool_output_id": "chirps_spi", "field": "reference_years_used"},
                ],
            }
        ],
        "evidence": [evidence_entry(first, ctx.manifest)],
        "ranked_recommendations": [
            {
                "intervention_id": "test-drip",
                "name": "Test drip",
                "benefit": "unknown",
                "cost": "unknown",
                "risk": "unknown",
                "narrative": {
                    "text": "Test drip (test-drip): ranked with score 0.85.",
                    "evidence_ids": [first.chunk_id],
                    "tool_output_ids": ["ranking:test-drip"],
                    "numbers": [
                        {"value": 0.85, "unit": None,
                         "tool_output_id": "ranking:test-drip", "field": "score_total"},
                    ],
                },
            }
        ],
        "excluded_options": [
            {
                "intervention_id": "test-flood",
                "name": "Test flood",
                "reason_codes": ["no_water_source"],
                "narrative": {
                    "text": "Test flood (test-flood): excluded. Reasons: no_water_source.",
                    "evidence_ids": [],
                    "tool_output_ids": ["constraints:test-flood"],
                    "numbers": [],
                },
            }
        ],
        "limitations": [
            "Indicator values are reported without drought categories or composite scores.",
            "Benefit, cost and risk are unknown unless the catalog cites a source.",
        ],
        "assumptions": ["Retrieved passages are cited for traceability."],
        "data_coverage": {
            "text": (
                "Location 30.43, -9.61; target window ending 2024-03; "
                "timescale 3 months; reference 1991 to 2020."
            ),
            "evidence_ids": [],
            "tool_output_ids": ["bundle"],
            "numbers": [
                {"value": 30.43, "unit": "deg",
                 "tool_output_id": "bundle", "field": "latitude"},
                {"value": -9.61, "unit": "deg",
                 "tool_output_id": "bundle", "field": "longitude"},
                {"value": 3.0, "unit": "months",
                 "tool_output_id": "bundle", "field": "timescale_months"},
                {"value": 1991.0, "unit": None,
                 "tool_output_id": "bundle", "field": "reference_start_year"},
                {"value": 2020.0, "unit": None,
                 "tool_output_id": "bundle", "field": "reference_end_year"},
            ],
        },
        "provenance_refs": [
            "bundle", "chirps_spi", "ranking:test-drip", "constraints:test-flood",
        ],
    }
