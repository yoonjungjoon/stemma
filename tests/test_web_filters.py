from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from conftest import web_catalog

from stemma import DriftKind, EntryState
from stemma.web import (
    CatalogQuery,
    QueryValidationError,
    build_catalog_page,
    parse_catalog_query,
)


def test_summary_counts_are_catalog_wide_and_rows_preserve_canonical_order() -> None:
    catalog = web_catalog()
    before = repr(catalog)

    page = build_catalog_page(catalog, CatalogQuery(device_id="DEVICE-B"))

    assert page.summary.total == 4
    assert page.summary.in_sync == 1
    assert page.summary.drifted == 3
    assert page.summary.missing == 2
    assert page.summary.path_mismatch == 1
    assert page.summary.mode_mismatch == 1
    assert page.summary.matching == 1
    assert [(row.folder_id, row.device_id) for row in page.rows] == [("company-docs", "DEVICE-B")]
    assert repr(catalog) == before
    with pytest.raises(FrozenInstanceError):
        page.summary.total = 0  # type: ignore[misc]


def test_missing_actual_remains_none_in_view_model() -> None:
    page = build_catalog_page(web_catalog(), CatalogQuery(drift_kind=DriftKind.MISSING))
    assert len(page.rows) == 2
    assert all(row.actual_path is None and row.actual_mode is None for row in page.rows)
    assert {row.drifts[0].label for row in page.rows} == {
        "Device snapshot missing",
        "Folder missing",
    }


@pytest.mark.parametrize(
    ("query_text", "expected_devices"),
    [
        ("company-docs", {"DEVICE-A", "DEVICE-B", "DEVICE-C"}),
        ("Company Documents", {"DEVICE-A", "DEVICE-B", "DEVICE-C"}),
        ("EDITOR", {"DEVICE-B"}),
        ("/SRV/DOCS", {"DEVICE-A"}),
        ("/users/editor/documents", {"DEVICE-B"}),
        ("MODE_MISMATCH", {"DEVICE-B"}),
        ("device_snapshot_missing", {"DEVICE-C"}),
    ],
)
def test_unicode_casefold_text_search_targets_display_fields(
    query_text: str,
    expected_devices: set[str],
) -> None:
    page = build_catalog_page(web_catalog(), CatalogQuery(q=query_text))
    assert {row.device_id for row in page.rows} == expected_devices


def test_device_state_and_drift_filters_combine_with_and() -> None:
    query = CatalogQuery(
        q="company",
        device_id="DEVICE-B",
        state=EntryState.DRIFTED,
        drift_kind=DriftKind.PATH_MISMATCH,
    )
    page = build_catalog_page(web_catalog(), query)
    assert [(row.folder_id, row.device_id) for row in page.rows] == [("company-docs", "DEVICE-B")]

    no_results = build_catalog_page(
        web_catalog(),
        CatalogQuery(state=EntryState.IN_SYNC, drift_kind=DriftKind.MISSING),
    )
    assert no_results.rows == ()
    assert no_results.summary.matching == 0


def test_empty_q_is_equivalent_to_an_unspecified_filter() -> None:
    catalog = web_catalog()
    parsed = parse_catalog_query([("q", "   ")], catalog)
    assert parsed.q is None
    assert build_catalog_page(catalog, parsed) == build_catalog_page(catalog, CatalogQuery())


def test_device_options_are_sorted_by_name_then_id() -> None:
    page = build_catalog_page(web_catalog(), CatalogQuery())
    assert [(option.name, option.id) for option in page.device_options] == [
        ("backup", "DEVICE-C"),
        ("editor", "DEVICE-B"),
        ("server", "DEVICE-A"),
    ]


@pytest.mark.parametrize(
    ("parameters", "field"),
    [
        ([("unknown", "value")], "unknown"),
        ([("q", "one"), ("q", "two")], "q"),
        ([("q", "x" * 201)], "q"),
        ([("device_id", "DEVICE-X")], "device_id"),
        ([("state", "missing")], "state"),
        ([("drift_kind", "other")], "drift_kind"),
    ],
)
def test_invalid_query_is_rejected_without_retaining_raw_value(
    parameters: list[tuple[str, str]],
    field: str,
) -> None:
    with pytest.raises(QueryValidationError) as raised:
        parse_catalog_query(parameters, web_catalog())
    assert raised.value.field == field
    assert set(vars(raised.value)) == {"field", "detail", "allowed"}


def test_query_parser_maps_domain_enums() -> None:
    parsed = parse_catalog_query(
        [
            ("device_id", "DEVICE-A"),
            ("state", "drifted"),
            ("drift_kind", "missing"),
        ],
        web_catalog(),
    )
    assert parsed.device_id == "DEVICE-A"
    assert parsed.state is EntryState.DRIFTED
    assert parsed.drift_kind is DriftKind.MISSING
