from __future__ import annotations

import json
import ssl
from collections.abc import Callable
from pathlib import Path

import certifi
import httpx
import pytest

from stemma.collectors import (
    DEFAULT_BASE_URL,
    CollectorConfigurationError,
    SyncthingAuthenticationError,
    SyncthingClient,
    SyncthingHTTPError,
    SyncthingResponseError,
    SyncthingResponseSchemaError,
    SyncthingTimeoutError,
    SyncthingTLSVerificationError,
    SyncthingUnavailableError,
)

_API_KEY = "TEST-API-KEY-SENTINEL"
_FIXTURES = Path(__file__).parent / "fixtures" / "syncthing"


def _json_fixture(name: str) -> object:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    base_url: str = DEFAULT_BASE_URL,
    connect_timeout: float = 2.0,
    read_timeout: float = 5.0,
    ca_bundle: Path | None = None,
) -> SyncthingClient:
    return SyncthingClient(
        api_key=_API_KEY,
        transport=httpx.MockTransport(handler),
        base_url=base_url,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        ca_bundle=ca_bundle,
    )


def test_gets_only_allowlisted_endpoints_with_required_headers() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/rest/system/status":
            return httpx.Response(200, json=_json_fixture("status-ok.json"))
        return httpx.Response(200, json=_json_fixture("folders-ok.json"))

    with _client(handler) as client:
        status = client.get_status()
        folders = client.get_folders()
        assert not any(hasattr(client, method) for method in ("post", "put", "patch", "delete"))

    assert status.my_id == "DEVICE-A"
    assert folders[0].id == "company-docs"
    assert [request.method for request in requests] == ["GET", "GET"]
    assert [request.url.path for request in requests] == [
        "/rest/system/status",
        "/rest/config/folders",
    ]
    assert all(request.headers["X-API-Key"] == _API_KEY for request in requests)
    assert all(request.headers["Accept"] == "application/json" for request in requests)


def test_redirect_is_not_followed() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://example.test/stolen"})

    with _client(handler) as client, pytest.raises(SyncthingHTTPError) as raised:
        client.get_status()

    assert raised.value.status_code == 302
    assert len(requests) == 1


@pytest.mark.parametrize(
    ("kind", "seconds"),
    [
        ("connect", 1.25),
        ("read", 3.5),
    ],
)
def test_distinguishes_connect_and_read_timeout(
    kind: str,
    seconds: float,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if kind == "connect":
            raise httpx.ConnectTimeout("connect", request=request)
        raise httpx.ReadTimeout("read", request=request)

    with (
        _client(handler, connect_timeout=1.25, read_timeout=3.5) as client,
        pytest.raises(SyncthingTimeoutError) as raised,
    ):
        client.get_status()

    assert raised.value.timeout_kind == kind
    assert raised.value.timeout_seconds == seconds
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


@pytest.mark.parametrize("status_code", [401, 403])
def test_classifies_authentication_without_response_body(status_code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=f"secret body {_API_KEY}")

    with _client(handler) as client, pytest.raises(SyncthingAuthenticationError) as raised:
        client.get_status()

    assert raised.value.status_code == status_code
    assert _API_KEY not in str(raised.value)
    assert _API_KEY not in repr(raised.value)


def test_classifies_other_http_status_without_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=f"server leaked {_API_KEY}")

    with _client(handler) as client, pytest.raises(SyncthingHTTPError) as raised:
        client.get_folders()

    assert raised.value.status_code == 500
    assert _API_KEY not in str(raised.value)


def test_distinguishes_tls_verification_and_connection_failure() -> None:
    def tls_failure(request: httpx.Request) -> httpx.Response:
        error = httpx.ConnectError("CERTIFICATE_VERIFY_FAILED", request=request)
        error.__cause__ = ssl.SSLCertVerificationError("certificate rejected")
        raise error

    with (
        _client(tls_failure, base_url="https://syncthing.example.test:8384") as client,
        pytest.raises(SyncthingTLSVerificationError) as raised,
    ):
        client.get_status()
    assert raised.value.host == "syncthing.example.test"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None

    def unavailable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    with _client(unavailable) as client, pytest.raises(SyncthingUnavailableError):
        client.get_status()


