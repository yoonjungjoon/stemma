from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import snapshot_document, write_json

from stemma import (
    ActualFolder,
    DeviceSnapshot,
    DuplicateSnapshotError,
    FolderMode,
    SnapshotParseError,
    SnapshotSchemaError,
    SnapshotSemanticError,
    load_inventory,
    load_snapshots,
    validate_snapshots,
)


def test_loads_valid_snapshots_and_accepts_empty_batch(
    inventory_path: Path,
    tmp_path: Path,
) -> None:
    inventory = load_inventory(inventory_path)
    snapshot_path = write_json(tmp_path / "device-a.json", snapshot_document())

    snapshots = load_snapshots([snapshot_path], inventory)

    assert snapshots[0].captured_at == datetime(2026, 7, 19, 13, tzinfo=UTC)
    assert snapshots[0].folders[0].path == "/srv/syncthing/company-docs"
    assert load_snapshots([], inventory) == ()


def test_rejects_malformed_json(inventory_path: Path, tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text('{"device_id":', encoding="utf-8")

    with pytest.raises(SnapshotParseError) as raised:
        load_snapshots([path], load_inventory(inventory_path))

    assert raised.value.source == str(path)
    assert raised.value.line == 1


def test_rejects_timestamp_without_timezone(inventory_path: Path, tmp_path: Path) -> None:
    document = snapshot_document()
    document["captured_at"] = "2026-07-19T13:00:00"

    with pytest.raises(SnapshotSchemaError) as raised:
        load_snapshots(
            [write_json(tmp_path / "snapshot.json", document)],
            load_inventory(inventory_path),
        )

    assert raised.value.pointer == "/captured_at"


def test_rejects_schema_valid_but_unrepresentable_timestamp_as_catalog_error(
    inventory_path: Path,
    tmp_path: Path,
) -> None:
    document = snapshot_document()
    document["captured_at"] = "1990-12-31T23:59:60Z"

    with pytest.raises(SnapshotSchemaError) as raised:
        load_snapshots(
            [write_json(tmp_path / "snapshot.json", document)],
            load_inventory(inventory_path),
        )

    assert type(raised.value) is SnapshotSchemaError
    assert raised.value.pointer == "/captured_at"
    assert "representable" in raised.value.detail


def test_rejects_unsupported_snapshot_schema_version(
    inventory_path: Path,
    tmp_path: Path,
) -> None:
    document = snapshot_document()
    document["schema_version"] = "0.0.2"

    with pytest.raises(SnapshotSchemaError) as raised:
        load_snapshots(
            [write_json(tmp_path / "snapshot.json", document)],
            load_inventory(inventory_path),
        )

    assert raised.value.pointer == "/schema_version"


def test_rejects_duplicate_actual_folder(inventory_path: Path, tmp_path: Path) -> None:
    document = snapshot_document()
    document["folders"].append(document["folders"][0].copy())

    with pytest.raises(SnapshotSemanticError, match="duplicate folder id"):
        load_snapshots(
            [write_json(tmp_path / "snapshot.json", document)],
            load_inventory(inventory_path),
        )


def test_rejects_unknown_snapshot_device_with_file_pointer(
    inventory_path: Path,
    tmp_path: Path,
) -> None:
    path = write_json(tmp_path / "device-a1.json", snapshot_document(device_id="DEVICE-A1"))

    with pytest.raises(SnapshotSemanticError) as raised:
        load_snapshots([path], load_inventory(inventory_path))

    assert raised.value.source == str(path)
    assert raised.value.pointer == "/device_id"
    assert "unknown inventory device" in raised.value.detail
    assert "device_snapshot_missing" not in str(raised.value)


def test_rejects_duplicate_device_snapshots(inventory_path: Path, tmp_path: Path) -> None:
    first = write_json(tmp_path / "first.json", snapshot_document())
    second = write_json(tmp_path / "second.json", snapshot_document())

    with pytest.raises(DuplicateSnapshotError) as raised:
        load_snapshots([first, second], load_inventory(inventory_path))

    assert raised.value.source == str(second)
    assert raised.value.pointer == "/device_id"
    assert str(first) in raised.value.detail


def test_windows_snapshot_path_is_validated_as_windows_on_any_host(
    inventory_path: Path,
    tmp_path: Path,
) -> None:
    inventory = load_inventory(inventory_path)
    valid = snapshot_document("DEVICE-W", r"c:/Users/Editor/Docs")
    assert load_snapshots([write_json(tmp_path / "valid.json", valid)], inventory)

    invalid = snapshot_document("DEVICE-W", "/host/posix/path")
    with pytest.raises(SnapshotSemanticError) as raised:
        load_snapshots([write_json(tmp_path / "invalid.json", invalid)], inventory)
    assert raised.value.pointer == "/folders/0/path"


def test_macos_snapshot_path_uses_inventory_device_os(
    inventory_path: Path,
    tmp_path: Path,
) -> None:
    inventory = load_inventory(inventory_path)
    valid = snapshot_document("DEVICE-M", "/Users/editor/Documents")
    assert load_snapshots([write_json(tmp_path / "mac-valid.json", valid)], inventory)

    invalid = snapshot_document("DEVICE-M", r"C:\Users\editor\Documents")
    with pytest.raises(SnapshotSemanticError) as raised:
        load_snapshots([write_json(tmp_path / "mac-invalid.json", invalid)], inventory)
    assert raised.value.pointer == "/folders/0/path"


def test_direct_batch_validation_enforces_same_rules(inventory_path: Path) -> None:
    inventory = load_inventory(inventory_path)
    first = DeviceSnapshot(
        schema_version="0.0.1",
        captured_at=datetime(2026, 7, 19, tzinfo=UTC),
        device_id="DEVICE-A",
        folders=(ActualFolder("docs", "/srv/docs", FolderMode.SEND_RECEIVE),),
    )

    with pytest.raises(DuplicateSnapshotError):
        validate_snapshots(inventory, [first, first])

    unknown = DeviceSnapshot(
        schema_version="0.0.1",
        captured_at=datetime(2026, 7, 19, tzinfo=UTC),
        device_id="DEVICE-X",
        folders=(),
    )
    with pytest.raises(SnapshotSemanticError, match="unknown inventory device"):
        validate_snapshots(inventory, [unknown])

    wrong_os_path = DeviceSnapshot(
        schema_version="0.0.1",
        captured_at=datetime(2026, 7, 19, tzinfo=UTC),
        device_id="DEVICE-W",
        folders=(ActualFolder("docs", "/posix/path", FolderMode.SEND_RECEIVE),),
    )
    with pytest.raises(SnapshotSemanticError) as raised:
        validate_snapshots(inventory, [wrong_os_path])
    assert raised.value.pointer == "/folders/0/path"
