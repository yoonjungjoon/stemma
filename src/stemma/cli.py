"""Command-line composition root for the local snapshot exporter."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

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


def _report(error: Exception, exit_code: int) -> int:
    print(str(error), file=sys.stderr)
    return exit_code
