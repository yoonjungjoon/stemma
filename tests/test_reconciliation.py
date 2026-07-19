from __future__ import annotations

from datetime import UTC, datetime

import pytest

import stemma.reconciliation as reconciliation_module
from stemma import (
    ActualFolder,
    Device,
    DeviceOS,
    DeviceSnapshot,
    DriftKind,
    DuplicateSnapshotError,
    EntryState,
    Folder,
    FolderMode,
    Inventory,
    Location,
    SnapshotSemanticError,
    reconcile,
    serialize_catalog,
)


def _inventory(
    *,
    desired_path: str = "/srv/docs",
    desired_mode: FolderMode = FolderMode.SEND_RECEIVE,
    device_os: DeviceOS = DeviceOS.LINUX,
) -> Inventory:
    return Inventory(
        schema_version="0.0.1",
        devices=(Device("DEVICE-A", "server", device_os),),
        folders=(
            Folder(
                id="docs",
                label="Documents",
                locations=(Location("DEVICE-A", desired_path, desired_mode),),
            ),
        ),
    )


def _snapshot(
    *folders: ActualFolder,
    device_id: str = "DEVICE-A",
) -> DeviceSnapshot:
    return DeviceSnapshot(
        schema_version="0.0.1",
        captured_at=datetime(2026, 7, 19, 13, tzinfo=UTC),
        device_id=device_id,
        folders=folders,
    )


def _actual(
    path: str = "/srv/docs",
    mode: FolderMode = FolderMode.SEND_RECEIVE,
    folder_id: str = "docs",
) -> ActualFolder:
    return ActualFolder(folder_id, path, mode)


def test_same_path_and_mode_is_in_sync() -> None:
    catalog = reconcile(_inventory(), [_snapshot(_actual(path="/srv//./docs/"))])
    entry = catalog.entries[0]

    assert entry.state is EntryState.IN_SYNC
    assert entry.drifts == ()
    assert entry.folder_label == "Documents"
    assert entry.actual == _actual(path="/srv//./docs/")


def test_missing_device_snapshot_has_specific_missing_reason() -> None:
    entry = reconcile(_inventory(), []).entries[0]

    assert entry.state is EntryState.DRIFTED
    assert entry.actual is None
    assert len(entry.drifts) == 1
    assert entry.drifts[0].kind is DriftKind.MISSING
    assert entry.drifts[0].reason == "device_snapshot_missing"
    assert entry.drifts[0].expected == "DEVICE-A"
    assert entry.drifts[0].actual is None


def test_missing_folder_has_specific_missing_reason() -> None:
    entry = reconcile(_inventory(), [_snapshot()]).entries[0]

    assert entry.actual is None
    assert [drift.kind for drift in entry.drifts] == [DriftKind.MISSING]
    assert entry.drifts[0].reason == "folder_missing"
    assert entry.drifts[0].expected == "docs"


def test_path_only_mismatch_preserves_original_paths() -> None:
    entry = reconcile(_inventory(), [_snapshot(_actual(path="/srv/Docs"))]).entries[0]

    assert [drift.kind for drift in entry.drifts] == [DriftKind.PATH_MISMATCH]
    assert entry.drifts[0].reason == "path_mismatch"
    assert entry.drifts[0].expected == "/srv/docs"
    assert entry.drifts[0].actual == "/srv/Docs"


def test_mode_only_mismatch_uses_canonical_values() -> None:
    entry = reconcile(
        _inventory(),
        [_snapshot(_actual(mode=FolderMode.SEND_ONLY))],
    ).entries[0]

    assert [drift.kind for drift in entry.drifts] == [DriftKind.MODE_MISMATCH]
    assert entry.drifts[0].expected == "sendreceive"
    assert entry.drifts[0].actual == "sendonly"


def test_path_and_mode_mismatch_are_both_preserved_in_order() -> None:
    entry = reconcile(
        _inventory(),
        [_snapshot(_actual("/different", FolderMode.SEND_ONLY))],
    ).entries[0]

    assert [drift.kind for drift in entry.drifts] == [
        DriftKind.PATH_MISMATCH,
        DriftKind.MODE_MISMATCH,
    ]
    assert [drift.reason for drift in entry.drifts] == ["path_mismatch", "mode_mismatch"]


def test_missing_does_not_infer_path_or_mode_mismatch() -> None:
    for snapshots in ((), (_snapshot(_actual(folder_id="other")),)):
        entry = reconcile(_inventory(), snapshots).entries[0]
        assert [drift.kind for drift in entry.drifts] == [DriftKind.MISSING]