@pytest.mark.parametrize(
    ("body", "expected_error"),
    [
        (b"not json", SyncthingResponseError),
        (json.dumps([]).encode(), SyncthingResponseError),
        (json.dumps({"uptime": 2}).encode(), SyncthingResponseSchemaError),
    ],
)
def test_rejects_invalid_status_response(
    body: bytes,
    expected_error: type[Exception],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    with _client(handler) as client, pytest.raises(expected_error):
        client.get_status()


@pytest.mark.parametrize(
    ("document", "pointer"),
    [
        ({"folders": []}, None),
        ([{"id": "docs", "path": "/docs"}], "/0/type"),
        ([{"id": "docs", "path": 1, "type": "sendreceive"}], "/0/path"),
        (["not-an-object"], "/0"),
    ],
)
def test_rejects_invalid_folder_response(document: object, pointer: str | None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=document)

    with _client(handler) as client, pytest.raises(SyncthingResponseError) as raised:
        client.get_folders()

    assert raised.value.pointer == pointer


@pytest.mark.parametrize(
    "base_url",
    [
        DEFAULT_BASE_URL,
        "http://127.0.0.1",
        "http://[::1]:8384",
        "https://127.0.0.1:8384",
        "https://syncthing.example.test:8384",
    ],
)
def test_accepts_safe_base_urls(base_url: str) -> None:
    with _client(lambda request: httpx.Response(200, json={}), base_url=base_url) as client:
        assert base_url.rstrip("/") in repr(client)


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost:8384",
        "http://192.0.2.1:8384",
        "ftp://127.0.0.1:8384",
        "http://user:password@127.0.0.1:8384",
        "http://127.0.0.1:8384?api_key=secret",
        "http://127.0.0.1:8384#fragment",
        "http://127.0.0.1:8384/rest/config",
        "http://127.0.0.1:99999",
        "https://example.com\x01:8384",
    ],
)
def test_rejects_unsafe_base_urls(base_url: str) -> None:
    with pytest.raises(CollectorConfigurationError) as raised:
        _client(lambda request: httpx.Response(200), base_url=base_url)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


@pytest.mark.parametrize("timeout", [0.0, -1.0, float("inf"), float("nan")])
def test_rejects_unbounded_or_invalid_timeout(timeout: float) -> None:
    with pytest.raises(CollectorConfigurationError):
        _client(lambda request: httpx.Response(200), connect_timeout=timeout)


def test_requires_non_blank_api_key_before_request() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200)

    with pytest.raises(CollectorConfigurationError):
        SyncthingClient(api_key="  ", transport=httpx.MockTransport(handler))
    assert called is False


@pytest.mark.parametrize(
    "api_key",
    ["", " ", "KEY\tVALUE", "KEY\nVALUE", "KEY\x7fVALUE", "KEY-비밀"],
)
def test_rejects_non_visible_ascii_api_key_before_header_creation(api_key: str) -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200)

    with pytest.raises(CollectorConfigurationError) as raised:
        SyncthingClient(api_key=api_key, transport=httpx.MockTransport(handler))

    assert called is False
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_non_ascii_api_key_is_not_echoed_in_configuration_error() -> None:
    api_key = "API-KEY-비밀-SENTINEL"

    with pytest.raises(CollectorConfigurationError) as raised:
        SyncthingClient(api_key=api_key)

    assert api_key not in str(raised.value)
    assert api_key not in repr(raised.value)
    assert api_key not in repr(raised.value.args)
    assert api_key not in repr(vars(raised.value))


def test_custom_ca_bundle_is_accepted_only_for_https() -> None:
    ca_bundle = Path(certifi.where())
    with _client(
        lambda request: httpx.Response(200, json={}),
        base_url="https://127.0.0.1:8384",
        ca_bundle=ca_bundle,
    ):
        pass

    with pytest.raises(CollectorConfigurationError):
        _client(lambda request: httpx.Response(200), ca_bundle=ca_bundle)


def test_http_client_security_options_are_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    constructor_arguments: dict[str, object] = {}
    real_client = httpx.Client

    def capture_client(*args: object, **kwargs: object) -> httpx.Client:
        constructor_arguments.update(kwargs)
        return real_client(transport=httpx.MockTransport(lambda request: httpx.Response(200)))

    monkeypatch.setattr(httpx, "Client", capture_client)
    client = SyncthingClient(api_key=_API_KEY)
    client.close()

    assert constructor_arguments["trust_env"] is False
    assert constructor_arguments["follow_redirects"] is False
    assert constructor_arguments["verify"] is not False
    assert isinstance(constructor_arguments["timeout"], httpx.Timeout)


@pytest.mark.parametrize(
    ("fixture", "expected_path", "expected_type"),
    [
        ("folders-deprecated-modes.json", "/srv/syncthing/read-write", "readwrite"),
        (
            "folders-windows-path.json",
            r"C:\Users\editor\Documents\company-docs",
            "sendreceive",
        ),
    ],
)
def test_reads_representative_folder_fixtures(
    fixture: str,
    expected_path: str,
    expected_type: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_json_fixture(fixture))

    with _client(handler) as client:
        folder = client.get_folders()[0]
    assert folder.path == expected_path
    assert folder.folder_type == expected_type


def test_rejects_malformed_folder_fixture() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_json_fixture("folders-malformed.json"))

    with _client(handler) as client, pytest.raises(SyncthingResponseSchemaError) as raised:
        client.get_folders()
    assert raised.value.pointer == "/0/path"
