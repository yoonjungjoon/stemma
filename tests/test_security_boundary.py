from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest
from conftest import inventory_document, snapshot_document, write_json, write_yaml

from stemma import (
    Catalog,
    DeviceSnapshot,
    Inventory,
    InventoryParseError,
    InventorySchemaError,
    SnapshotSchemaError,
    load_inventory,
    load_snapshots,
)

_SECRET = "SUPER-SECRET-API-KEY-DO-NOT-ECHO"


def test_inventory_rejects_api_key_without_echoing_value(tmp_path: Path) -> None:
    document = inventory_document()
    document["api_key"] = _SECRET

    with pytest.raises(InventorySchemaError) as raised:
        load_inventory(write_yaml(tmp_path / "inventory.yaml", document))

    assert "api_key" in str(raised.value)
    assert _SECRET not in str(raised.value)
    assert _SECRET not in repr(raised.value)
    assert set(vars(raised.value)) == {"detail", "source", "pointer", "line", "column"}


def test_snapshot_rejects_credentials_without_echoing_value(
    inventory_path: Path,
    tmp_path: Path,
) -> None:
    document = snapshot_document()
    document["authorization"] = _SECRET

    with pytest.raises(SnapshotSchemaError) as raised:
        load_snapshots(
            [write_json(tmp_path / "snapshot.json", document)],
            load_inventory(inventory_path),
        )

    assert _SECRET not in str(raised.value)
    assert _SECRET not in repr(raised.value)


def test_yaml_safe_loader_rejects_python_object_tags(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.yaml"
    path.write_text("!!python/object/apply:os.system ['false']", encoding="utf-8")

    with pytest.raises(InventoryParseError):
        load_inventory(path)


def test_loaders_do_not_modify_input_files(inventory_path: Path, tmp_path: Path) -> None:
    snapshot_path = write_json(tmp_path / "snapshot.json", snapshot_document())
    inventory_before = inventory_path.read_bytes()
    snapshot_before = snapshot_path.read_bytes()

    inventory = load_inventory(inventory_path)
    load_snapshots([snapshot_path], inventory)

    assert inventory_path.read_bytes() == inventory_before
    assert snapshot_path.read_bytes() == snapshot_before


@pytest.mark.parametrize("model_type", [Inventory, DeviceSnapshot, Catalog])
def test_top_level_models_have_no_api_or_transport_fields(model_type: type[object]) -> None:
    names = {field.name.lower() for field in fields(model_type)}  # type: ignore[arg-type]
    assert all(token not in name for name in names for token in ("api", "auth", "header", "raw"))
