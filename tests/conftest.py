from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml


def inventory_document() -> dict[str, Any]:
    return {
        "schema_version": "0.0.1",
        "devices": [
            {"id": "DEVICE-A", "name": "server", "os": "linux"},
            {"id": "DEVICE-M", "name": "editor", "os": "darwin"},
            {"id": "DEVICE-W", "name": "workstation", "os": "windows"},
        ],
        "folders": [
            {
                "id": "company-docs",
                "label": "Company documents",
                "locations": [
                    {
                        "device_id": "DEVICE-A",
                        "path": "/srv/syncthing/company-docs",
                        "mode": "sendreceive",
                    },
                    {
                        "device_id": "DEVICE-M",
                        "path": "/Users/editor/company-docs",
                        "mode": "sendonly",
                    },
                    {
                        "device_id": "DEVICE-W",
                        "path": "C:\\Users\\editor\\company-docs",
                        "mode": "receiveonly",
                    },
                ],
            }
        ],
    }


def snapshot_document(
    device_id: str = "DEVICE-A",
    path: str = "/srv/syncthing/company-docs",
) -> dict[str, Any]:
    return {
        "schema_version": "0.0.1",
        "captured_at": "2026-07-19T13:00:00Z",
        "device_id": device_id,
        "folders": [{"id": "company-docs", "path": path, "mode": "sendreceive"}],
    }


@pytest.fixture
def inventory_path(tmp_path: Path) -> Path:
    path = tmp_path / "inventory.yaml"
    path.write_text(yaml.safe_dump(inventory_document(), sort_keys=False), encoding="utf-8")
    return path


def write_yaml(path: Path, document: object) -> Path:
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def write_json(path: Path, document: object) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path
