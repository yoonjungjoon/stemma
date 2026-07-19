"""Command-line composition roots for snapshot export and local catalog viewing."""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from .catalog import build_catalog
from .collectors import (
    DEFAULT_BASE_URL,
    CollectorConfigurationError,
    SnapshotWriteError,
    SyncthingAuthenticationError,
    SyncthingClient,
    SyncthingHTTPError,
    SyncthingResponseError,
    SyncthingTimeoutError,
    SyncthingTLSVerificationError,
    SyncthingUnavailableError,
    SystemClock,
    collect_snapshot,
    write_snapshot,
)
from .errors import CatalogError
from .web import WebServerConfigurationError, create_app, run_server

_URI_WITH_AUTHORITY = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_WINDOWS_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def main(argv: Sequence[str] | None = None) -> int:
    selected_arguments = tuple(sys.argv[1:] if argv is None else argv)
    if any(
        argument == "--api-key" or argument.startswith("--api-key=")
        for argument in selected_arguments
    ):
        print("API keys must be provided only through SYNCTHING_API_KEY", file=sys.stderr)
        return 2
    parser = _parser()
    arguments = parser.parse_args(selected_arguments)
    command = cast(str, arguments.command)
    if command != "snapshot":  # pragma: no cover - argparse requires a command
        parser.error("a command is required")

    base_url = cast(str, arguments.base_url)
    connect_timeout = cast(float, arguments.connect_timeout)
    read_timeout = cast(float, arguments.read_timeout)
    ca_bundle = cast(Path | None, arguments.ca_bundle)
    output = cast(Path, arguments.output)

    try:
        with SyncthingClient(
            api_key=os.environ.get("SYNCTHING_API_KEY", ""),
            base_url=base_url,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            ca_bundle=ca_bundle,
        ) as client:
            snapshot = collect_snapshot(client, clock=SystemClock())
        write_snapshot(snapshot, output)
    except CollectorConfigurationError as error:
        return _report(error, 2)
    except SyncthingAuthenticationError as error:
        return _report(error, 3)
    except (
        SyncthingTimeoutError,
        SyncthingTLSVerificationError,
        SyncthingUnavailableError,
    ) as error:
        return _report(error, 4)
    except (SyncthingHTTPError, SyncthingResponseError) as error:
        return _report(error, 5)
    except SnapshotWriteError as error:
        return _report(error, 6)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="docs-sync-exporter")
    commands = parser.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("snapshot", help="collect a local Syncthing snapshot")
    snapshot.add_argument("--output", type=Path, default=Path("device-inventory.json"))
    snapshot.add_argument("--base-url", default=DEFAULT_BASE_URL)
    snapshot.add_argument("--ca-bundle", type=Path)
    snapshot.add_argument("--connect-timeout", type=float, default=2.0)
    snapshot.add_argument("--read-timeout", type=float, default=5.0)
    return parser


def main_catalog(argv: Sequence[str] | None = None) -> int:
    """Start the loopback-only local catalog viewer after validating all inputs."""

    selected_arguments = tuple(sys.argv[1:] if argv is None else argv)
    parser = _catalog_parser()
    arguments = parser.parse_args(selected_arguments)
    if cast(str, arguments.command) != "web":  # pragma: no cover - required subcommand
        parser.error("a command is required")

    try:
        inventory_path = _local_file(cast(str, arguments.inventory), "inventory")
        snapshot_paths = tuple(
            _local_file(value, "snapshot") for value in cast(list[str], arguments.snapshots)
        )
        catalog = build_catalog(inventory_path, snapshot_paths)
        app = create_app(catalog)
        run_server(
            app,
            host=cast(str, arguments.host),
            port=cast(int, arguments.port),
        )
    except (CatalogError, WebServerConfigurationError) as error:
        return _report(error, 2)
    return 0


def _catalog_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="docs-sync-catalog")
    commands = parser.add_subparsers(dest="command", required=True)
    web = commands.add_parser("web", help="serve a local read-only catalog viewer")
    web.add_argument("--inventory", required=True)
    web.add_argument("--snapshot", dest="snapshots", action="append", default=[])
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8080)
    return parser


def _local_file(value: str, label: str) -> Path:
    if value == "-" or _is_remote_url(value):
        raise WebServerConfigurationError(f"{label} must be an explicit local file path")
    try:
        path = Path(value)
        is_file = path.is_file()
    except (OSError, ValueError):
        raise WebServerConfigurationError(f"{label} must be an existing local file") from None
    if not is_file:
        raise WebServerConfigurationError(f"{label} must be an existing local file")
    return path


def _is_remote_url(value: str) -> bool:
    return _WINDOWS_DRIVE_PATH.match(value) is None and _URI_WITH_AUTHORITY.match(value) is not None


def _report(error: Exception, exit_code: int) -> int:
    print(str(error), file=sys.stderr)
    return exit_code
