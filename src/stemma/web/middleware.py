"""Request IDs, browser security headers, safe errors, and allowlist access logs."""

from __future__ import annotations

import html
import logging
from typing import cast
from uuid import uuid4

from starlette.responses import HTMLResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .logging import ACCESS_LOGGER_NAME

_CSP = (
    "default-src 'self'; script-src 'none'; object-src 'none'; "
    "base-uri 'none'; frame-ancestors 'none'"
)
_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": _CSP,
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}
_LOGGED_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})


class RequestSecurityMiddleware:
    """ASGI middleware that never logs raw targets, headers, bodies, or exceptions."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.logger = logging.getLogger(ACCESS_LOGGER_NAME)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid4().hex
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        status = 500
        response_started = False

        async def secure_send(message: Message) -> None:
            nonlocal response_started, status
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                headers = list(message.get("headers", []))
                protected = {name.lower().encode("ascii") for name in _SECURITY_HEADERS}
                protected.add(b"x-request-id")
                headers = [
                    (name, value) for name, value in headers if name.lower() not in protected
                ]
                headers.extend(
                    (name.lower().encode("ascii"), value.encode("ascii"))
                    for name, value in _SECURITY_HEADERS.items()
                )
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, secure_send)
        except Exception:
            status = 500
            self.logger.error(
                "event=web_error request_id=%s code=internal_error",
                request_id,
            )
            if not response_started:
                response = HTMLResponse(
                    _internal_error_html(request_id),
                    status_code=500,
                )
                await response(scope, receive, secure_send)
        finally:
            method_value = cast(object, scope.get("method", ""))
            method = (
                method_value
                if isinstance(method_value, str) and method_value in _LOGGED_METHODS
                else "<other>"
            )
            self.logger.info(
                "event=web_request request_id=%s method=%s route=%s status=%d",
                request_id,
                method,
                _route_label(scope),
                status,
            )


def _route_label(scope: Scope) -> str:
    path = scope.get("path")
    if path in {"/", "/catalog"}:
        return cast(str, path)
    if isinstance(path, str) and path.startswith("/static/"):
        return "/static/{path}"
    return "<unmatched>"


def _internal_error_html(request_id: str) -> str:
    safe_request_id = html.escape(request_id, quote=True)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        "<title>Internal server error</title></head><body>"
        "<main><h1>Internal server error</h1>"
        "<p>The request could not be completed.</p>"
        f"<p>Request ID: <code>{safe_request_id}</code></p>"
        "</main></body></html>"
    )
