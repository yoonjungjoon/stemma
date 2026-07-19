"""Syncthing response adaptation and atomic snapshot serialization."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from stemma.models import ActualFolder, DeviceSnapshot, FolderMode
from stemma.schema import find_schema_violation

from .errors import (
    CollectorConfigurationError,
    SnapshotWriteError,
    SyncthingResponseSchemaError,
)
from .syncthing_api import SyncthingClient

_FOLDERS_ENDPOINT = "/rest/config/folders"
_MODE_MAPPING = {
    "sendreceive": FolderMode.SEND_RECEIVE,
    "sendonly": FolderMode.SEND_ONLY,
    "receiveonly": FolderMode.RECEIVE_ONLY,
    "receiveencrypted": FolderMode.RECEIVE_ENCRYPTED,
    "readwrite": FolderMode.SEND_RECEIVE,
    "readonly": FolderMode.SEND_ONLY,
}


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def collect_snapshot(
    client: SyncthingClient,
    *,
    clock: Clock,
) -> DeviceSnapshot:
    """Collect a complete, schema-valid snapshot without interpreting path syntax."""

    status = client.get_status()
    upstream_folders = client.get_folders()
    if not status.my_id.strip():
        raise SyncthingResponseSchemaError(
            "/rest/system/status",
            "/myID",
            "myID must be a non-blank string",
        )
    captured_at = clock.now()
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise CollectorConfigurationError("collector clock must return a timezone-aware datetime")
    captured_at = captured_at.astimezone(UTC).replace(microsecond=0)

    folder_ids: set[str] = set()
    folders: list[ActualFolder] = []
    for index, folder in enumerate(upstream_folders):
        for field, value in (
            ("id", folder.id),
            ("path", folder.path),
            ("type", folder.folder_type),
        ):
            if not value.strip():
                raise SyncthingResponseSchemaError(
                    _FOLDERS_ENDPOINT,
                    f"/{index}/{field}",
                    f"{field} must be a non-blank string",
                )
        if folder.id in folder_ids:
            raise SyncthingResponseSchemaError(
                _FOLDERS_ENDPOINT,
                f"/{index}/id",
                "folder id must be unique",
            )
        folder_ids.add(folder.id)
        mode = _MODE_MAPPING.get(folder.folder_type)
        if mode is None:
            raise SyncthingResponseSchemaError(
                _FOLDERS_ENDPOINT,
                f"/{index}/type",
                "unsupported Syncthing folder type",
            )
        folders.append(ActualFolder(id=folder.id, path=folder.path, mode=mode))

    snapshot = DeviceSnapshot(
        schema_version="0.0.1",
        captured_at=captured_at,
        device_id=status.my_id,
        folders=tuple(sorted(folders, key=lambda folder: folder.id)),
    )
    violation = find_schema_violation(_snapshot_document(snapshot), "snapshot-v0.0.1.schema.json")
    if violation is not None:  # pragma: no cover - adapter invariants are tested field-by-field
        raise SyncthingResponseSchemaError(
            _FOLDERS_ENDPOINT,
            violation.pointer,
            violation.detail,
        )
    return snapshot


def write_snapshot(snapshot: DeviceSnapshot, output: Path) -> None:
    """Validate and atomically replace ``output`` with deterministic snapshot JSON."""

    document = _snapshot_document(snapshot)
    violation = find_schema_violation(document, "snapshot-v0.0.1.schema.json")
    if violation is not None:
        raise SnapshotWriteError(
            str(output),
            f"snapshot does not satisfy schema: {violation.detail}",
            pointer=violation.pointer,
        )
    payload = json.dumps(document, ensure_ascii=False, indent=2) + "\n"

    temporary_path: Path | None = None
    file_descriptor = -1
    failure: SnapshotWriteError | None = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        if os.name == "posix":
            os.fchmod(file_descriptor, 0o600)
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
            file_descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, output)
        temporary_path = None
    except (OSError, UnicodeError) as error:
        failure = SnapshotWriteError(
            str(output),
            f"unable to write snapshot ({type(error).__name__})",
        )
    finally:
        if file_descriptor >= 0:
            with suppress(OSError):
                os.close(file_descriptor)
        if temporary_path is not None:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)
    if failure is not None:
        raise failure


def _snapshot_document(snapshot: DeviceSnapshot) -> dict[str, object]:
    if snapshot.captured_at.tzinfo is None or snapshot.captured_at.utcoffset() is None:
        timestamp = snapshot.captured_at.isoformat(timespec="seconds")
    else:
        captured_at = snapshot.captured_at.astimezone(UTC).replace(microsecond=0)
        timestamp = captured_at.isoformat(timespec="seconds").replace("+00:00", "Z")
    folders = [
        {"id": folder.id, "path": folder.path, "mode": folder.mode.value}
        for folder in sorted(snapshot.folders, key=lambda item: item.id)
    ]
    return {
        "schema_version": snapshot.schema_version,
        "captured_at": timestamp,
        "device_id": snapshot.device_id,
        "folders": folders,
    }
