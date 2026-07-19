from __future__ import annotations

import http.client
import socket
import threading
import time

import pytest
import uvicorn
from conftest import web_catalog

from stemma.web import create_app, create_server_config


def _ephemeral_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def test_real_server_suppresses_raw_access_log_and_sensitive_request_data(
    capsys: pytest.CaptureFixture[str],
) -> None:
    port = _ephemeral_port()
    server = uvicorn.Server(create_server_config(create_app(web_catalog()), port=port))
    failures: list[BaseException] = []

    def serve() -> None:
        try:
            server.run()
        except BaseException as error:  # pragma: no cover - reported in main test thread
            failures.append(error)

    thread = threading.Thread(target=serve, name="stemma-test-server", daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)

    assert server.started
    assert failures == []

    query_secret = "sensitive-company-path"
    header_secret = "client-request-id-secret"
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request(
            "GET",
            f"/catalog?q=%2F{query_secret}",
            headers={"X-Request-ID": header_secret, "Authorization": "header-secret"},
        )
        response = connection.getresponse()
        response.read()
        response_id = response.getheader("X-Request-ID")
        status = response.status
    finally:
        connection.close()
        server.should_exit = True
        thread.join(timeout=5)

    assert failures == []
    assert not thread.is_alive()
    assert status == 200
    assert response_id is not None and response_id != header_secret

    captured = capsys.readouterr()
    logs = captured.out + captured.err
    assert query_secret not in logs
    assert "%2Fsensitive" not in logs
    assert header_secret not in logs
    assert "header-secret" not in logs
    assert "GET /catalog?" not in logs
    assert (
        f"event=web_request request_id={response_id} method=GET route=/catalog status=200" in logs
    )
