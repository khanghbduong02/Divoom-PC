"""Bearer-token gate for everything except the static editor page."""

from __future__ import annotations

import hmac

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

PROTECTED_PREFIXES = ("/api", "/media", "/ws")


def _extract_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.query_params.get("token")


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """Rejects requests without the local token.

    Browsers cannot set headers on ``<img>`` or WebSocket requests, so the token
    is also accepted as a ``?token=`` query parameter — the agent opens the UI
    with it once and the page keeps it in local storage.
    """

    def __init__(self, app, token: str) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        path = request.url.path
        if any(path == prefix or path.startswith(prefix + "/") for prefix in PROTECTED_PREFIXES):
            supplied = _extract_token(request)
            if not supplied or not hmac.compare_digest(supplied, self._token):
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": (
                            "Missing or invalid token. Open the URL printed by the agent "
                            "(it includes ?token=...) or send Authorization: Bearer <token>."
                        )
                    },
                )
        return await call_next(request)
