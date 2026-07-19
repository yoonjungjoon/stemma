"""Secret-safe errors for Syncthing collection and snapshot output."""

from __future__ import annotations


class CollectorError(RuntimeError):
    """Base collector error containing sanitized scalar diagnostics only."""

    def __init__(
        self,
        detail: str,
        *,
        code: str,
        endpoint: str | None = None,
        status_code: int | None = None,
        timeout_kind: str | None = None,
        timeout_seconds: float | None = None,
        host: str | None = None,
        pointer: str | None = None,
        output: str | None = None,
    ) -> None:
        self.detail = detail
        self.code = code
        self.endpoint = endpoint
        self.status_code = status_code
        self.timeout_kind = timeout_kind
        self.timeout_seconds = timeout_seconds
        self.host = host
        self.pointer = pointer
        self.output = output
        super().__init__(self._render())

    def _render(self) -> str:
        location = self.endpoint or self.output or self.host
        if location and self.pointer:
            location += f"#{self.pointer}"
        elif self.pointer:
            location = self.pointer
        prefix = f"{location}: " if location else ""
        suffix = f" (HTTP {self.status_code})" if self.status_code is not None else ""
        return f"{prefix}{self.detail}{suffix}"


class CollectorConfigurationError(CollectorError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail, code="configuration")


class SyncthingAuthenticationError(CollectorError):
    def __init__(self, endpoint: str, status_code: int) -> None:
        super().__init__(
            "Syncthing API authentication failed",
            code="authentication",
            endpoint=endpoint,
            status_code=status_code,
        )


class SyncthingTimeoutError(CollectorError):
    def __init__(self, endpoint: str, timeout_kind: str, timeout_seconds: float) -> None:
        super().__init__(
            f"Syncthing {timeout_kind} timeout after {timeout_seconds:g} seconds",
            code="timeout",
            endpoint=endpoint,
            timeout_kind=timeout_kind,
            timeout_seconds=timeout_seconds,
        )


class SyncthingTLSVerificationError(CollectorError):
    def __init__(self, host: str) -> None:
        super().__init__(
            "TLS certificate verification failed; configure a trusted certificate or CA bundle",
            code="tls_verification",
            host=host,
        )


class SyncthingUnavailableError(CollectorError):
    def __init__(self, host: str) -> None:
        super().__init__(
            "unable to connect to the Syncthing API",
            code="unavailable",
            host=host,
        )


class SyncthingHTTPError(CollectorError):
    def __init__(self, endpoint: str, status_code: int) -> None:
        super().__init__(
            "unexpected Syncthing HTTP status",
            code="http_status",
            endpoint=endpoint,
            status_code=status_code,
        )


class SyncthingResponseError(CollectorError):
    def __init__(self, endpoint: str, detail: str) -> None:
        super().__init__(detail, code="response", endpoint=endpoint)


class SyncthingResponseSchemaError(SyncthingResponseError):
    def __init__(self, endpoint: str, pointer: str, detail: str) -> None:
        CollectorError.__init__(
            self,
            detail,
            code="response_schema",
            endpoint=endpoint,
            pointer=pointer,
        )


class SnapshotWriteError(CollectorError):
    def __init__(self, output: str, detail: str, *, pointer: str | None = None) -> None:
        super().__init__(
            detail,
            code="snapshot_write",
            output=output,
            pointer=pointer,
        )
