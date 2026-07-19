"""Allowlist-based deterministic serialization for Catalog results."""

from __future__ import annotations

import json

from .models import ActualFolder, Catalog, CatalogEntry, Drift, DriftKind, Location

_DRIFT_ORDER = {
    DriftKind.MISSING: 0,
    DriftKind.PATH_MISMATCH: 1,
    DriftKind.MODE_MISMATCH: 2,
}


def serialize_catalog(catalog: Catalog) -> str:
    """Return canonical JSON text with exactly one trailing newline."""

    entries = sorted(catalog.entries, key=lambda entry: (entry.folder_id, entry.device_id))
    document: dict[str, object] = {
        "schema_version": catalog.schema_version,
        "entries": [_entry_document(entry) for entry in entries],
    }
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def _entry_document(entry: CatalogEntry) -> dict[str, object]:
    drifts = sorted(entry.drifts, key=lambda drift: _DRIFT_ORDER[drift.kind])
    return {
        "folder_id": entry.folder_id,
        "folder_label": entry.folder_label,
        "device_id": entry.device_id,
        "device_name": entry.device_name,
        "desired": _desired_document(entry.desired),
        "actual": None if entry.actual is None else _actual_document(entry.actual),
        "state": entry.state.value,
        "drifts": [_drift_document(drift) for drift in drifts],
    }


def _desired_document(desired: Location) -> dict[str, str]:
    return {
        "device_id": desired.device_id,
        "path": desired.path,
        "mode": desired.mode.value,
    }


def _actual_document(actual: ActualFolder) -> dict[str, str]:
    return {
        "id": actual.id,
        "path": actual.path,
        "mode": actual.mode.value,
    }


def _drift_document(drift: Drift) -> dict[str, str | None]:
    return {
        "kind": drift.kind.value,
        "reason": drift.reason,
        "expected": drift.expected,
        "actual": drift.actual,
    }
