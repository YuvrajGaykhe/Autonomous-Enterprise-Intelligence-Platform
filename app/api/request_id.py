"""
Request correlation IDs for the Layer 1 API (spec Section 10).

Every response carries an X-Request-ID header, and every error envelope
repeats the same value. A client-supplied X-Request-ID is reused only when it
is a short token of safe characters, so it can never inject header or log
content; any other value is replaced by a new UUID4 hex.
"""

from __future__ import annotations

import re
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


def resolve_request_id(candidate: str | None) -> str:
    """Return the client value if it is a safe token, otherwise a new ID."""
    if candidate is not None and _SAFE_REQUEST_ID.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


def request_id_of(request: Request) -> str:
    """The correlation ID RequestIdMiddleware assigned to this request."""
    request_id = getattr(request.state, "request_id", None)
    return request_id if isinstance(request_id, str) else resolve_request_id(None)


class RequestIdMiddleware:
    """Assign the request ID before routing and add it to the response headers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = resolve_request_id(Headers(scope=scope).get(REQUEST_ID_HEADER))
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        await self.app(scope, receive, send_with_request_id)
