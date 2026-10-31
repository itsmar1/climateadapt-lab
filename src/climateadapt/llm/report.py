"""Report schema and the deterministic tool-output registry.

A report is the only LLM-written artifact a user may see, and it is only shown
after :mod:`climateadapt.llm.validator` accepts it. The schema enforces the
traceability contract structurally:

* every statement carries ``evidence_ids`` (retrieved chunk ids) and/or
  ``tool_output_ids`` (deterministic outputs) — at least one must be non-empty;
* every number in the report appears as a :class:`ReportedNumber` that names the
  tool output and field it was copied from — prose numerals are cross-checked
  against these declarations and the declarations against the registry;
* benefit/cost/risk echoes on ranked recommendations must equal the catalog
  strings stored in the registry (``"unknown"`` unless cited);
* limitations and provenance references are mandatory; the deterministic
  fallback is the only report allowed to set ``fallback=True``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

REPORT_SCHEMA_VERSION = 1
"""Version of the report JSON contract (rejected when it differs)."""

FALLBACK_GENERATOR = "deterministic-fallback"
"""Generator label of the deterministic fallback report (never model-written)."""


class ReportedNumber(BaseModel):
    """One number copied verbatim from a deterministic tool output."""

    model_config = ConfigDict(extra="forbid")

    value: float = Field(allow_inf_nan=False)
    unit: str | None = Field(default=None, min_length=1, max_length=24)
    tool_output_id: str = Field(min_length=1, max_length=120)
    field: str = Field(min_length=1, max_length=80)


class Statement(BaseModel):
    """One prose claim plus the ids that make it traceable."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list)
    tool_output_ids: list[str] = Field(default_factory=list)
    numbers: list[ReportedNumber] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_traceability(self) -> Statement:
        if not self.evidence_ids and not self.tool_output_ids:
            raise ValueError("A statement needs evidence_ids and/or tool_output_ids.")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("evidence_ids holds duplicates.")
        if len(set(self.tool_output_ids)) != len(self.tool_output_ids):
            raise ValueError("tool_output_ids holds duplicates.")
        return self


class EvidenceItem(BaseModel):
    """One cited chunk. Every field is verified against the chunk + manifest."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)
    citation: str = Field(min_length=1, max_length=600)
    pages: str = Field(min_length=1, max_length=120)
    landing_url: str = Field(min_length=1)
    license: str = Field(min_length=1)
    license_status: str = Field(min_length=1)


class RankedRecommendation(BaseModel):
    """One ranked option: identifiers, echoes, and a traceable narrative."""

    model_config = ConfigDict(extra="forbid")

    intervention_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    benefit: str = Field(min_length=1, max_length=280)
    cost: str = Field(min_length=1, max_length=280)
    risk: str = Field(min_length=1, max_length=280)
    narrative: Statement


class ExcludedOption(BaseModel):
    """One excluded option with machine-readable reason codes."""

    model_config = ConfigDict(extra="forbid")

    intervention_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    reason_codes: list[str] = Field(min_length=1)
    narrative: Statement


class Report(BaseModel):
    """The validated report contract (model draft or deterministic fallback)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = REPORT_SCHEMA_VERSION
    generator: str = Field(min_length=1, max_length=120)
    fallback: bool = False
    fallback_note: str | None = Field(default=None, max_length=600)
    summary: Statement
    environmental_findings: list[Statement] = Field(min_length=1)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    ranked_recommendations: list[RankedRecommendation] = Field(default_factory=list)
    excluded_options: list[ExcludedOption] = Field(default_factory=list)
    limitations: list[str] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)
    data_coverage: Statement
    provenance_refs: list[str] = Field(min_length=1)


class ToolOutput(BaseModel):
    """One deterministic output: copied numbers, copied strings, provenance."""

    model_config = ConfigDict(extra="forbid")

    output_id: str = Field(min_length=1, max_length=120)
    kind: Literal["bundle", "indicator", "ranking", "constraints"]
    values: dict[str, float] = Field(default_factory=dict)
    texts: dict[str, str] = Field(default_factory=dict)
    label: str | None = Field(default=None, max_length=120)
    provenance: str = Field(min_length=1, max_length=600)


