"""Offline tests for the LLM provider adapter. No network, no real credentials."""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from climateadapt.llm.provider import (
    BasetenProvider,
    FakeProvider,
    LLMAuthError,
    LLMInvalidResponseError,
    LLMMessage,
    LLMProviderError,
    LLMRateLimitError,
    LLMRequest,
    LLMTimeoutError,
    LLMUsage,
)

FAKE_KEY = "[REDACTED]"
MODEL = "meta-models/muse-spark-open-1026"


@pytest.fixture
def no_sleep(monkeypatch):
    calls: list[float] = []
    monkeypatch.setattr(
        "climateadapt.llm.provider.time.sleep", lambda s: calls.append(s)
    )
    return calls


def make_request(text: str = "say ok") -> LLMRequest:
    return LLMRequest(
        messages=[LLMMessage(role="user", content=text)], max_tokens=16
    )


def completion_body(content: str | None = "ok", **overrides) -> dict:
    body = {
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "prompt_tokens_details": {"cached_tokens": 3},
        },
    }
    body.update(overrides)
    return body


def provider_with(routes: list, **kwargs) -> tuple[BasetenProvider, list]:
    """BasetenProvider over a MockTransport script; returns (provider, requests)."""
    seen: list[httpx.Request] = []
    script = list(routes)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        item = script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://example.test/v1"
    )
    provider = BasetenProvider(
        FAKE_KEY,
        base_url="https://example.test/v1",
        model_id=MODEL,
        http_client=client,
        backoff_base_seconds=0.0,
        **kwargs,
    )
    return provider, seen


def test_success_returns_content_usage_and_request_id():
    provider, seen = provider_with(
        [httpx.Response(200, json=completion_body(), headers={"x-baseten-request-id": "r1"})]
    )
    response = provider.complete(make_request())

    assert response.content == "ok"
    assert response.finish_reason == "stop"
    assert response.usage == LLMUsage(
        prompt_tokens=10, completion_tokens=5, total_tokens=15, cached_tokens=3
    )
    assert response.request_id == "r1"
    assert response.attempts == 1
    payload = json.loads(seen[0].content.decode())
    assert payload["model"] == MODEL
    assert payload["max_tokens"] == 16
    assert payload["messages"] == [{"role": "user", "content": "say ok"}]
    assert "n" not in payload  # verified: n > 1 returns HTTP 400
    assert seen[0].headers["authorization"] == f"Bearer {FAKE_KEY}"
    assert seen[0].url.path == "/v1/chat/completions"


def test_rate_limit_then_success_retries(no_sleep):
    provider, seen = provider_with(
        [
            httpx.Response(429, json={"error": "slow down"}),
            httpx.Response(200, json=completion_body()),
        ]
    )
    response = provider.complete(make_request())

    assert response.content == "ok"
    assert response.attempts == 2
    assert len(seen) == 2
    assert no_sleep == [0.0]  # backoff ran (zero base in tests)


def test_rate_limit_exhausted_raises_and_hides_key(no_sleep):
    provider, _ = provider_with(
        [httpx.Response(429, json={"error": "slow"})] * 4, max_retries=3
    )
    with pytest.raises(LLMRateLimitError, match="retries exhausted") as excinfo:
        provider.complete(make_request())
    assert FAKE_KEY not in str(excinfo.value)


def test_shed_load_529_is_retried_like_429(no_sleep):
    provider, seen = provider_with(
        [httpx.Response(529, json={"error": "shed"}), httpx.Response(200, json=completion_body())],
        max_retries=1,
    )
    assert provider.complete(make_request()).attempts == 2
    assert len(seen) == 2


def test_transient_5xx_retries_then_succeeds(no_sleep):
    provider, _ = provider_with(
        [httpx.Response(503, text="busy"), httpx.Response(200, json=completion_body())]
    )
    assert provider.complete(make_request()).content == "ok"


def test_auth_failure_fails_fast_without_retry():
    provider, seen = provider_with([httpx.Response(401, json={"error": "bad key"})])
    with pytest.raises(LLMAuthError, match="credentials"):
        provider.complete(make_request())
    assert len(seen) == 1


def test_missing_key_fails_before_any_network_call():
    seen: list[httpx.Request] = []
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: (seen.append(request), httpx.Response(200))[1]
        ),
        base_url="https://example.test/v1",
    )
    with pytest.raises(LLMAuthError, match="No Baseten API key"):
        BasetenProvider("", http_client=client)
    assert seen == []


def test_timeout_retries_then_raises_timeout(no_sleep):
    provider, _ = provider_with(
        [httpx.TimeoutException("slow")] * 3, max_retries=2
    )
    with pytest.raises(LLMTimeoutError, match="timed out"):
        provider.complete(make_request())
    assert no_sleep == [0.0, 0.0]


def test_success_without_choices_is_invalid():
    provider, _ = provider_with([httpx.Response(200, json={"choices": []})])
    with pytest.raises(LLMInvalidResponseError, match="no choices"):
        provider.complete(make_request())


def test_model_refusal_is_invalid():
    body = completion_body()
    body["choices"][0]["message"] = {"role": "assistant", "refusal": "no"}
    provider, _ = provider_with([httpx.Response(200, json=body)])
    with pytest.raises(LLMInvalidResponseError, match="refused"):
        provider.complete(make_request())


def test_cut_content_is_returned_for_the_service_to_handle():
    body = completion_body(content=None)
    body["choices"][0]["finish_reason"] = "length"
    provider, _ = provider_with([httpx.Response(200, json=body)])
    response = provider.complete(make_request())
    assert response.content is None
    assert response.finish_reason == "length"


def test_billing_and_bad_request_errors_do_not_retry():
    for status in (400, 402, 404, 413):
        provider, seen = provider_with([httpx.Response(status, text="nope")])
        with pytest.raises((LLMProviderError, LLMAuthError)):
            provider.complete(make_request())
        assert len(seen) == 1


def test_long_error_bodies_are_truncated():
    provider, _ = provider_with([httpx.Response(400, text="x" * 2000)])
    with pytest.raises(LLMProviderError) as excinfo:
        provider.complete(make_request())
    assert len(str(excinfo.value)) < 2000
    assert "truncated" in str(excinfo.value)


def test_key_never_appears_in_logs(caplog):
    provider, _ = provider_with(
        [
            httpx.Response(429, json={"error": "slow"}),
            httpx.Response(200, json=completion_body()),
        ]
    )
    with caplog.at_level(logging.INFO, logger="climateadapt.llm.provider"):
        provider.complete(make_request())
    assert FAKE_KEY not in caplog.text
    assert "Bearer" not in caplog.text


def test_fake_provider_replays_script_and_records_requests():
    fake = FakeProvider.with_text('{"a": 1}')
    request = make_request()
    response = fake.complete(request)

    assert response.content == '{"a": 1}'
    assert fake.requests == [request]
    assert fake.label == "fake"
    with pytest.raises(LLMProviderError, match="script exhausted"):
        fake.complete(request)


def test_fake_provider_replays_errors():
    fake = FakeProvider([LLMRateLimitError("limited")])
    with pytest.raises(LLMRateLimitError):
        fake.complete(make_request())
