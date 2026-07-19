"""Locked-down Uvicorn configuration for loopback-only catalog serving."""

from __future__ import annotations

from copy import deepcopy

import uvicorn

from .app import WebApplication
from .logging import SERVER_LOG_CONFIG

_LOOPBACK_HOST = "127.0.0.1"


class WebServerConfigurationError(ValueError):
    """Invalid local viewer bind or input configuration."""


def create_server_config(
    app: WebApplication,
    *,
    host: str = _LOOPBACK_HOST,
    port: int = 8080,
) -> uvicorn.Config:
    """Create production config that cannot inherit debug/access-log environment defaults."""

    _validate_bind(host, port)
    return uvicorn.Config(
        app=app,
        host=host,
        port=port,
        access_log=False,
        reload=False,
        workers=1,
        proxy_headers=False,
        server_header=False,
        date_header=False,
        use_colors=False,
        log_level="info",
        log_config=deepcopy(SERVER_LOG_CONFIG),
    )


def run_server(
    app: WebApplication,
    *,
    host: str = _LOOPBACK_HOST,
    port: int = 8080,
) -> None:
    config = create_server_config(app, host=host, port=port)
    uvicorn.Server(config).run()


def _validate_bind(host: str, port: int) -> None:
    if host != _LOOPBACK_HOST:
        raise WebServerConfigurationError("host must be exactly 127.0.0.1")
    if not _is_valid_port(port):
        raise WebServerConfigurationError("port must be an integer between 1 and 65535")


def _is_valid_port(port: object) -> bool:
    return not isinstance(port, bool) and isinstance(port, int) and 1 <= port <= 65535
