"""File-based application service for building a validated Catalog."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from .inventory import load_inventory
from .models import Catalog
from .reconciliation import reconcile
from .snapshot import load_snapshots


def build_catalog(
    inventory_path: Path,
    snapshot_paths: Sequence[Path],
) -> Catalog:
    """Load validated inputs and reconcile them without writing any output."""

    inventory = load_inventory(inventory_path)
    snapshots = load_snapshots(snapshot_paths, inventory)
    return reconcile(inventory, snapshots)
