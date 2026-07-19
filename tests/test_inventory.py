from __future__ import annotations

from pathlib import Path

import pytest
from conftest import inventory_document, write_yaml

from stemma import (
    DeviceOS,
    FolderMode,
    InventoryParseError,
    InventorySchemaError,
    InventorySemanticError,
    load_inventory,
)


def test_loads_valid_inventory_as_immutable_domain_model(inventory_path: Path) -> None:
    inventory = load_inventory(inventory_path)

    assert inventory.schema_version == "0.0.1"
    assert inventory.devices[0].os is DeviceOS.LINUX
    assert inventory.folders[0].locations[1].mode is FolderMode.SEND_ONLY
    assert isinstance(inventory.devices, tuple)
    assert inventory.folders[0].locations[2].path == "C:\\Users\\editor\\company-docs"


def test_rejects_malformed_yaml_with_location(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("devices: [\n", encoding="utf-8")

    with pytest.raises(InventoryParseError) as raised:
        load_inventory(path)

    assert raised.value.source == str(path)
    assert raised.value.line is not None
    assert "malformed YAML" in str(raised.value)


def test_rejects_missing_required_field(tmp_path: Path) -> None:
    document = inventory_document()
    del document["folders"]
    path = write_yaml(tmp_path / "inventory.yaml", document)

    with pytest.raises(InventorySchemaError) as raised:
        load_inventory(path)

    assert raised.value.pointer == "/folders"
    assert "required" in raised.value.detail


def test_rejects_unsupported_inventory_schema_version(tmp_path: Path) -> None:
    document = inventory_document()
    document["schema_version"] = "0.0.2"

    with pytest.raises(InventorySchemaError) as raised:
        load_inventory(write_yaml(tmp_path / "inventory.yaml", document))

    assert raised.value.pointer == "/schema_version"


def test_rejects_unknown_field_and_unsupported_mode(tmp_path: Path) -> None:
    document = inventory_document()
    document["unexpected"] = True
    path = write_yaml(tmp_path / "unknown.yaml", document)
    with pytest.raises(InventorySchemaError, match="unexpected property"):
        load_inventory(path)

    document = inventory_document()
    document["folders"][0]["locations"][0]["mode"] = "rw"
    path = write_yaml(tmp_path / "mode.yaml", document)
    with pytest.raises(InventorySchemaError) as raised:
        load_inventory(path)
    assert raised.value.pointer == "/folders/0/locations/0/mode"


def test_rejects_duplicate_device_folder_and_location(tmp_path: Path) -> None:
    document = inventory_document()
    document["devices"].append(document["devices"][0].copy())
    with pytest.raises(InventorySemanticError, match="duplicate device id"):
        load_inventory(write_yaml(tmp_path / "device.yaml", document))

    document = inventory_document()
    document["folders"].append(document["folders"][0].copy())
    with pytest.raises(InventorySemanticError, match="duplicate folder id"):
        load_inventory(write_yaml(tmp_path / "folder.yaml", document))

    document = inventory_document()
    document["folders"][0]["locations"].append(document["folders"][0]["locations"][0].copy())
    with pytest.raises(InventorySemanticError, match="duplicate location"):
        load_inventory(write_yaml(tmp_path / "location.yaml", document))


def test_rejects_unknown_device_reference(tmp_path: Path) -> None:
    document = inventory_document()
    document["folders"][0]["locations"][0]["device_id"] = "DEVICE-X"

    with pytest.raises(InventorySemanticError) as raised:
        load_inventory(write_yaml(tmp_path / "inventory.yaml", document))

    assert raised.value.pointer == "/folders/0/locations/0/device_id"
    assert "unknown device" in raised.value.detail


@pytest.mark.parametrize("invalid_path", ["relative/path", "/srv/../secret"])
def test_rejects_invalid_inventory_paths(tmp_path: Path, invalid_path: str) -> None:
    document = inventory_document()
    document["folders"][0]["locations"][0]["path"] = invalid_path

    with pytest.raises(InventorySemanticError) as raised:
        load_inventory(write_yaml(tmp_path / "inventory.yaml", document))

    assert raised.value.pointer == "/folders/0/locations/0/path"
