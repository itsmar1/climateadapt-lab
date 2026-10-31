"""LLM provider adapter. Every model call goes through ``LLMProvider``.

The only network-backed implementation is ``BasetenProvider``, written strictly
against the verified API in ``docs/LLM_PROVIDER_NOTES.md`` (OpenAI-compatible
``POST {base_url}/chat/completions``, Bearer auth, OpenAI-shaped usage). No other
provider or model ID exists here. Tests use ``FakeProvider``; no test touches the
network.

Secrets: the API key is held as ``SecretStr`` (or transient ``str`` in tests) and
is never logged, never included in an exception message, and never echoed in a
request recording.
"""

from __future__ import annotations

import logging
import time
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from climateadapt.config import get_settings

logger = logging.getLogger(__name__)

CHAT_COMPLETIONS_PATH = "/chat/completions"
"""Verified route (LLM_PROVIDER_NOTES.md §1): POST {base_url}/chat/completions."""

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504, 529})
"""429/529 = rate limit or shed load; 5xx = transient (verified error table)."""

ERROR_BODY_PREVIEW_CHARS = 500
"""Cap on server error text kept in an exception message (never a secret)."""

MAX_RETRY_AFTER_SECONDS = 60.0
"""Upper bound for honouring a server-sent Retry-After header."""


class LLMError(Exception):
    """Base class for every provider failure (transport, API, or bad payload)."""


class LLMAuthError(LLMError):
    """Missing key, bad key, or forbidden model (401/403). Never retried."""


class LLMRateLimitError(LLMError):
    """Rate limit or shed load persisted past the retry budget (429/529)."""


class LLMTimeoutError(LLMError):
    """No response within the timeout, after retries."""


class LLMProviderError(LLMError):
    """Other provider failure (billing, bad request, bad model slug, 5xx)."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LLMInvalidResponseError(LLMError):
    """HTTP 200 whose body is not a usable completion (no choices, refusal)."""


class LLMMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(pattern=r"^(system|user|assistant|tool)$")
    content: str = Field(min_length=1)


class LLMRequest(BaseModel):
    """One chat-completions call. ``n > 1`` is never sent (verified 400)."""

    model_config = ConfigDict(extra="forbid")

    messages: list[LLMMessage] = Field(min_length=1)
    max_tokens: int = Field(strict=True, ge=1, le=100000)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    response_format: dict | None = Field(
        default=None,
        description="Optional json_schema hint. Accepted but NOT enforced for "
        "Muse Spark Open: client-side validation is the real enforcement.",
    )


class LLMUsage(BaseModel):
    """Token accounting exactly as the API returns it (all fields optional)."""

    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cached_tokens: int | None = None


class LLMResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str | None = Field(
        default=None,
        description="Assistant text; None when the completion was cut "
        "(finish_reason=length on a reasoning model with a small budget).",
    )
    finish_reason: str | None = None
    usage: LLMUsage | None = None
    request_id: str | None = Field(
        default=None, description="x-baseten-request-id when the server sent one."
    )
    latency_ms: float = Field(ge=0.0)
    attempts: int = Field(strict=True, ge=1)


class LLMProvider(Protocol):
    """Synchronous completion interface. Implementations must be secret-safe."""

    @property
    def label(self) -> str:
        """Short human label (model id or 'fake'); safe to log and store."""
        ...

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Run one completion; raise an ``LLMError`` subclass on any failure."""
        ...

    def close(self) -> None:
        """Release owned resources. Best-effort; never raises on a fake."""
        ...


def _backoff_seconds(attempt: int, base: float, cap: float) -> float:
    return min(cap, base * (2**attempt))


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        value = float(raw.strip())
    except ValueError:
        return None
    if value < 0:
        return None
    return min(value, MAX_RETRY_AFTER_SECONDS)


def _preview(text: str) -> str:
    if len(text) <= ERROR_BODY_PREVIEW_CHARS:
        return text
    return text[:ERROR_BODY_PREVIEW_CHARS] + "... [truncated]"


