from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import cast

import httpx
from conftest import asgi_request, web_catalog

from stemma import Catalog, CatalogEntry, EntryState, FolderMode, Location
from stemma.web import create_app
from stemma.web.logging import ACCESS_LOGGER_NAME


class RecordHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _capture_requests[Result](
    callback: Callable[[], Result],
) -> tuple[list[str], Result]:
    logger = logging.getLogger(ACCESS_LOGGER_NAME)
    handler = RecordHandler()
    previous_handlers = logger.handlers[:]
    previous_level = logger.level
    previous_propagate = logger.propagate
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        result = callback()
    finally:
        logger.handlers = previous_handlers
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate
    return [record.getMessage() for record in handler.records], result


def test_application_log_contains_only_allowlisted_request_fields() -> None:
    query_secret = "/sensitive/company/path"
    header_secret = "CLIENT-REQUEST-ID-SECRET"

    def request() -> httpx.Response:
        return asgi_request(
            create_app(web_catalog()),
            "GET",
            "/catalog?q=%2Fsensitive%2Fcompany%2Fpath",
            headers={"X-Request-ID": header_secret, "Authorization": "secret-header"},
        )

    messages, response = _capture_requests(request)
    request_message = next(message for message in messages if "event=web_request" in message)
    response_id = response.headers["x-request-id"]

    assert request_message == (
        f"event=web_request request_id={response_id} method=GET route=/catalog status=200"
    )
    assert query_secret not in "\n".join(messages)
    assert "%2Fsensitive" not in "\n".join(messages)
    assert header_secret not in "\n".join(messages)
    assert "secret-header" not in "\n".join(messages)
    assert re.fullmatch(r"[0-9a-f]{32}", response_id)


def test_unknown_sensitive_path_is_logged_as_unmatched() -> None:
    path_secret = "PRIVATE-COMPANY-PATH"
    messages, response = _capture_requests(
        lambda: asgi_request(create_app(web_catalog()), "GET", f"/{path_secret}")
    )

    assert response.status_code == 404
    combined = "\n".join(messages)
    assert path_secret not in combined
    assert "route=<unmatched> status=404" in combined


def test_internal_error_log_has_only_request_id_and_error_code() -> None:
    invalid_mode = cast(FolderMode, object())
    catalog = Catalog(
        "0.0.1",
        (
            CatalogEntry(
                "docs",
                None,
                "DEVICE-A",
                "server",
                Location("DEVICE-A", "/secret/path", invalid_mode),
                None,
                EntryState.IN_SYNC,
                (),
            ),
        ),
    )
    messages, response = _capture_requests(
        lambda: asgi_request(create_app(catalog), "GET", "/catalog")
    )
    response_id = response.headers["x-request-id"]

    assert response.status_code == 500
    assert messages == [
        f"event=web_error request_id={response_id} code=internal_error",
        f"event=web_request request_id={response_id} method=GET route=/catalog status=500",
    ]
    assert "/secret/path" not in "\n".join(messages)
    assert "AttributeError" not in "\n".join(messages)
