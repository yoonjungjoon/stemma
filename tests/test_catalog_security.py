from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import cast

import pytest

from stemma import SnapshotSchemaError, build_catalog, serialize_catalog

_FIXTURES = Path(__file__).parent / "fixtures" / "reconciliation"
_INVENTORY = _FIXTURES / "inventory-valid.yaml"
_SNAPSHOT = _FIXTURES / "snapshot-device-a.json"
_SECRET = "CATALOG-API-KEY-SENTINEL"


def test_rejects_snapshot_auth_field_without_secret_echo(tmp_path: Path) -> None:
    document = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))
    document["api_key"] = _SECRET
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(SnapshotSchemaError) as raised:
        build_catalog(_INVENTORY, [snapshot])

    assert _SECRET not in str(raised.value)
    assert _SECRET not in repr(raised.value)


def test_catalog_and_serialization_have_no_credential_or_transport_fields() -> None:
    catalog = build_catalog(_INVENTORY, [_SNAPSHOT])
    serialized = serialize_catalog(catalog)

    assert _SECRET not in repr(catalog)
    assert _SECRET not in serialized
    forbidden = {"api_key", "authorization", "headers", "base_url", "raw_snapshot"}
    serialized_keys: set[str] = set()

    def collect_keys(value: object) -> None:
        if isinstance(value, dict):
            for key, child in cast(dict[object, object], value).items():
                if isinstance(key, str):
                    serialized_keys.add(key)
                collect_keys(child)
        elif isinstance(value, list):
            for child in cast(list[object], value):
                collect_keys(child)

    collect_keys(cast(object, json.loads(serialized)))
    assert serialized_keys.isdisjoint(forbidden)


def test_build_catalog_has_no_network_or_write_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_network(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is not allowed during reconciliation")

    def forbidden_write(*args: object, **kwargs: object) -> int:
        raise AssertionError("file writes are not allowed while building a catalog")

    monkeypatch.setattr(socket, "socket", forbidden_network)
    monkeypatch.setattr(Path, "write_text", forbidden_write)

    catalog = build_catalog(_INVENTORY, [_SNAPSHOT])
    assert catalog.entries
