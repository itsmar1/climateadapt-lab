"""Request body size cap (P11). Oversized bodies get 413, never reach a route."""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from climateadapt.api.errors import REQUEST_TOO_LARGE


class BodyLimitMiddleware:
    """Buffer bodies up to ``max_bytes``; reject larger ones with 413 + code."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                await self.app(scope, receive, send)
                return
            if message["type"] != "http.request":
                continue
            body += message.get("body", b"")
            if len(body) > self.max_bytes:
                response = JSONResponse(
                    status_code=413,
                    content={
                        "detail": [
                            {
                                "loc": [],
                                "msg": (
                                    "Request body exceeds "
                                    f"{self.max_bytes} bytes."
                                ),
                                "type": REQUEST_TOO_LARGE,
                            }
                        ]
                    },
                )
                await response(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if replayed:
                return {"type": "http.request", "body": b"", "more_body": False}
            replayed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)
