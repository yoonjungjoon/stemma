from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from conftest import asgi_request, web_catalog

import stemma.catalog as catalog_module
import stemma.cli as cli_module
from stemma.cli import main_catalog
from stemma.collectors import SyncthingClient
from stemma.web import WebApplication, create_app

_FIXTURES = Path(__file__).parent / "fixtures" / "reconciliation"
_INVENTORY = _FIXTURES / "inventory-valid.yaml"
_SNAPSHOT_A = _FIXTURES / "snapshot-device-a.json"
_SNAPSHOT_B = _FIXTURES / "snapshot-device-b.json"


def _accept_server(app: WebApplication, *, host: str, port: int) -> None:
    assert app.debug is False
    assert host == "127.0.0.1"
    assert port == 8080


def test_cli_builds_catalog_before_starting_local_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[tuple[str, int, bool]] = []

    def capture_server(app: WebApplication, *, host: str, port: int) -> None:
        started.append((host, port, app.debug is False))

    monkeypatch.setattr(cli_module, "run_server", capture_server)
    result = main_catalog(
        [
            "web",
            "--inventory",
            str(_INVENTORY),
            "--snapshot",
            str(_SNAPSHOT_A),
            "--snapshot",
            str(_SNAPSHOT_B),
            "--host",
            "127.0.0.1",
            "--port",
            "9080",
        ]
    )
    assert result == 0
    assert started == [("127.0.0.1", 9080, True)]


@pytest.mark.parametrize(
    ("inventory", "snapshots"),
    [
        (_FIXTURES / "inventory-malformed.yaml", []),
        (_INVENTORY, [_FIXTURES / "snapshot-malformed.json"]),
    ],
)
def test_invalid_inputs_fail_before_server_bind(
    inventory: Path,
    snapshots: list[Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden_server(*args: object, **kwargs: object) -> None:
        raise AssertionError("server must not start for malformed input")

    monkeypatch.setattr(cli_module, "run_server", forbidden_server)
    arguments = ["web", "--inventory", str(inventory)]
    for snapshot in snapshots:
        arguments.extend(("--snapshot", str(snapshot)))

    assert main_catalog(arguments) == 2
    assert str(inventory if "inventory-malformed" in str(inventory) else snapshots[0]) in (
        capsys.readouterr().err
    )


@pytest.mark.parametrize(
    ("inventory", "snapshots"),
    [
        ("-", []),
        ("https://example.test/inventory.yaml", []),
        (str(_FIXTURES), []),
        (str(_INVENTORY), ["-"]),
        (str(_INVENTORY), ["file:///tmp/snapshot.json"]),
        (str(_INVENTORY), [str(_FIXTURES)]),
    ],
)
def test_cli_accepts_only_explicit_existing_local_files(
    inventory: str,
    snapshots: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_server(*args: object, **kwargs: object) -> None:
        raise AssertionError("server must not start for non-file input")

    monkeypatch.setattr(cli_module, "run_server", forbidden_server)
    arguments = ["web", "--inventory", inventory]
    for snapshot in snapshots:
        arguments.extend(("--snapshot", snapshot))
    assert main_catalog(arguments) == 2


def test_cli_accepts_existing_windows_drive_path_form(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = str(_INVENTORY)
    if os.name != "nt":
        value = r"C:\catalog\inventory.yaml"
        monkeypatch.chdir(tmp_path)
        shutil.copyfile(_INVENTORY, Path(value))

    monkeypatch.setattr(cli_module, "run_server", _accept_server)
    assert main_catalog(["web", "--inventory", value]) == 0


@pytest.mark.skipif(os.name == "nt", reason="colon is not valid in a Windows filename")
def test_cli_accepts_existing_posix_filename_with_colon(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = tmp_path / "inventory:prod.yaml"
    shutil.copyfile(_INVENTORY, inventory)
    monkeypatch.setattr(cli_module, "run_server", _accept_server)

    assert main_catalog(["web", "--inventory", str(inventory)]) == 0


@pytest.mark.parametrize("value", ["//[invalid", "\0"])
def test_malformed_local_file_input_returns_safe_configuration_error(
    value: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden_server(*args: object, **kwargs: object) -> None:
        raise AssertionError("server must not start for malformed input")

    monkeypatch.setattr(cli_module, "run_server", forbidden_server)
    assert main_catalog(["web", "--inventory", value]) == 2
    error = capsys.readouterr().err
    assert "inventory must be an existing local file" in error
    assert value not in error


@pytest.mark.parametrize(
    ("host", "port"),
    [("0.0.0.0", "8080"), ("localhost", "8080"), ("127.0.0.1", "0")],
)
def test_cli_rejects_non_loopback_or_invalid_port_without_binding(host: str, port: str) -> None:
    assert (
        main_catalog(
            [
                "web",
                "--inventory",
                str(_INVENTORY),
                "--host",
                host,
                "--port",
                port,
            ]
        )
        == 2
    )


def test_requests_do_not_reload_inputs_call_syncthing_or_write_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(web_catalog())

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("request handling crossed the read-only boundary")

    monkeypatch.setattr(catalog_module, "load_inventory", forbidden)
    monkeypatch.setattr(catalog_module, "load_snapshots", forbidden)
    monkeypatch.setattr(SyncthingClient, "get_status", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)

    response = asgi_request(app, "GET", "/catalog?q=company")
    assert response.status_code == 200
