from __future__ import annotations

import json
from pathlib import Path

import pytest

from stemma import (
    DriftKind,
    DuplicateSnapshotError,
    InventoryParseError,
    SnapshotParseError,
    SnapshotSemanticError,
    build_catalog,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "reconciliation"
_INVENTORY = _FIXTURES / "inventory-valid.yaml"
_SNAPSHOT_A = _FIXTURES / "snapshot-device-a.json"
_SNAPSHOT_B = _FIXTURES / "snapshot-device-b.json"


def test_build_catalog_end_to_end_from_pr1_and_pr2_files() -> None:
    catalog = build_catalog(_INVENTORY, [_SNAPSHOT_B, _SNAPSHOT_A])

    assert [(entry.folder_id, entry.device_id) for entry in catalog.entries] == [
        ("assets", "DEVICE-A"),
        ("company-docs", "DEVICE-A"),
        ("company-docs", "DEVICE-B"),
        ("company-docs", "DEVICE-C"),
    ]
    assert [drift.reason for drift in catalog.entries[0].drifts] == ["folder_missing"]
    assert catalog.entries[1].drifts == ()
    assert [drift.kind for drift in catalog.entries[2].drifts] == [
        DriftKind.PATH_MISMATCH,
        DriftKind.MODE_MISMATCH,
    ]
    assert [drift.reason for drift in catalog.entries[3].drifts] == ["device_snapshot_missing"]


def test_empty_snapshot_batch_marks_every_location_as_device_missing() -> None:
    catalog = build_catalog(_INVENTORY, [])
    assert len(catalog.entries) == 4
    assert all(entry.actual is None for entry in catalog.entries)
    assert all(entry.drifts[0].reason == "device_snapshot_missing" for entry in catalog.entries)


def test_malformed_inventory_preserves_specific_loader_error() -> None:
    with pytest.raises(InventoryParseError) as raised:
        build_catalog(_FIXTURES / "inventory-malformed.yaml", [])
    assert raised.value.source == str(_FIXTURES / "inventory-malformed.yaml")
    assert raised.value.line is not None


def test_malformed_snapshot_prevents_partial_catalog() -> None:
    with pytest.raises(SnapshotParseError) as raised:
        build_catalog(_INVENTORY, [_SNAPSHOT_A, _FIXTURES / "snapshot-malformed.json"])
    assert raised.value.source == str(_FIXTURES / "snapshot-malformed.json")


def test_duplicate_snapshot_and_typo_device_are_input_errors(tmp_path: Path) -> None:
    with pytest.raises(DuplicateSnapshotError):
        build_catalog(_INVENTORY, [_SNAPSHOT_A, _SNAPSHOT_A])

    document = json.loads(_SNAPSHOT_A.read_text(encoding="utf-8"))
    document["device_id"] = "DEVICE-A1"
    typo = tmp_path / "device-a1.json"
    typo.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(SnapshotSemanticError) as raised:
        build_catalog(_INVENTORY, [typo])
    assert raised.value.pointer == "/device_id"


def test_build_catalog_reads_but_does_not_modify_inputs() -> None:
    before = {path: path.read_bytes() for path in (_INVENTORY, _SNAPSHOT_A, _SNAPSHOT_B)}
    build_catalog(_INVENTORY, [_SNAPSHOT_A, _SNAPSHOT_B])
    assert {path: path.read_bytes() for path in before} == before
