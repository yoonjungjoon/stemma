"""Allowlist-based presentation models and pure catalog filtering."""

from __future__ import annotations

from dataclasses import dataclass

from stemma.models import Catalog, CatalogEntry, Drift, DriftKind, EntryState


@dataclass(frozen=True, slots=True)
class CatalogQuery:
    q: str | None = None
    device_id: str | None = None
    state: EntryState | None = None
    drift_kind: DriftKind | None = None


@dataclass(frozen=True, slots=True)
class CatalogSummary:
    total: int
    in_sync: int
    drifted: int
    missing: int
    path_mismatch: int
    mode_mismatch: int
    matching: int


@dataclass(frozen=True, slots=True)
class DriftView:
    kind: str
    reason: str
    label: str


@dataclass(frozen=True, slots=True)
class DeviceOption:
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class CatalogRow:
    state: str
    folder_id: str
    folder_label: str | None
    device_id: str
    device_name: str
    desired_path: str
    actual_path: str | None
    desired_mode: str
    actual_mode: str | None
    drifts: tuple[DriftView, ...]


@dataclass(frozen=True, slots=True)
class CatalogPage:
    query: CatalogQuery
    summary: CatalogSummary
    device_options: tuple[DeviceOption, ...]
    rows: tuple[CatalogRow, ...]


def build_catalog_page(catalog: Catalog, query: CatalogQuery) -> CatalogPage:
    """Build a filtered page while keeping all summary counts catalog-wide."""

    matching_entries = tuple(entry for entry in catalog.entries if _matches(entry, query))
    return CatalogPage(
        query=query,
        summary=_summary(catalog, len(matching_entries)),
        device_options=_device_options(catalog),
        rows=tuple(_row(entry) for entry in matching_entries),
    )


def _summary(catalog: Catalog, matching: int) -> CatalogSummary:
    return CatalogSummary(
        total=len(catalog.entries),
        in_sync=sum(entry.state is EntryState.IN_SYNC for entry in catalog.entries),
        drifted=sum(entry.state is EntryState.DRIFTED for entry in catalog.entries),
        missing=_count_entries_with(catalog, DriftKind.MISSING),
        path_mismatch=_count_entries_with(catalog, DriftKind.PATH_MISMATCH),
        mode_mismatch=_count_entries_with(catalog, DriftKind.MODE_MISMATCH),
        matching=matching,
    )


def _count_entries_with(catalog: Catalog, kind: DriftKind) -> int:
    return sum(any(drift.kind is kind for drift in entry.drifts) for entry in catalog.entries)


def _device_options(catalog: Catalog) -> tuple[DeviceOption, ...]:
    devices = {entry.device_id: entry.device_name for entry in catalog.entries}
    return tuple(
        DeviceOption(id=device_id, name=name)
        for device_id, name in sorted(devices.items(), key=lambda item: (item[1], item[0]))
    )


def _matches(entry: CatalogEntry, query: CatalogQuery) -> bool:
    if query.device_id is not None and entry.device_id != query.device_id:
        return False
    if query.state is not None and entry.state is not query.state:
        return False
    if query.drift_kind is not None and not any(
        drift.kind is query.drift_kind for drift in entry.drifts
    ):
        return False
    return query.q is None or _matches_text(entry, query.q)


def _matches_text(entry: CatalogEntry, query_text: str) -> bool:
    values = [
        entry.folder_id,
        entry.folder_label,
        entry.device_id,
        entry.device_name,
        entry.desired.path,
        None if entry.actual is None else entry.actual.path,
    ]
    values.extend(value for drift in entry.drifts for value in (drift.kind.value, drift.reason))
    folded_query = query_text.casefold()
    return any(value is not None and folded_query in value.casefold() for value in values)


def _row(entry: CatalogEntry) -> CatalogRow:
    return CatalogRow(
        state=entry.state.value,
        folder_id=entry.folder_id,
        folder_label=entry.folder_label,
        device_id=entry.device_id,
        device_name=entry.device_name,
        desired_path=entry.desired.path,
        actual_path=None if entry.actual is None else entry.actual.path,
        desired_mode=entry.desired.mode.value,
        actual_mode=None if entry.actual is None else entry.actual.mode.value,
        drifts=tuple(_drift_view(drift) for drift in entry.drifts),
    )


def _drift_view(drift: Drift) -> DriftView:
    labels = {
        "device_snapshot_missing": "Device snapshot missing",
        "folder_missing": "Folder missing",
        "path_mismatch": "Path mismatch",
        "mode_mismatch": "Mode mismatch",
    }
    return DriftView(
        kind=drift.kind.value,
        reason=drift.reason,
        label=labels.get(drift.reason, "Catalog drift"),
    )
