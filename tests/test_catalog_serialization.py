from __future__ import annotations

import json
from pathlib import Path

from stemma import (
    Catalog,
    CatalogEntry,
    Drift,
    DriftKind,
    EntryState,
    FolderMode,
    Location,
    build_catalog,
    serialize_catalog,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "reconciliation"


def test_serializes_allowlisted_shape_and_json_values() -> None:
    catalog = build_catalog(
        _FIXTURES / "inventory-valid.yaml",
        [_FIXTURES / "snapshot-device-a.json", _FIXTURES / "snapshot-device-b.json"],
    )

    text = serialize_catalog(catalog)
    document = json.loads(text)
    entry = document["entries"][0]

    assert text.endswith("\n") and not text.endswith("\n\n")
    assert list(document) == ["schema_version", "entries"]
    assert list(entry) == [
        "folder_id",
        "folder_label",
        "device_id",
        "device_name",
        "desired",
        "actual",
        "state",
        "drifts",
    ]
    assert set(entry["desired"]) == {"device_id", "path", "mode"}
    assert entry["actual"] is None
    assert list(entry["drifts"][0]) == ["kind", "reason", "expected", "actual"]
    assert entry["drifts"][0]["actual"] is None


def test_serializer_is_byte_deterministic_and_canonicalizes_input_order() -> None:
    desired_a = Location("DEVICE-A", "/a", FolderMode.SEND_RECEIVE)
    desired_b = Location("DEVICE-B", "/b", FolderMode.SEND_ONLY)
    path_drift = Drift(DriftKind.PATH_MISMATCH, "path_mismatch", "/a", "/x")
    mode_drift = Drift(DriftKind.MODE_MISMATCH, "mode_mismatch", "sendreceive", "sendonly")
    entry_a = CatalogEntry(
        "a",
        None,
        "DEVICE-A",
        "server",
        desired_a,
        None,
        EntryState.DRIFTED,
        (mode_drift, path_drift),
    )
    entry_b = CatalogEntry(
        "b",
        "B",
        "DEVICE-B",
        "editor",
        desired_b,
        None,
        EntryState.DRIFTED,
        (Drift(DriftKind.MISSING, "folder_missing", "b", None),),
    )
    forward = Catalog("0.0.1", (entry_a, entry_b))
    reverse = Catalog("0.0.1", (entry_b, entry_a))

    first = serialize_catalog(forward)
    assert first == serialize_catalog(forward)
    assert first == serialize_catalog(reverse)
    assert [item["kind"] for item in json.loads(first)["entries"][0]["drifts"]] == [
        "path_mismatch",
        "mode_mismatch",
    ]


def test_serializer_preserves_unicode_and_escapes_json_without_writing(tmp_path: Path) -> None:
    desired = Location("DEVICE-A", '/문서/"기획"', FolderMode.SEND_RECEIVE)
    entry = CatalogEntry(
        "문서",
        "기획 문서",
        "DEVICE-A",
        "서버",
        desired,
        None,
        EntryState.DRIFTED,
        (Drift(DriftKind.MISSING, "folder_missing", "문서", None),),
    )

    text = serialize_catalog(Catalog("0.0.1", (entry,)))

    assert "문서" in text
    assert '\\"기획\\"' in text
    assert list(tmp_path.iterdir()) == []
