"""JSON snapshot parsing and inventory-aware batch validation."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from .errors import (
    DuplicateSnapshotError,
    PathValidationError,
    SnapshotParseError,
    SnapshotSchemaError,
    SnapshotSemanticError,
)
from .models import ActualFolder, DeviceSnapshot, FolderMode, Inventory
from .path_normalization import normalize_path
from .schema import find_schema_violation

_SCHEMA_FILE = "snapshot-v0.0.1.schema.json"


def load_snapshots(
    paths: Sequence[Path],
    inventory: Inventory,
) -> tuple[DeviceSnapshot, ...]:
    """Load snapshots atomically, then validate the complete inventory-aware batch."""

    snapshots: list[DeviceSnapshot] = []
    sources: list[str] = []
    for path in paths:
        snapshots.append(_load_snapshot(path))
        sources.append(str(path))
    result = tuple(snapshots)
    _validate_snapshots(inventory, result, sources=sources)
    return result


def validate_snapshots(
    inventory: Inventory,
    snapshots: Sequence[DeviceSnapshot],
) -> None:
    """Validate already parsed snapshots against an inventory as one batch."""

    sources = [f"snapshot[{index}]" for index in range(len(snapshots))]
    _validate_snapshots(inventory, snapshots, sources=sources)


def _load_snapshot(path: Path) -> DeviceSnapshot:
    source = str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise SnapshotParseError("unable to read snapshot as UTF-8", source=source) from None

    try:
        document: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise SnapshotParseError(
            "malformed JSON",
            source=source,
            line=error.lineno,
            column=error.colno,
        ) from None

    violation = find_schema_violation(document, _SCHEMA_FILE)
    if violation is not None:
        raise SnapshotSchemaError(
            violation.detail,
            source=source,
            pointer=violation.pointer,
        )

    data = cast(dict[str, Any], document)
    try:
        captured_at = datetime.fromisoformat(cast(str, data["captured_at"]).replace("Z", "+00:00"))
    except ValueError:
        raise SnapshotSchemaError(
            "captured_at is not representable as a supported datetime",
            source=source,
            pointer="/captured_at",
        ) from None
    folders = tuple(
        ActualFolder(id=item["id"], path=item["path"], mode=FolderMode(item["mode"]))
        for item in cast(list[dict[str, str]], data["folders"])
    )
    return DeviceSnapshot(
        schema_version=data["schema_version"],
        captured_at=captured_at,
        device_id=data["device_id"],
        folders=folders,
    )


def _validate_snapshots(
    inventory: Inventory,
    snapshots: Sequence[DeviceSnapshot],
    *,
    sources: Sequence[str],
) -> None:
    devices = {device.id: device for device in inventory.devices}
    seen_devices: dict[str, int] = {}

    for snapshot_index, snapshot in enumerate(snapshots):
        source = sources[snapshot_index]
        if snapshot.schema_version != "0.0.1":
            raise SnapshotSemanticError(
                "unsupported snapshot schema version",
                source=source,
                pointer="/schema_version",
            )
        if snapshot.captured_at.tzinfo is None or snapshot.captured_at.utcoffset() is None:
            raise SnapshotSemanticError(
                "captured_at must include a timezone offset",
                source=source,
                pointer="/captured_at",
            )
        if not snapshot.device_id.strip():
            raise SnapshotSemanticError(
                "device_id must not be blank",
                source=source,
                pointer="/device_id",
            )
        if snapshot.device_id in seen_devices:
            first_source = sources[seen_devices[snapshot.device_id]]
            raise DuplicateSnapshotError(
                f"duplicate device snapshot; first snapshot: {first_source}",
                source=source,
                pointer="/device_id",
            )
        seen_devices[snapshot.device_id] = snapshot_index

        device = devices.get(snapshot.device_id)
        if device is None:
            raise SnapshotSemanticError(
                "snapshot references an unknown inventory device",
                source=source,
                pointer="/device_id",
            )

        folder_ids: set[str] = set()
        for folder_index, folder in enumerate(snapshot.folders):
            pointer = f"/folders/{folder_index}"
            if not folder.id.strip():
                raise SnapshotSemanticError(
                    "folder id must not be blank",
                    source=source,
                    pointer=f"{pointer}/id",
                )
            if folder.id in folder_ids:
                raise SnapshotSemanticError(
                    "duplicate folder id in device snapshot",
                    source=source,
                    pointer=f"{pointer}/id",
                )
            folder_ids.add(folder.id)
            try:
                normalize_path(folder.path, device.os)
            except PathValidationError as error:
                raise SnapshotSemanticError(
                    error.detail,
                    source=source,
                    pointer=f"{pointer}/path",
                ) from None