class ToolOutputRegistry(BaseModel):
    """All deterministic outputs a report may cite, plus allowed date strings."""

    model_config = ConfigDict(extra="forbid")

    outputs: dict[str, ToolOutput] = Field(default_factory=dict)
    dates: set[str] = Field(default_factory=set)

    def has(self, output_id: str) -> bool:
        return output_id in self.outputs

    def lookup_number(self, output_id: str, field: str) -> float | None:
        output = self.outputs.get(output_id)
        if output is None:
            return None
        return output.values.get(field)

    def all_numbers(self) -> list[float]:
        numbers: list[float] = []
        for output in self.outputs.values():
            numbers.extend(output.values.values())
        return numbers


def ranking_output_id(intervention_id: str) -> str:
    return f"ranking:{intervention_id}"


def constraints_output_id(intervention_id: str) -> str:
    return f"constraints:{intervention_id}"


def _scalar_values(result: dict[str, Any]) -> dict[str, float]:
    """Top-level int/float scalars of a pipeline result (bools excluded)."""
    values: dict[str, float] = {}
    for key, item in result.items():
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            values[key] = float(item)
        elif isinstance(item, float):
            values[key] = item
    return values


def tool_outputs_from_bundle(bundle: Any) -> list[ToolOutput]:
    """Build registry entries from an environmental bundle (response or dict).

    Accepts an ``EnvironmentalBundleResponse`` (or its ``model_dump``) so the
    live path and stored snapshots share one builder. Every bundle entry gets
    an output — entries without a result carry no values, so no number can be
    cited from an indicator that was never computed.
    """
    data = bundle.model_dump(mode="json") if hasattr(bundle, "model_dump") else bundle
    outputs = [
        ToolOutput(
            output_id="bundle",
            kind="bundle",
            values={
                "latitude": float(data["latitude"]),
                "longitude": float(data["longitude"]),
                "timescale_months": float(data["timescale_months"]),
                "reference_start_year": float(data["reference_start_year"]),
                "reference_end_year": float(data["reference_end_year"]),
            },
            provenance="Environmental bundle request parameters.",
        )
    ]
    for entry in data.get("entries", []):
        indicator = entry["indicator"]
        result = entry.get("result") or {}
        texts = (
            {"data_source": str(result["data_source"])}
            if result.get("data_source")
            else {}
        )
        outputs.append(
            ToolOutput(
                output_id=indicator,
                kind="indicator",
                values=_scalar_values(result),
                texts=texts,
                provenance=(
                    f"{indicator} pipeline result (status {entry.get('status')})."
                ),
            )
        )
    return outputs


def tool_outputs_from_recommendations(response: Any) -> list[ToolOutput]:
    """Build registry entries from a recommendation response (model or dict)."""
    data = response.model_dump(mode="json") if hasattr(response, "model_dump") else response
    outputs: list[ToolOutput] = []
    for option in data.get("ranked", []):
        components = option.get("score_components", {})
        outputs.append(
            ToolOutput(
                output_id=ranking_output_id(option["intervention_id"]),
                kind="ranking",
                values={
                    "score_total": float(option["score_total"]),
                    **{k: float(v) for k, v in components.items()},
                },
                texts={
                    "benefit": option["benefit"],
                    "cost": option["cost"],
                    "risk": option["risk"],
                },
                label=option["name"],
                provenance="Deterministic ranking score and catalog echoes.",
            )
        )
    for option in data.get("excluded", []):
        outputs.append(
            ToolOutput(
                output_id=constraints_output_id(option["intervention_id"]),
                kind="constraints",
                values={},
                texts={"reason_codes": ",".join(r["code"] for r in option["reasons"])},
                label=option["name"],
                provenance="Deterministic hard-constraint exclusion reasons.",
            )
        )
    return outputs


def dates_from_bundle(bundle: Any) -> set[str]:
    """Date strings (YYYY-MM windows) a report may repeat verbatim."""
    data = bundle.model_dump(mode="json") if hasattr(bundle, "model_dump") else bundle
    dates = {str(data["target_end_month"])}
    for entry in data.get("entries", []):
        result = entry.get("result") or {}
        for key in ("target_window_start", "target_window_end"):
            if result.get(key):
                dates.add(str(result[key]))
    return dates


def build_registry(bundle: Any, recommendations: Any) -> ToolOutputRegistry:
    """Build the full registry both the prompt and the validator share."""
    outputs: dict[str, ToolOutput] = {}
    for output in tool_outputs_from_bundle(bundle) + tool_outputs_from_recommendations(
        recommendations
    ):
        outputs[output.output_id] = output
    return ToolOutputRegistry(outputs=outputs, dates=dates_from_bundle(bundle))
