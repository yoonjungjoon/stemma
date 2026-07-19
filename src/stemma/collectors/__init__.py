"""Read-only collectors that adapt external systems into Stemma snapshots."""

from .errors import (
    CollectorConfigurationError,
    CollectorError,
    SnapshotWriteError,
    SyncthingAuthenticationError,
    SyncthingHTTPError,
    SyncthingResponseError,
    SyncthingResponseSchemaError,
    SyncthingTimeoutError,
    SyncthingTLSVerificationError,
    SyncthingUnavailableError,
)
from .snapshot import Clock, SystemClock, collect_snapshot, write_snapshot
from .syncthing_api import (
    DEFAULT_BASE_URL,
    SyncthingClient,
    SyncthingFolder,
    SyncthingStatus,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "Clock",
    "CollectorConfigurationError",
    "CollectorError",
    "SnapshotWriteError",
    "SyncthingAuthenticationError",
    "SyncthingClient",
    "SyncthingFolder",
    "SyncthingHTTPError",
    "SyncthingResponseError",
    "SyncthingResponseSchemaError",
    "SyncthingStatus",
    "SyncthingTLSVerificationError",
    "SyncthingTimeoutError",
    "SyncthingUnavailableError",
    "SystemClock",
    "collect_snapshot",
    "write_snapshot",
]
