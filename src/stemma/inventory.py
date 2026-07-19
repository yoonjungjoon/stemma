"""YAML inventory loader with schema and semantic validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

from .errors import (
    InventoryParseError,
    InventorySchemaError,
    InventorySemanticError,
    PathValidationError,
)
from .models import Device, DeviceOS, Folder, FolderMode, Inventory, Location
from .path_normalization import normalize_path
from .schema import find_schema_violation

_SCHEMA_FILE = "inventory-v0.0.1.schema.json"


def load_inventory(path: Path) -> Inventory:
    """Read an inventory as UTF-8 YAML and return a fully validated immutable model."""

    source = str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise InventoryParseError("unable to read inventory as UTF-8", source=source) from None

    try:
        document: object = yaml.safe_load(text)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        raise InventoryParseError(
            "malformed YAML",
            source=source,
            line=None if mark is None else mark.line + 1,
            column=None if mark is None else mark.column + 1,
        ) from None

    violation = find_schema_violation(document, _SCHEMA_FILE)
    if violation is not None:
        raise InventorySchemaError(
            violation.detail,
            source=source,
            pointer=violation.pointer,
        )

    data = cast(dict[str, Any], document)
    devices = tuple(
        Device(id=item["id"], name=item["name"], os=DeviceOS(item["os"]))
        for item in cast(list[dict[str, str]], data["devices"])
    )
    folders = tuple(_make_folder(item) for item in cast(list[dict[str, Any]], data["folders"]))
    inventory = Inventory(schema_version=data["schema_version"], devices=devices, folders=folders)
    validate_inventory(inventory, source=source)
    return inventory


def _make_folder(item: dict[str, Any]) -> Folder:
    locations = tuple(
        Location(
            device_id=location["device_id"],
            path=location["path"],
            mode=FolderMode(location["mode"]),
        )
        for location in cast(list[dict[str, str]], item["locations"])
    )
    return Folder(id=item["id"], label=item.get("label"), locations=locations)


def validate_inventory(inventory: Inventory, *, source: str = "inventory") -> None:
    """Validate cross-field and OS-specific invariants of an inventory domain object."""

    device_indexes: dict[str, int] = {}
    for index, device in enumerate(inventory.devices):
        if device.id in device_indexes:
            raise InventorySemanticError(
                "duplicate device id",
                source=source,
                pointer=f"/devices/{index}/id",
            )
        device_indexes[device.id] = index

    folder_ids: set[str] = set()
    devices = {device.id: device for device in inventory.devices}
    for folder_index, folder in enumerate(inventory.folders):
        if folder.id in folder_ids:
            raise InventorySemanticError(
                "duplicate folder id",
                source=source,
                pointer=f"/folders/{folder_index}/id",
            )
        folder_ids.add(folder.id)

        location_devices: set[str] = set()
        for location_index, location in enumerate(folder.locations):
            pointer = f"/folders/{folder_index}/locations/{location_index}"
            if location.device_id in location_devices:
                raise InventorySemanticError(
                    "duplicate location for device",
                    source=source,
                    pointer=f"{pointer}/device_id",
                )
            location_devices.add(location.device_id)

            referenced_device = devices.get(location.device_id)
            if referenced_device is None:
                raise InventorySemanticError(
                    "location references an unknown device",
                    source=source,
                    pointer=f"{pointer}/device_id",
                )
            try:
                normalize_path(location.path, referenced_device.os)
            except PathValidationError as error:
                raise InventorySemanticError(
                    error.detail,
                    source=source,
                    pointer=f"{pointer}/path",
                ) from None