def test_actual_only_folder_is_ignored() -> None:
    snapshot = _snapshot(
        _actual(),
        _actual(path="/unexpected", folder_id="actual-only"),
    )
    catalog = reconcile(_inventory(), [snapshot])

    assert len(catalog.entries) == 1
    assert catalog.entries[0].folder_id == "docs"


@pytest.mark.parametrize(
    ("device_os", "desired", "actual"),
    [
        (DeviceOS.LINUX, "/srv//docs", "/srv/docs/"),
        (DeviceOS.DARWIN, "/Users/editor/./docs", "/Users/editor/docs/"),
        (DeviceOS.WINDOWS, r"C:\Sync\Docs", "c:/Sync//Docs/"),
        (DeviceOS.WINDOWS, r"\\server\share\Docs", "\\\\server\\\\share\\Docs\\"),
    ],
)
def test_uses_target_device_os_path_normalization(
    device_os: DeviceOS,
    desired: str,
    actual: str,
) -> None:
    entry = reconcile(
        _inventory(desired_path=desired, device_os=device_os),
        [_snapshot(_actual(path=actual))],
    ).entries[0]
    assert entry.state is EntryState.IN_SYNC


def test_passes_same_inventory_device_os_to_desired_and_actual_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, DeviceOS]] = []
    original = reconciliation_module.normalize_path

    def recording_normalizer(path: str, device_os: DeviceOS) -> str:
        calls.append((path, device_os))
        return original(path, device_os)

    monkeypatch.setattr(reconciliation_module, "normalize_path", recording_normalizer)
    reconcile(
        _inventory(desired_path=r"C:\Sync\Docs", device_os=DeviceOS.WINDOWS),
        [_snapshot(_actual(path="c:/Sync/Docs/"))],
    )

    assert calls == [
        (r"C:\Sync\Docs", DeviceOS.WINDOWS),
        ("c:/Sync/Docs/", DeviceOS.WINDOWS),
    ]


def test_rejects_unknown_and_duplicate_snapshot_before_indexing() -> None:
    unknown = _snapshot(device_id="DEVICE-X")
    with pytest.raises(SnapshotSemanticError, match="unknown inventory device"):
        reconcile(_inventory(), [unknown])

    duplicate = _snapshot(_actual())
    with pytest.raises(DuplicateSnapshotError):
        reconcile(_inventory(), [duplicate, duplicate])


def test_reconciliation_is_deterministic_idempotent_and_does_not_mutate_inputs() -> None:
    devices = (
        Device("DEVICE-B", "editor", DeviceOS.LINUX),
        Device("DEVICE-A", "server", DeviceOS.LINUX),
    )
    folders = (
        Folder("z-folder", None, (Location("DEVICE-B", "/z", FolderMode.SEND_ONLY),)),
        Folder(
            "a-folder",
            "A folder",
            (
                Location("DEVICE-B", "/a/b", FolderMode.SEND_ONLY),
                Location("DEVICE-A", "/a/a", FolderMode.SEND_RECEIVE),
            ),
        ),
    )
    inventory = Inventory("0.0.1", devices, folders)
    snapshots = (
        _snapshot(
            ActualFolder("z-folder", "/z", FolderMode.SEND_ONLY),
            ActualFolder("a-folder", "/a/b", FolderMode.SEND_ONLY),
            device_id="DEVICE-B",
        ),
        _snapshot(
            ActualFolder("a-folder", "/wrong", FolderMode.RECEIVE_ONLY),
            device_id="DEVICE-A",
        ),
    )
    before = (repr(inventory), repr(snapshots))

    first = reconcile(inventory, snapshots)
    reordered_inventory = Inventory(
        "0.0.1",
        tuple(reversed(devices)),
        tuple(
            Folder(folder.id, folder.label, tuple(reversed(folder.locations)))
            for folder in reversed(folders)
        ),
    )
    reordered_snapshots = tuple(
        DeviceSnapshot(
            item.schema_version,
            item.captured_at,
            item.device_id,
            tuple(reversed(item.folders)),
        )
        for item in reversed(snapshots)
    )
    second = reconcile(reordered_inventory, reordered_snapshots)

    assert first == reconcile(inventory, snapshots)
    assert first == second
    assert serialize_catalog(first) == serialize_catalog(second)
    assert [(entry.folder_id, entry.device_id) for entry in first.entries] == [
        ("a-folder", "DEVICE-A"),
        ("a-folder", "DEVICE-B"),
        ("z-folder", "DEVICE-B"),
    ]
    assert (repr(inventory), repr(snapshots)) == before
