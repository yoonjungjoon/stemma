"""Restricted, read-only Syncthing REST client."""

from __future__ import annotations

import math
import ssl
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Never, TypeVar, cast
from urllib.parse import SplitResult, urlsplit, urlunsplit

import httpx

from .errors import (
    CollectorConfigurationError,
    CollectorError,
    SyncthingAuthenticationError,
    SyncthingHTTPError,
    SyncthingResponseError,
    SyncthingResponseSchemaError,
    SyncthingTimeoutError,
    SyncthingTLSVerificationError,
    SyncthingUnavailableError,
)

DEFAULT_BASE_URL = "http://127.0.0.1:8384"
USER_AGENT = "docs-sync-exporter/0.0.1"
_STATUS_ENDPOINT = "/rest/system/status"
_FOLDERS_ENDPOINT = "/rest/config/folders"
_ALLOWED_ENDPOINTS = frozenset({_STATUS_ENDPOINT, _FOLDERS_ENDPOINT})

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class SyncthingStatus:
    my_id: str


@dataclass(frozen=True, slots=True)
class SyncthingFolder:
    id: str
    path: str
    folder_type: str


class SyncthingClient:
    """Syncthing client exposing only the two GET operations needed by PR2."""

    __slots__ = (
        "_base_url",
        "_client",
        "_connect_timeout",
        "_host",
        "_read_timeout",
    )

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        connect_timeout: float | int = 2.0,
        read_timeout: float | int = 5.0,
        ca_bundle: Path | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        api_key = _validate_api_key(api_key)
        normalized_url, parsed = _validate_base_url(base_url)
        self._base_url = normalized_url
        self._host = cast(str, parsed.hostname)
        self._connect_timeout = _validate_timeout(connect_timeout, "connect timeout")
        self._read_timeout = _validate_timeout(read_timeout, "read timeout")

        verify = _tls_verification(parsed, ca_bundle)
        timeout = httpx.Timeout(
            connect=self._connect_timeout,
            read=self._read_timeout,
            write=self._read_timeout,
            pool=self._connect_timeout,
        )
        self._client = httpx.Client(
            headers={
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
                "X-API-Key": api_key,
            },
            timeout=timeout,
            verify=verify,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    def __repr__(self) -> str:
        return (
            f"SyncthingClient(base_url={self._base_url!r}, "
            f"connect_timeout={self._connect_timeout!r}, "
            f"read_timeout={self._read_timeout!r})"
        )

    def __enter__(self) -> SyncthingClient:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def get_status(self) -> SyncthingStatus:
        result = self._request(_STATUS_ENDPOINT, _parse_status)
        if isinstance(result, CollectorError):
            _raise_sanitized(result)
        return result

    def get_folders(self) -> tuple[SyncthingFolder, ...]:
        result = self._request(_FOLDERS_ENDPOINT, _parse_folders)
        if isinstance(result, CollectorError):
            _raise_sanitized(result)
        return result

    def _request(
        self,
        endpoint: str,
        parser: Callable[[object, str], T | CollectorError],
    ) -> T | CollectorError:
        if endpoint not in _ALLOWED_ENDPOINTS:  # pragma: no cover - internal invariant
            return CollectorConfigurationError("endpoint is not in the read-only allowlist")

        try:
            response = self._client.get(f"{self._base_url}{endpoint}")
        except httpx.DecodingError:
            return SyncthingResponseError(endpoint, "response content encoding is invalid")
        except httpx.ConnectTimeout:
            return SyncthingTimeoutError(endpoint, "connect", self._connect_timeout)
        except httpx.ReadTimeout:
            return SyncthingTimeoutError(endpoint, "read", self._read_timeout)
        except httpx.TimeoutException:
            return SyncthingTimeoutError(endpoint, "transport", self._read_timeout)
        except httpx.TransportError as error:
            if _contains_tls_verification_failure(error):
                return SyncthingTLSVerificationError(self._host)
            return SyncthingUnavailableError(self._host)

        if response.status_code in {401, 403}:
            return SyncthingAuthenticationError(endpoint, response.status_code)
        if not 200 <= response.status_code < 300:
            return SyncthingHTTPError(endpoint, response.status_code)
        try:
            document = cast(object, response.json())
        except ValueError:
            return SyncthingResponseError(endpoint, "response is not valid JSON")
        return parser(document, endpoint)


def _validate_base_url(base_url: str) -> tuple[str, SplitResult]:
    if not base_url or any(
        character.isspace() or not character.isprintable() for character in base_url
    ):
        raise CollectorConfigurationError(
            "base URL must contain printable characters without whitespace"
        )
    parsed: SplitResult | None = None
    port: int | None = None
    hostname: str | None = None
    username: str | None = None
    password: str | None = None
    try:
        candidate = urlsplit(base_url)
        candidate_port = candidate.port
        candidate_hostname = candidate.hostname
        candidate_username = candidate.username
        candidate_password = candidate.password
    except (UnicodeError, ValueError):
        pass
    else:
        parsed = candidate
        port = candidate_port
        hostname = candidate_hostname
        username = candidate_username
        password = candidate_password
    if parsed is None:
        raise CollectorConfigurationError("base URL has an invalid host or port")

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise CollectorConfigurationError("base URL scheme must be http or https")
    if hostname is None:
        raise CollectorConfigurationError("base URL must include a host")
    if username is not None or password is not None:
        raise CollectorConfigurationError("base URL must not include credentials")
    if parsed.query or parsed.fragment:
        raise CollectorConfigurationError("base URL must not include a query or fragment")
    if parsed.path not in {"", "/"}:
        raise CollectorConfigurationError("base URL must not include a REST or application path")
    if port is not None and not 1 <= port <= 65535:
        raise CollectorConfigurationError("base URL port must be between 1 and 65535")

    host = hostname.lower()
    if scheme == "http" and host not in {"127.0.0.1", "::1"}:
        raise CollectorConfigurationError(
            "plain HTTP is allowed only for 127.0.0.1 or bracketed [::1]"
        )

    normalized = urlunsplit((scheme, parsed.netloc, "", "", ""))
    urls_are_valid = True
    try:
        httpx.URL(f"{normalized}{_STATUS_ENDPOINT}")
        httpx.URL(f"{normalized}{_FOLDERS_ENDPOINT}")
    except (httpx.InvalidURL, UnicodeError):
        urls_are_valid = False
    if not urls_are_valid:
        raise CollectorConfigurationError("base URL is not a valid HTTP URL")
    normalized_parsed = urlsplit(normalized)
    return normalized, normalized_parsed


def _validate_api_key(api_key: str) -> str:
    if not api_key:
        raise CollectorConfigurationError("SYNCTHING_API_KEY is required and must not be blank")
    if any(not 0x21 <= ord(character) <= 0x7E for character in api_key):
        raise CollectorConfigurationError(
            "SYNCTHING_API_KEY must contain visible ASCII characters only"
        )
    return api_key


def _validate_timeout(value: float | int, name: str) -> float:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        raise CollectorConfigurationError(f"{name} must be a finite positive number")
    return float(value)


def _tls_verification(parsed: SplitResult, ca_bundle: Path | None) -> bool | ssl.SSLContext:
    if parsed.scheme == "http":
        if ca_bundle is not None:
            raise CollectorConfigurationError("CA bundle can be used only with an HTTPS base URL")
        return True
    if ca_bundle is None:
        return True
    if not ca_bundle.is_file():
        raise CollectorConfigurationError("CA bundle must be a readable regular file")

    context: ssl.SSLContext | None = None
    with suppress(OSError, ssl.SSLError):
        context = ssl.create_default_context(cafile=str(ca_bundle))
    if context is None:
        raise CollectorConfigurationError("CA bundle could not be loaded as a certificate bundle")
    return context


def _contains_tls_verification_failure(error: BaseException) -> bool:
    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, ssl.SSLCertVerificationError):
            return True
        if "CERTIFICATE_VERIFY_FAILED" in str(current):
            return True
        current = current.__cause__ or current.__context__
    return False


