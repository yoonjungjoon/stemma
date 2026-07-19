from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import pytest
from conftest import inventory_document, write_yaml

from stemma import (
    DeviceOS,
    DeviceSnapshot,
    FolderMode,
    SnapshotSemanticError,
    load_inventory,
    load_snapshots,
)
from stemma.collectors import (
    CollectorConfigurationError,
    SyncthingClient,
    SyncthingFolder,
    SyncthingResponseSchemaError,
    SyncthingStatus,
    collect_snapshot,
    write_snapshot,
)


@dataclass(frozen=True)
class FixedClock:
    value: datetime

    def now(self) -> datetime:
        return self.value


class FakeClient:
    def __init__(
        self,
        *,
        status: SyncthingStatus | None = None,
        folders: tuple[SyncthingFolder, ...] = (),
    ) -> None:
        self.status = status or SyncthingStatus("DEVICE-A")
        self.folders = folders
        self.calls: list[str] = []

    def get_status(self) -> SyncthingStatus:
        self.calls.append("status")
        return self.status

    def get_folders(self) -> tuple[SyncthingFolder, ...]:
        self.calls.append("folders")
        return self.folders


def _collect(fake: FakeClient, clock: FixedClock | None = None) -> DeviceSnapshot:
    selected_clock = clock or FixedClock(datetime(2026, 7, 19, 22, 0, 0, 987654, tzinfo=UTC))
    return collect_snapshot(cast(SyncthingClient, cast(object, fake)), clock=selected_clock)


def test_maps_status_and_folders_with_deterministic_order() -> None:
    upstream = (
        SyncthingFolder("z-docs", "/srv/z", "sendonly"),
        SyncthingFolder("a-docs", "/srv/a", "sendreceive"),
    )
    fake = FakeClient(folders=upstream)

    snapshot = _collect(fake)

    assert fake.calls == ["status", "folders"]
    assert snapshot.schema_version == "0.0.1"
    assert snapshot.device_id == "DEVICE-A"
    assert snapshot.captured_at == datetime(2026, 7, 19, 22, tzinfo=UTC)
    assert [folder.id for folder in snapshot.folders] == ["a-docs", "z-docs"]
    assert snapshot.folders[1].mode is FolderMode.SEND_ONLY
    assert upstream[0].folder_type == "sendonly"


@pytest.mark.parametrize(
    ("folder_type", "expected"),
    [
        ("sendreceive", FolderMode.SEND_RECEIVE),
        ("sendonly", FolderMode.SEND_ONLY),
        ("receiveonly", FolderMode.RECEIVE_ONLY),
        ("receiveencrypted", FolderMode.RECEIVE_ENCRYPTED),
        ("readwrite", FolderMode.SEND_RECEIVE),
        ("readonly", FolderMode.SEND_ONLY),
    ],
)
def test_maps_canonical_and_deprecated_folder_modes(
    folder_type: str,
    expected: FolderMode,
) -> None:
    snapshot = _collect(FakeClient(folders=(SyncthingFolder("docs", "/docs", folder_type),)))
    assert snapshot.folders[0].mode is expected


def test_rejects_unknown_mode_duplicate_folder_and_blank_fields() -> None:
    with pytest.raises(SyncthingResponseSchemaError) as raised:
        _collect(FakeClient(folders=(SyncthingFolder("docs", "/docs", "unknown"),)))
    assert raised.value.pointer == "/0/type"

    duplicate = (
        SyncthingFolder("docs", "/one", "sendreceive"),
        SyncthingFolder("docs", "/two", "sendonly"),
    )
    with pytest.raises(SyncthingResponseSchemaError) as raised:
        _collect(FakeClient(folders=duplicate))
    assert raised.value.pointer == "/1/id"

    for folder in (
        SyncthingFolder(" ", "/docs", "sendreceive"),
        SyncthingFolder("docs", " ", "sendreceive"),
        SyncthingFolder("docs", "/docs", " "),
    ):
        with pytest.raises(SyncthingResponseSchemaError):
            _collect(FakeClient(folders=(folder,)))


def test_rejects_blank_device_id_and_naive_clock() -> None:
    with pytest.raises(SyncthingResponseSchemaError) as raised:
        _collect(FakeClient(status=SyncthingStatus(" ")))
    assert raised.value.pointer == "/myID"

    with pytest.raises(CollectorConfigurationError, match="timezone-aware"):
        _collect(FakeClient(), FixedClock(datetime(2026, 7, 19, 13)))


def test_converts_clock_to_utc_and_seconds() -> None:
    local_time = datetime(
        2026,
        7,
        20,
        8,
        30,
        12,
        999999,
        tzinfo=timezone(timedelta(hours=9)),
    )
    snapshot = _collect(FakeClient(), FixedClock(local_time))
    assert snapshot.captured_at == datetime(2026, 7, 19, 23, 30, 12, tzinfo=UTC)


def test_preserves_windows_path_without_os_validation() -> None:
    windows_path = r"C:\Users\editor\Documents\company-docs"
    snapshot = _collect(
        FakeClient(folders=(SyncthingFolder("company-docs", windows_path, "sendreceive"),))
    )
    assert snapshot.folders[0].path == windows_path


def test_generated_snapshot_is_compatible_with_pr1_loader(tmp_path: Path) -> None:
    windows_path = r"C:\Users\editor\Documents\company-docs"
    snapshot = _collect(
        FakeClient(
            status=SyncthingStatus("DEVICE-W"),
            folders=(SyncthingFolder("company-docs", windows_path, "sendreceive"),),
        )
    )
    snapshot_path = tmp_path / "device-inventory.json"
    write_snapshot(snapshot, snapshot_path)

    inventory_data = inventory_document()
    inventory_data["folders"][0]["locations"][2]["path"] = windows_path
    inventory = load_inventory(write_yaml(tmp_path / "inventory.yaml", inventory_data))
    loaded = load_snapshots([snapshot_path], inventory)

    assert loaded == (snapshot,)
    assert inventory.devices[2].os is DeviceOS.WINDOWS


def test_os_invalid_path_is_rejected_by_pr1_not_collector(tmp_path: Path) -> None:
    snapshot = _collect(
        FakeClient(
            status=SyncthingStatus("DEVICE-W"),
            folders=(SyncthingFolder("company-docs", "/posix/on/windows", "sendreceive"),),
        )
    )
    assert snapshot.folders[0].path == "/posix/on/windows"
    snapshot_path = tmp_path / "device-inventory.json"
    write_snapshot(snapshot, snapshot_path)
    inventory = load_inventory(write_yaml(tmp_path / "inventory.yaml", inventory_document()))

    with pytest.raises(SnapshotSemanticError):
        load_snapshots([snapshot_path], inventory)


def test_snapshot_contains_only_schema_fields(tmp_path: Path) -> None:
    snapshot = _collect(FakeClient(folders=(SyncthingFolder("docs", "/docs", "sendreceive"),)))
    output = tmp_path / "snapshot.json"
    write_snapshot(snapshot, output)
    document = json.loads(output.read_text(encoding="utf-8"))

    assert set(document) == {"schema_version", "captured_at", "device_id", "folders"}
    assert set(document["folders"][0]) == {"id", "path", "mode"}
