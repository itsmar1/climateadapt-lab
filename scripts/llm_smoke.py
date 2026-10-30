"""Tiny gated live probe of the Baseten Model APIs route (P03 verification spike).

Runs ONLY when CLIMATEADAPT_RUN_LIVE_LLM=1 and a Baseten API key is configured
(via CLIMATEADAPT_BASETEN_API_KEY or BASETEN_API_KEY). Makes at most 5 small,
cheap requests (tiny max_tokens), then stops. Prints statuses, latencies, token
usage, and truncated bodies; never prints the API key.

PowerShell, current session only:

    $env:CLIMATEADAPT_RUN_LIVE_LLM = "1"
    uv run python scripts/llm_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
import time

import httpx

from climateadapt.config import get_settings

MAX_CALLS = 5
MAX_TOKENS = 64
BODY_PREVIEW_CHARS = 600
GATE_ENV_VAR = "CLIMATEADAPT_RUN_LIVE_LLM"


def _preview(text: str) -> str:
    if len(text) <= BODY_PREVIEW_CHARS:
        return text
    return text[:BODY_PREVIEW_CHARS] + f"... [truncated, {len(text)} chars total]"


def main() -> int:
    if os.environ.get(GATE_ENV_VAR) != "1":
        print(f"NOT RUN: {GATE_ENV_VAR}=1 is not set (refusing live LLM calls).")
        return 2
    settings = get_settings()
    secret = settings.baseten_api_key
    key = secret.get_secret_value() if secret is not None else ""
    if not key:
        print("NOT RUN: no Baseten API key configured (set CLIMATEADAPT_BASETEN_API_KEY).")
        return 2

    base_url = settings.baseten_base_url.rstrip("/")
    model = settings.baseten_model_id
    print(f"base_url: {base_url}")
    print(f"model: {model}")
    print(f"key: configured ({len(key)} chars, never printed)")
    print(f"call budget: {MAX_CALLS} requests, max_tokens={MAX_TOKENS} each")

    calls = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0

    def post(name: str, payload: dict) -> dict | None:
        nonlocal calls, total_prompt_tokens, total_completion_tokens
        if calls >= MAX_CALLS:
            print(f"[{name}] SKIPPED: call budget exhausted.")
            return None
        calls += 1
        started = time.monotonic()
        try:
            response = client.post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            print(f"[{name}] TRANSPORT ERROR: {type(exc).__name__}: {exc}")
            return None
        latency_ms = (time.monotonic() - started) * 1000
        print(f"[{name}] HTTP {response.status_code} in {latency_ms:.0f} ms")
        try:
            body = response.json()
        except ValueError:
            print(f"[{name}] non-JSON body: {_preview(response.text)}")
            return None
        usage = body.get("usage") or {}
        total_prompt_tokens += int(usage.get("prompt_tokens") or 0)
        total_completion_tokens += int(usage.get("completion_tokens") or 0)
        if usage:
            print(f"[{name}] usage: {json.dumps(usage)}")
        return body

    try:
        client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {key}"},
            timeout=settings.http_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        print(f"TRANSPORT ERROR creating client: {type(exc).__name__}: {exc}")
        return 1

    with client:
        # (a) Trivial completion.
        body = post(
            "a/trivial",
            {
                "model": model,
                "messages": [{"role": "user", "content": "Reply with exactly: smoke-ok"}],
                "max_tokens": 32,
            },
        )
        if body is not None:
            choices = body.get("choices") or []
            if choices:
                message = choices[0].get("message") or {}
                print(f"[a/trivial] finish_reason={choices[0].get('finish_reason')}")
                print(f"[a/trivial] content: {_preview(str(message.get('content')))}")
            else:
                print(f"[a/trivial] no choices; body: {_preview(json.dumps(body))}")

        # (b) Structured-output request (docs: accepted but NOT enforced for this model).
        schema: dict = {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        }
        body = post(
            "b/json-schema",
            {
                "model": model,
                "messages": [{"role": "user", "content": 'Reply with {"answer": "pong"}'}],
                "max_tokens": MAX_TOKENS,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "ping", "schema": schema, "strict": True},
                },
            },
        )
        if body is not None:
            choices = body.get("choices") or []
            content = str((choices[0].get("message") or {}).get("content")) if choices else ""
            try:
                parsed = json.loads(content)
                valid = isinstance(parsed, dict) and set(parsed) == {"answer"}
            except ValueError:
                valid = False
            print(f"[b/json-schema] client-side parse valid={valid}")
            print(f"[b/json-schema] content: {_preview(content)}")

        # (c) Tool-call round trip (docs: supported).
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "add",
                    "description": "Add two numbers.",
                    "parameters": {
                        "type": "object",
                        "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                        "required": ["a", "b"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
            }
        ]
        messages = [{"role": "user", "content": "Use add to calculate 3.14 + 3.14."}]
        body = post(
            "c/tool-call",
            {
                "model": model,
                "messages": messages,
                "tools": tools,
                "tool_choice": "required",
                "max_tokens": MAX_TOKENS,
            },
        )
        tool_calls: list = []
        if body is not None:
            choices = body.get("choices") or []
            if choices:
                message = choices[0].get("message") or {}
                tool_calls = message.get("tool_calls") or []
                print(f"[c/tool-call] finish_reason={choices[0].get('finish_reason')}")
                print(f"[c/tool-call] tool_calls={len(tool_calls)}")
                for call in tool_calls:
                    function = call.get("function") or {}
                    print(f"[c/tool-call] {function.get('name')}({function.get('arguments')})")
            if tool_calls:
                first = tool_calls[0]
                function = first.get("function") or {}
                try:
                    args = json.loads(function.get("arguments") or "{}")
                    result = float(args["a"]) + float(args["b"])
                    follow_up_messages = [
                        *messages,
                        {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": first.get("id"),
                                    "type": "function",
                                    "function": {
                                        "name": function.get("name"),
                                        "arguments": function.get("arguments"),
                                    },
                                }
                            ],
                        },
                        {"role": "tool", "tool_call_id": first.get("id"), "content": str(result)},
                    ]
                    follow = post(
                        "c/tool-result",
                        {
                            "model": model,
                            "messages": follow_up_messages,
                            "tool_choice": "none",
                            "max_tokens": MAX_TOKENS,
                        },
                    )
                    if follow is not None:
                        follow_choices = follow.get("choices") or []
                        if follow_choices:
                            text = (follow_choices[0].get("message") or {}).get("content")
                            print(f"[c/tool-result] content: {_preview(str(text))}")
                except (ValueError, KeyError, TypeError) as exc:
                    print(f"[c/tool-result] SKIPPED: bad tool arguments ({exc})")

        # (d) Deliberately malformed request (no generation cost expected).
        body = post("d/malformed", {})
        if body is not None:
            print(f"[d/malformed] error body: {_preview(json.dumps(body))}")

    print(f"calls made: {calls}/{MAX_CALLS}")
    print(f"total usage: prompt={total_prompt_tokens} completion={total_completion_tokens}")
    print("Probe (e), a rate-limit probe, was deliberately skipped: hammering limits is unsafe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