def _parse_status(document: object, endpoint: str) -> SyncthingStatus | CollectorError:
    if not isinstance(document, dict):
        return SyncthingResponseError(endpoint, "expected a JSON object")
    mapping = cast(dict[object, object], document)
    my_id = mapping.get("myID")
    if not isinstance(my_id, str) or not my_id.strip():
        return SyncthingResponseSchemaError(
            endpoint,
            "/myID",
            "myID must be a non-blank string",
        )
    return SyncthingStatus(my_id=my_id)


def _parse_folders(
    document: object,
    endpoint: str,
) -> tuple[SyncthingFolder, ...] | CollectorError:
    if not isinstance(document, list):
        return SyncthingResponseError(endpoint, "expected a JSON array")

    folders: list[SyncthingFolder] = []
    for index, item in enumerate(cast(list[object], document)):
        if not isinstance(item, dict):
            return SyncthingResponseSchemaError(
                endpoint,
                f"/{index}",
                "folder must be a JSON object",
            )
        mapping = cast(dict[object, object], item)
        values: list[str] = []
        for field in ("id", "path", "type"):
            value = mapping.get(field)
            if not isinstance(value, str) or not value.strip():
                return SyncthingResponseSchemaError(
                    endpoint,
                    f"/{index}/{field}",
                    f"{field} must be a non-blank string",
                )
            values.append(value)
        folders.append(SyncthingFolder(values[0], values[1], values[2]))
    return tuple(folders)


def _raise_sanitized(error: CollectorError) -> Never:
    error.__cause__ = None
    error.__context__ = None
    raise error
