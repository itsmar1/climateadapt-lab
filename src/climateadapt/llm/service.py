"""Report generation: one model call, strict validation, labelled fallback.

``generate_report`` is the only path from a provider to a user-visible report:
it sends the prompt, parses the draft as JSON, and validates it. The model
draft is returned only when validation passes; every other outcome — provider
error, empty content, malformed JSON, or a single validation problem — yields
the deterministic fallback with the rejection codes recorded.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from climateadapt.llm.provider import (
    LLMAuthError,
    LLMError,
    LLMInvalidResponseError,
    LLMProvider,
    LLMRateLimitError,
    LLMRequest,
    LLMTimeoutError,
    LLMUsage,
)
from climateadapt.llm.report import Report
from climateadapt.llm.validator import (
    ValidationContext,
    ValidationResult,
    validate_report,
)


@dataclass
class ReportOutcome:
    report: Report
    accepted: bool
    problems: list[str]
    usage: LLMUsage | None
    latency_ms: float
    attempts: int


def _provider_code(exc: LLMError) -> str:
    if isinstance(exc, LLMRateLimitError):
        return "provider-rate-limit"
    if isinstance(exc, LLMTimeoutError):
        return "provider-timeout"
    if isinstance(exc, LLMAuthError):
        return "provider-auth"
    if isinstance(exc, LLMInvalidResponseError):
        return "provider-refusal"
    return "provider-error"


def parse_model_json(content: str | None, finish_reason: str | None) -> dict:
    """Parse a draft body as JSON (fenced or raw). Raises ``ValueError``."""
    if content is None or not content.strip():
        raise ValueError(
            f"[empty-content] Model returned no text (finish_reason={finish_reason})."
        )
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:] if len(lines) > 1 else []
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"[invalid-json] Draft is not valid JSON: {exc}.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("[invalid-json] Draft JSON is not an object.")
    return parsed


def generate_report(
    provider: LLMProvider,
    request: LLMRequest,
    ctx: ValidationContext,
    make_fallback: Callable[[list[str]], Report],
) -> ReportOutcome:
    """Draft via the provider; return the draft or the labelled fallback."""
    try:
        response = provider.complete(request)
    except LLMError as exc:
        code = _provider_code(exc)
        problems = [f"[{code}] {exc}"]
        return ReportOutcome(
            report=make_fallback(problems),
            accepted=False,
            problems=problems,
            usage=None,
            latency_ms=0.0,
            attempts=0,
        )
    try:
        draft = parse_model_json(response.content, response.finish_reason)
    except ValueError as exc:
        problems = [str(exc)]
        return ReportOutcome(
            report=make_fallback(problems),
            accepted=False,
            problems=problems,
            usage=response.usage,
            latency_ms=response.latency_ms,
            attempts=response.attempts,
        )
    result: ValidationResult = validate_report(draft, ctx)
    if result.valid and result.report is not None:
        return ReportOutcome(
            report=result.report,
            accepted=True,
            problems=[],
            usage=response.usage,
            latency_ms=response.latency_ms,
            attempts=response.attempts,
        )
    return ReportOutcome(
        report=make_fallback(result.problems),
        accepted=False,
        problems=result.problems,
        usage=response.usage,
        latency_ms=response.latency_ms,
        attempts=response.attempts,
    )
