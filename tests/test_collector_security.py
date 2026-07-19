from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import httpx
import pytest

from stemma.cli import main
from stemma.collectors import (
    CollectorError,
    SyncthingAuthenticationError,
    SyncthingClient,
    SyncthingHTTPError,
    SyncthingResponseError,
)

_SECRET = "COLLECTOR-SECRET-API-KEY"


def _exception_graph_text(error: BaseException) -> str:
    seen: set[int] = set()
    pending: list[BaseException] = [error]
    parts: list[str] = []
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        parts.extend((str(current), repr(current), repr(current.args), repr(vars(current))))
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return "\n".join(parts)


def _object_graph_contains_secret(
    value: object,
    secret: str,
    seen: set[int] | None = None,
) -> bool:
    visited: set[int] = set() if seen is None else seen
    if id(value) in visited:
        return False
    visited.add(id(value))

    if isinstance(value, str):
        return secret in value
    if isinstance(value, bytes):
        return secret.encode() in value
    if isinstance(value, httpx.Request):
        return _object_graph_contains_secret(str(value.url), secret, visited) or (
            _object_graph_contains_secret(tuple(value.headers.multi_items()), secret, visited)
        )
    if isinstance(value, BaseException):
        related: tuple[object, ...] = (
            value.args,
            vars(value),
            value.__cause__,
            value.__context__,
        )
        return _object_graph_contains_secret(related, secret, visited)
    if isinstance(value, dict):
        mapping = cast(dict[object, object], value)
        return any(
            _object_graph_contains_secret(item, secret, visited)
            for pair in mapping.items()
            for item in pair
        )
    if isinstance(value, (list, tuple, set, frozenset)):
        values = cast(list[object] | tuple[object, ...] | set[object] | frozenset[object], value)
        return any(_object_graph_contains_secret(item, secret, visited) for item in values)
    return False


@pytest.mark.parametrize("status_code", [401, 500])
def test_key_is_absent_from_errors_and_exception_chains(status_code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=f"body contains {_SECRET}")

    client = SyncthingClient(api_key=_SECRET, transport=httpx.MockTransport(handler))
    expected = SyncthingAuthenticationError if status_code == 401 else SyncthingHTTPError
    try:
        with pytest.raises(expected) as raised:
            client.get_status()
    finally:
        client.close()

    assert isinstance(raised.value, CollectorError)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert _SECRET not in _exception_graph_text(raised.value)


def test_raw_request_exception_is_not_retained() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout(f"request had {_SECRET}", request=request)

    client = SyncthingClient(api_key=_SECRET, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(CollectorError) as raised:
            client.get_status()
    finally:
        client.close()

    assert _SECRET not in _exception_graph_text(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_malformed_content_encoding_does_not_retain_credential_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"Content-Encoding": "gzip"},
            content=b"not-gzip",
        )

    client = SyncthingClient(api_key=_SECRET, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(SyncthingResponseError) as raised:
            client.get_status()
    finally:
        client.close()

    assert raised.value.detail == "response content encoding is invalid"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert _object_graph_contains_secret(requests[0], _SECRET)
    assert not _object_graph_contains_secret(raised.value, _SECRET)


@pytest.mark.parametrize(
    "variable",
    [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
    ],
)
def test_transport_environment_is_ignored(
    variable: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    is_proxy = "PROXY" in variable.upper()
    value = "http://proxy.invalid:9999" if is_proxy else "/invalid/ca"
    monkeypatch.setenv(variable, value)
    received: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(200, json={"myID": "DEVICE-A"})

    uses_http = variable.lower() == "http_proxy"
    base_url = "http://127.0.0.1:8384" if uses_http else "https://127.0.0.1:8384"
    with SyncthingClient(
        api_key=_SECRET,
        base_url=base_url,
        transport=httpx.MockTransport(handler),
    ) as client:
        assert client.get_status().my_id == "DEVICE-A"
    assert len(received) == 1


def test_client_repr_and_snapshot_never_include_key(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/rest/system/status":
            return httpx.Response(200, json={"myID": "DEVICE-A"})
        return httpx.Response(200, json=[])

    with SyncthingClient(api_key=_SECRET, transport=httpx.MockTransport(handler)) as client:
        assert _SECRET not in repr(client)

        from datetime import UTC, datetime

        from stemma.collectors import collect_snapshot, write_snapshot

        class Clock:
            def now(self) -> datetime:
                return datetime(2026, 7, 19, 13, tzinfo=UTC)

        snapshot = collect_snapshot(client, clock=Clock())
    output = tmp_path / "snapshot.json"
    write_snapshot(snapshot, output)
    assert _SECRET not in repr(snapshot)
    assert _SECRET not in output.read_text(encoding="utf-8")
    assert set(json.loads(output.read_text(encoding="utf-8"))) == {
        "schema_version",
        "captured_at",
        "device_id",
        "folders",
    }


def test_cli_has_no_api_key_option_and_fails_before_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("SYNCTHING_API_KEY", raising=False)
    output = tmp_path / "snapshot.json"

    exit_code = main(["snapshot", "--output", str(output)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "SYNCTHING_API_KEY" in captured.err
    assert not output.exists()

    assert main(["snapshot", "--api-key", _SECRET]) == 2
    assert _SECRET not in capsys.readouterr().err

    monkeypatch.setattr("sys.argv", ["docs-sync-exporter", "snapshot", f"--api-key={_SECRET}"])
    assert main() == 2
    assert _SECRET not in capsys.readouterr().err


def test_cli_sanitizes_invalid_environment_api_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invalid_key = "API-KEY-비밀-SENTINEL"
    monkeypatch.setenv("SYNCTHING_API_KEY", invalid_key)

    assert main(["snapshot"]) == 2
    captured = capsys.readouterr()
    assert "visible ASCII" in captured.err
    assert invalid_key not in captured.err
