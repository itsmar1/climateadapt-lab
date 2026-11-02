"""Auditable run traces: stages, tool calls, verdicts, usage — never secrets.

A trace records what ran, in which order, how long each step took, what each
tool returned (summarised), what the validator said, and how many tokens the
run consumed. It deliberately excludes: credentials (never in scope — the
scenario carries none), full retrieved passage text (ids + scores only, so a
trace is not a corpus redistribution channel), and full LLM prompt bodies
(sizes only; the deterministic inputs that built them are summarised).
Model draft and repair outputs ARE kept verbatim (P22: needed to debug
validator rejections; they carry no credentials).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

SUMMARY_CHARS = 20000
"""Per-record cap; longer summaries are cut with an explicit marker."""


def summarize(text: str, limit: int = SUMMARY_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [truncated, {len(text)} chars total]"


class StageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: str = Field(pattern=r"^(ok|failed|skipped)$")
    started_at: str
    duration_ms: float = Field(ge=0.0)
    detail: str = ""
    error_code: str | None = None


class ToolCallRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    ok: bool
    duration_ms: float = Field(ge=0.0)
    input_summary: str = ""
    output_summary: str = ""
    error_code: str | None = None


class RunTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    agent_version: int
    started_at: str
    ended_at: str = ""
    duration_ms_total: float = 0.0
    scenario: dict = Field(default_factory=dict)
    config: dict = Field(default_factory=dict)
    component_versions: dict[str, str] = Field(default_factory=dict)
    stages: list[StageRecord] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    validator_verdicts: list[str] = Field(default_factory=list)
    draft_text: str = ""
    """First model draft, verbatim (empty when no content was returned)."""
    repair_text: str = ""
    """Repair output, verbatim (empty when no repair ran or returned any)."""
    usage: dict | None = None
    outcome: str = ""
    problems: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def save_trace(trace: RunTrace, path: Path) -> Path:
    """Write a trace as indented JSON (callers choose a git-ignored directory)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(trace.model_dump_json(indent=1), encoding="utf-8")
    return path
