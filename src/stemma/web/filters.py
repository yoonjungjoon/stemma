"""Strict parsing for catalog page query parameters."""

from __future__ import annotations

from collections.abc import Sequence

from stemma.models import Catalog, DriftKind, EntryState

from .view_models import CatalogQuery

_ALLOWED_FIELDS = frozenset({"q", "device_id", "state", "drift_kind"})


class QueryValidationError(ValueError):
    """A secret-safe query error that never retains the submitted value."""

    def __init__(
        self,
        field: str,
        detail: str,
        *,
        allowed: tuple[str, ...] = (),
    ) -> None:
        self.field = field
        self.detail = detail
        self.allowed = allowed
        super().__init__(f"invalid query field {field}: {detail}")


def parse_catalog_query(
    parameters: Sequence[tuple[str, str]],
    catalog: Catalog,
) -> CatalogQuery:
    """Parse a query pair sequence, rejecting duplicates and unknown fields."""

    values: dict[str, str] = {}
    for field, value in parameters:
        if field not in _ALLOWED_FIELDS:
            raise QueryValidationError(field, "unknown query parameter")
        if field in values:
            raise QueryValidationError(field, "parameter must be provided at most once")
        values[field] = value

    query_text = values.get("q")
    if query_text is not None:
        query_text = query_text.strip()
        if not query_text:
            query_text = None
        elif len(query_text) > 200:
            raise QueryValidationError("q", "must be at most 200 characters")

    device_id = values.get("device_id") or None
    if device_id is not None:
        allowed_devices = tuple(sorted({entry.device_id for entry in catalog.entries}))
        if device_id not in allowed_devices:
            raise QueryValidationError(
                "device_id",
                "must identify a device present in the catalog",
                allowed=allowed_devices,
            )

    state = _parse_state(values.get("state"))
    drift_kind = _parse_drift_kind(values.get("drift_kind"))
    return CatalogQuery(
        q=query_text,
        device_id=device_id,
        state=state,
        drift_kind=drift_kind,
    )


def _parse_state(value: str | None) -> EntryState | None:
    if value in {None, ""}:
        return None
    try:
        return EntryState(value)
    except ValueError:
        raise QueryValidationError(
            "state",
            "must be one of the allowed values",
            allowed=tuple(state.value for state in EntryState),
        ) from None


def _parse_drift_kind(value: str | None) -> DriftKind | None:
    if value in {None, ""}:
        return None
    try:
        return DriftKind(value)
    except ValueError:
        raise QueryValidationError(
            "drift_kind",
            "must be one of the allowed values",
            allowed=tuple(kind.value for kind in DriftKind),
        ) from None
