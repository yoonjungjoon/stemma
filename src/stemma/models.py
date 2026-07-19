"""Immutable domain and result models shared by catalog stages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class DeviceOS(StrEnum):
    LINUX = "linux"
    DARWIN = "darwin"
    WINDOWS = "windows"


class FolderMode(StrEnum):
    SEND_RECEIVE = "sendreceive"
    SEND_ONLY = "sendonly"
    RECEIVE_ONLY = "receiveonly"
    RECEIVE_ENCRYPTED = "receiveencrypted"


class DriftKind(StrEnum):
    MISSING = "missing"
    PATH_MISMATCH = "path_mismatch"
    MODE_MISMATCH = "mode_mismatch"


class EntryState(StrEnum):
    IN_SYNC = "in_sync"
    DRIFTED = "drifted"


@dataclass(frozen=True, slots=True)
class Device:
    id: str
    name: str
    os: DeviceOS


@dataclass(frozen=True, slots=True)
class Location:
    device_id: str
    path: str
    mode: FolderMode


@dataclass(frozen=True, slots=True)
class Folder:
    id: str
    label: str | None
    locations: tuple[Location, ...]


@dataclass(frozen=True, slots=True)
class Inventory:
    schema_version: str
    devices: tuple[Device, ...]
    folders: tuple[Folder, ...]


@dataclass(frozen=True, slots=True)
class ActualFolder:
    id: str
    path: str
    mode: FolderMode


@dataclass(frozen=True, slots=True)
class DeviceSnapshot:
    schema_version: str
    captured_at: datetime
    device_id: str
    folders: tuple[ActualFolder, ...]


@dataclass(frozen=True, slots=True)
class Drift:
    kind: DriftKind
    reason: str
    expected: str | None = None
    actual: str | None = None


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    folder_id: str
    folder_label: str | None
    device_id: str
    device_name: str
    desired: Location
    actual: ActualFolder | None
    state: EntryState
    drifts: tuple[Drift, ...]


@dataclass(frozen=True, slots=True)
class Catalog:
    schema_version: str
    entries: tuple[CatalogEntry, ...]