class BasetenProvider:
    """Live provider for Baseten Model APIs (Chat Completions only).

    Retries ``RETRYABLE_STATUS`` plus connect/timeout transport errors with
    bounded exponential backoff; auth/billing/shape errors fail immediately.
    Logs statuses, latencies and usage only — never the key or full bodies.
    """

    def __init__(
        self,
        api_key: SecretStr | str | None = None,
        *,
        base_url: str | None = None,
        model_id: str | None = None,
        timeout_seconds: float = 120.0,
        max_retries: int = 3,
        backoff_base_seconds: float = 1.0,
        backoff_max_seconds: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        secret = api_key if api_key is not None else settings.baseten_api_key
        if secret is None or (
            isinstance(secret, SecretStr) and not secret.get_secret_value()
        ):
            raise LLMAuthError("No Baseten API key configured.")
        if isinstance(secret, str) and not secret:
            raise LLMAuthError("No Baseten API key configured.")
        self._secret = secret
        self._base_url = (base_url or settings.baseten_base_url).rstrip("/")
        self._model_id = model_id or settings.baseten_model_id
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._backoff_base = backoff_base_seconds
        self._backoff_max = backoff_max_seconds
        self._client = http_client
        self._owns_client = http_client is None

    @property
    def label(self) -> str:
        return f"baseten:{self._model_id}"

    @property
    def model_id(self) -> str:
        return self._model_id

    def _key(self) -> str:
        return (
            self._secret.get_secret_value()
            if isinstance(self._secret, SecretStr)
            else self._secret
        )

    def _client_or_new(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._key()}"},
            timeout=self._timeout,
        )

    def complete(self, request: LLMRequest) -> LLMResponse:
        # Fail fast before any network access: nothing leaves this method
        # unvalidated, and the key never appears in a message or log.
        payload: dict = {
            "model": self._model_id,
            "messages": [m.model_dump() for m in request.messages],
            "max_tokens": request.max_tokens,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.response_format is not None:
            payload["response_format"] = request.response_format

        client = self._client_or_new()
        owns = self._owns_client and self._client is None
        started_all = time.monotonic()
        try:
            return self._post_with_retries(client, payload)
        finally:
            if owns:
                client.close()
            logger.info(
                "llm complete model=%s attempts_done total_ms=%.0f",
                self._model_id,
                (time.monotonic() - started_all) * 1000,
            )

    def _post_with_retries(
        self, client: httpx.Client, payload: dict
    ) -> LLMResponse:
        headers = {"Authorization": f"Bearer {self._key()}"}
        last_error: LLMError | None = None
        for attempt in range(self._max_retries + 1):
            started = time.monotonic()
            try:
                response = client.post(
                    CHAT_COMPLETIONS_PATH, json=payload, headers=headers
                )
            except httpx.TimeoutException as exc:
                last_error = LLMTimeoutError(f"LLM request timed out: {type(exc).__name__}.")
                logger.warning("llm attempt %d timed out", attempt + 1)
            except httpx.HTTPError as exc:
                last_error = LLMProviderError(
                    f"LLM transport error: {type(exc).__name__}."
                )
                logger.warning(
                    "llm attempt %d transport error: %s", attempt + 1, type(exc).__name__
                )
            else:
                latency_ms = (time.monotonic() - started) * 1000
                logger.info(
                    "llm attempt %d http=%d ms=%.0f",
                    attempt + 1,
                    response.status_code,
                    latency_ms,
                )
                outcome = self._handle_response(response, latency_ms, attempt)
                if outcome is not None:
                    return outcome
                last_error = self._last_retryable_error(response)
            if attempt < self._max_retries:
                delay = _backoff_seconds(attempt, self._backoff_base, self._backoff_max)
                time.sleep(delay)
        assert last_error is not None  # the loop always sets it before falling through
        raise last_error

    def _handle_response(
        self, response: httpx.Response, latency_ms: float, attempt: int
    ) -> LLMResponse | None:
        """Return a response, raise a terminal error, or None when retryable."""
        status = response.status_code
        if status == 200:
            return self._parse_success(response, latency_ms, attempt)
        if status in (401, 403):
            raise LLMAuthError(f"Baseten rejected the credentials (HTTP {status}).")
        if status == 402:
            raise LLMProviderError(
                f"Baseten billing error (HTTP 402): {_preview(response.text)}",
                status_code=status,
            )
        if status == 404:
            raise LLMProviderError(
                f"Baseten endpoint or model not found (HTTP 404): {_preview(response.text)}",
                status_code=status,
            )
        if status in RETRYABLE_STATUS:
            retry_after = _retry_after_seconds(response)
            if retry_after is not None:
                time.sleep(retry_after)
            return None
        raise LLMProviderError(
            f"Baseten request failed (HTTP {status}): {_preview(response.text)}",
            status_code=status,
        )

    def _last_retryable_error(self, response: httpx.Response) -> LLMError:
        status = response.status_code
        if status in (429, 529):
            return LLMRateLimitError(
                f"Baseten rate limit or shed load (HTTP {status}); "
                f"retries exhausted after {self._max_retries + 1} attempts."
            )
        return LLMProviderError(
            f"Baseten transient error (HTTP {status}); "
            f"retries exhausted after {self._max_retries + 1} attempts: "
            f"{_preview(response.text)}",
            status_code=status,
        )

    def _parse_success(
        self, response: httpx.Response, latency_ms: float, attempt: int
    ) -> LLMResponse:
        try:
            body = response.json()
        except ValueError as exc:
            raise LLMInvalidResponseError("Baseten returned a non-JSON 200 body.") from exc
        choices = body.get("choices") or []
        if not choices:
            raise LLMInvalidResponseError("Baseten 200 body holds no choices.")
        message = choices[0].get("message") or {}
        if message.get("refusal"):
            raise LLMInvalidResponseError(
                f"Model refused the request: {_preview(str(message['refusal']))}"
            )
        usage: LLMUsage | None = None
        raw_usage = body.get("usage")
        if isinstance(raw_usage, dict):
            details = raw_usage.get("prompt_tokens_details") or {}
            usage = LLMUsage(
                prompt_tokens=raw_usage.get("prompt_tokens"),
                completion_tokens=raw_usage.get("completion_tokens"),
                total_tokens=raw_usage.get("total_tokens"),
                cached_tokens=details.get("cached_tokens"),
            )
            logger.info(
                "llm usage prompt=%s completion=%s cached=%s",
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.cached_tokens,
            )
        return LLMResponse(
            content=message.get("content"),
            finish_reason=choices[0].get("finish_reason"),
            usage=usage,
            request_id=response.headers.get("x-baseten-request-id"),
            latency_ms=latency_ms,
            attempts=attempt + 1,
        )

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            try:
                self._client.close()
            except Exception:  # best-effort shutdown
                logger.exception("Error closing the Baseten HTTP client.")


class FakeProvider:
    """Scripted provider for offline tests. No network, no key, no sleeping."""

    def __init__(self, script: list[LLMResponse | Exception]) -> None:
        self._script = list(script)
        self.requests: list[LLMRequest] = []

    @property
    def label(self) -> str:
        return "fake"

    @classmethod
    def with_text(
        cls,
        content: str | None,
        *,
        finish_reason: str | None = "stop",
        usage: LLMUsage | None = None,
    ) -> FakeProvider:
        return cls(
            [
                LLMResponse(
                    content=content,
                    finish_reason=finish_reason,
                    usage=usage,
                    latency_ms=0.0,
                    attempts=1,
                )
            ]
        )

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self._script:
            raise LLMProviderError("FakeProvider script exhausted.")
        next_item = self._script.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item

    def close(self) -> None:
        return None
