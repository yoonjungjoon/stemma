"""Typed domain and input validation for the Stemma catalog."""

from .catalog import build_catalog
from .errors import (
    CatalogError,
    DuplicateSnapshotError,
    InventoryParseError,
    InventorySchemaError,
    InventorySemanticError,
    PathValidationError,
    SnapshotParseError,
    SnapshotSchemaError,
    SnapshotSemanticError,
)
from .inventory import load_inventory, validate_inventory
from .models import (
    ActualFolder,
    Catalog,
    CatalogEntry,
    Device,
    DeviceOS,
    DeviceSnapshot,
    Drift,
    DriftKind,
    EntryState,
    Folder,
    FolderMode,
    Inventory,
    Location,
)
from .path_normalization import normalize_path
from .reconciliation import reconcile
from .serialization import serialize_catalog
from .snapshot import load_snapshots, validate_snapshots

__all__ = [
    "ActualFolder",
    "Catalog",
    "CatalogEntry",
    "CatalogError",
    "Device",
    "DeviceOS",
    "DeviceSnapshot",
    "Drift",
    "DriftKind",
    "DuplicateSnapshotError",
    "EntryState",
    "Folder",
    "FolderMode",
    "Inventory",
    "InventoryParseError",
    "InventorySchemaError",
    "InventorySemanticError",
    "Location",
    "PathValidationError",
    "SnapshotParseError",
    "SnapshotSchemaError",
    "SnapshotSemanticError",
    "build_catalog",
    "load_inventory",
    "load_snapshots",
    "normalize_path",
    "reconcile",
    "serialize_catalog",
    "validate_inventory",
    "validate_snapshots",
]
