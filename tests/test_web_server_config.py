from __future__ import annotations

import logging
from typing import cast

import pytest
from conftest import web_catalog

from stemma.web import WebServerConfigurationError, create_app, create_server_config


def test_production_server_disables_access_debug_reload_and_proxy_features() -> None:
    app = create_app(web_catalog())
    config = create_server_config(app)

    assert app.debug is False
    assert config.host == "127.0.0.1"
    assert config.port == 8080
    assert config.access_log is False
    assert config.reload is False
    assert config.workers == 1
    assert config.proxy_headers is False
    assert config.server_header is False
    assert config.date_header is False
    assert config.use_colors is False

    log_config = cast(dict[str, object], config.log_config)
    loggers = cast(dict[str, dict[str, object]], log_config["loggers"])
    assert loggers["uvicorn.access"]["handlers"] == ["discard"]
    assert loggers["uvicorn.access"]["propagate"] is False
    assert loggers["uvicorn.access"]["level"] == "CRITICAL"


def test_environment_cannot_enable_production_debug_reload_or_access_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UVICORN_RELOAD", "true")
    monkeypatch.setenv("UVICORN_ACCESS_LOG", "true")
    monkeypatch.setenv("DEBUG", "true")
    config = create_server_config(create_app(web_catalog()))
    assert config.reload is False
    assert config.access_log is False
    assert config.app.debug is False  # type: ignore[union-attr]


@pytest.mark.parametrize("host", ["0.0.0.0", "localhost", "192.168.1.10", "::", "::1"])
def test_rejects_every_non_ipv4_loopback_bind(host: str) -> None:
    with pytest.raises(WebServerConfigurationError):
        create_server_config(create_app(web_catalog()), host=host)


@pytest.mark.parametrize("port", [0, -1, 65536, True, 8080.5, "8080", None])
def test_rejects_invalid_port(port: object) -> None:
    with pytest.raises(WebServerConfigurationError):
        create_server_config(create_app(web_catalog()), port=cast(int, port))


def test_server_access_logger_does_not_propagate_after_config_creation() -> None:
    create_server_config(create_app(web_catalog()))
    logger = logging.getLogger("uvicorn.access")
    assert logger.propagate is False
    assert all(isinstance(handler, logging.NullHandler) for handler in logger.handlers)
