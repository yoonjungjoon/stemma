"""Public, secret-safe exceptions raised while loading catalog inputs."""

from __future__ import annotations


class CatalogError(ValueError):
    """Base error containing only sanitized diagnostics, never source documents."""

    def __init__(
        self,
        detail: str,
        *,
        source: str | None = None,
        pointer: str | None = None,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        self.detail = detail
        self.source = source
        self.pointer = pointer
        self.line = line
        self.column = column
        super().__init__(self._render())

    def _render(self) -> str:
        location = self.source or "input"
        if self.line is not None:
            location += f":{self.line}"
            if self.column is not None:
                location += f":{self.column}"
        if self.pointer:
            location += f" {self.pointer}"
        return f"{location}: {self.detail}"


class InventoryParseError(CatalogError):
    """The inventory could not be decoded or parsed as YAML."""


class InventorySchemaError(CatalogError):
    """The parsed inventory does not conform to its JSON Schema."""


class InventorySemanticError(CatalogError):
    """The inventory violates a cross-field or path rule."""


class SnapshotParseError(CatalogError):
    """A snapshot could not be decoded or parsed as JSON."""


class SnapshotSchemaError(CatalogError):
    """A parsed snapshot does not conform to its JSON Schema."""


class SnapshotSemanticError(CatalogError):
    """One or more snapshots violate cross-field or inventory-aware rules."""


class DuplicateSnapshotError(SnapshotSemanticError):
    """More than one snapshot describes the same inventory device."""


class PathValidationError(CatalogError):
    """A path is not an absolute, lexical path for the declared OS."""
