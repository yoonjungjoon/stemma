from __future__ import annotations

import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from stemma import ActualFolder, DeviceSnapshot, FolderMode
from stemma.collectors import SnapshotWriteError, write_snapshot


def _snapshot(*folders: ActualFolder) -> DeviceSnapshot:
    return DeviceSnapshot(
        schema_version="0.0.1",
        captured_at=datetime(2026, 7, 19, 13, 0, 0, 123456, tzinfo=UTC),
        device_id="DEVICE-A",
        folders=folders,
    )


def test_writes_deterministic_utf8_json_with_lf_and_final_newline(tmp_path: Path) -> None:
    output = tmp_path / "device-inventory.json"
    snapshot = _snapshot(
        ActualFolder("z-docs", "/문서/z", FolderMode.SEND_ONLY),
        ActualFolder("a-docs", "/문서/a", FolderMode.SEND_RECEIVE),
    )

    write_snapshot(snapshot, output)
    first = output.read_bytes()
    write_snapshot(snapshot, output)

    assert output.read_bytes() == first
    assert first.endswith(b"\n")
    assert b"\r\n" not in first
    assert "문서" in first.decode("utf-8")
    document = json.loads(first)
    assert list(document) == ["schema_version", "captured_at", "device_id", "folders"]
    assert [folder["id"] for folder in document["folders"]] == ["a-docs", "z-docs"]
    assert document["captured_at"] == "2026-07-19T13:00:00Z"


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions apply only on POSIX")
def test_sets_snapshot_permissions_to_0600(tmp_path: Path) -> None:
    output = tmp_path / "device-inventory.json"
    write_snapshot(_snapshot(), output)
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_atomic_replace_failure_preserves_existing_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "device-inventory.json"
    original = b'{"known":"good"}\n'
    output.write_bytes(original)

    def fail_replace(source: Path, destination: Path) -> None:
        raise PermissionError("sensitive lower-level detail")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(SnapshotWriteError) as raised:
        write_snapshot(_snapshot(), output)

    assert output.read_bytes() == original
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert "sensitive lower-level detail" not in str(raised.value)
    assert not list(tmp_path.glob(".device-inventory.json.*.tmp"))


def test_schema_failure_does_not_replace_existing_snapshot(tmp_path: Path) -> None:
    output = tmp_path / "device-inventory.json"
    output.write_text("existing\n", encoding="utf-8")
    invalid = DeviceSnapshot(
        schema_version="0.0.1",
        captured_at=datetime(2026, 7, 19, 13),
        device_id="DEVICE-A",
        folders=(),
    )

    with pytest.raises(SnapshotWriteError) as raised:
        write_snapshot(invalid, output)

    assert raised.value.pointer == "/captured_at"
    assert output.read_text(encoding="utf-8") == "existing\n"


def test_missing_output_directory_is_a_safe_write_error(tmp_path: Path) -> None:
    output = tmp_path / "missing" / "device-inventory.json"
    with pytest.raises(SnapshotWriteError) as raised:
        write_snapshot(_snapshot(), output)
    assert raised.value.output == str(output)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
