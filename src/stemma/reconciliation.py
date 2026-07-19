"""Pure desired/actual reconciliation for Stemma catalogs."""

from __future__ import annotations

from collections.abc import Sequence

from .models import (
    ActualFolder,
    Catalog,
    CatalogEntry,
    Device,
    DeviceSnapshot,
    Drift,
    DriftKind,
    EntryState,
    Folder,
    Inventory,
    Location,
)
from .path_normalization import normalize_path
from .snapshot import validate_snapshots

_DRIFT_ORDER = {
    DriftKind.MISSING: 0,
    DriftKind.PATH_MISMATCH: 1,
    DriftKind.MODE_MISMATCH: 2,
}


def reconcile(
    inventory: Inventory,
    snapshots: Sequence[DeviceSnapshot],
) -> Catalog:
    """Compare every desired location with its actual folder, without I/O."""

    validate_snapshots(inventory, snapshots)
    devices_by_id = {device.id: device for device in inventory.devices}
    snapshots_by_device_id = {snapshot.device_id: snapshot for snapshot in snapshots}
    actual_folders_by_device_id = {
        snapshot.device_id: {folder.id: folder for folder in snapshot.folders}
        for snapshot in snapshots
    }

    entries: list[CatalogEntry] = []
    for folder in inventory.folders:
        for desired in folder.locations:
            device = devices_by_id[desired.device_id]
            snapshot = snapshots_by_device_id.get(desired.device_id)
            if snapshot is None:
                entries.append(_missing_device_entry(folder, desired, device))
                continue

            actual = actual_folders_by_device_id[snapshot.device_id].get(folder.id)
            if actual is None:
                entries.append(_missing_folder_entry(folder, desired, device))
                continue

            drifts = _compare_location(desired, actual, device)
            entries.append(_entry(folder, desired, actual, device, drifts))

    entries.sort(key=lambda entry: (entry.folder_id, entry.device_id))
    return Catalog(schema_version="0.0.1", entries=tuple(entries))


def _missing_device_entry(folder: Folder, desired: Location, device: Device) -> CatalogEntry:
    drift = Drift(
        kind=DriftKind.MISSING,
        reason="device_snapshot_missing",
        expected=desired.device_id,
        actual=None,
    )
    return _entry(folder, desired, None, device, (drift,))


def _missing_folder_entry(folder: Folder, desired: Location, device: Device) -> CatalogEntry:
    drift = Drift(
        kind=DriftKind.MISSING,
        reason="folder_missing",
        expected=folder.id,
        actual=None,
    )
    return _entry(folder, desired, None, device, (drift,))


def _compare_location(
    desired: Location,
    actual: ActualFolder,
    device: Device,
) -> tuple[Drift, ...]:
    drifts: list[Drift] = []
    if normalize_path(desired.path, device.os) != normalize_path(actual.path, device.os):
        drifts.append(
            Drift(
                kind=DriftKind.PATH_MISMATCH,
                reason="path_mismatch",
                expected=desired.path,
                actual=actual.path,
            )
        )
    if desired.mode != actual.mode:
        drifts.append(
            Drift(
                kind=DriftKind.MODE_MISMATCH,
                reason="mode_mismatch",
                expected=desired.mode.value,
                actual=actual.mode.value,
            )
        )
    return tuple(sorted(drifts, key=lambda drift: _DRIFT_ORDER[drift.kind]))


def _entry(
    folder: Folder,
    desired: Location,
    actual: ActualFolder | None,
    device: Device,
    drifts: tuple[Drift, ...],
) -> CatalogEntry:
    return CatalogEntry(
        folder_id=folder.id,
        folder_label=folder.label,
        device_id=device.id,
        device_name=device.name,
        desired=desired,
        actual=actual,
        state=EntryState.IN_SYNC if not drifts else EntryState.DRIFTED,
        drifts=drifts,
    )
