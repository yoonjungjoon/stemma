from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from stemma import Catalog, build_catalog
from stemma.web import WebApplication


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


def web_catalog() -> Catalog:
    fixtures = Path(__file__).parent / "fixtures" / "reconciliation"
    return build_catalog(
        fixtures / "inventory-valid.yaml",
        [fixtures / "snapshot-device-a.json", fixtures / "snapshot-device-b.json"],
    )


def asgi_request(
    app: WebApplication,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    follow_redirects: bool = False,
) -> httpx.Response:
    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=follow_redirects,
        ) as client:
            return await client.request(method, path, headers=headers)

    return asyncio.run(send_request())
