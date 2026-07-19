from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from stemma import (
    ActualFolder,
    Catalog,
    CatalogEntry,
    DeviceOS,
    Drift,
    DriftKind,
    EntryState,
    FolderMode,
    Location,
)


def test_result_models_are_immutable_and_support_multiple_drifts() -> None:
    desired = Location("DEVICE-A", "/desired", FolderMode.SEND_ONLY)
    actual = ActualFolder("docs", "/actual", FolderMode.RECEIVE_ONLY)
    drifts = (
        Drift(DriftKind.PATH_MISMATCH, "path_mismatch", "/desired", "/actual"),
        Drift(DriftKind.MODE_MISMATCH, "mode_mismatch", "sendonly", "receiveonly"),
    )
    entry = CatalogEntry(
        folder_id="docs",
        folder_label=None,
        device_id="DEVICE-A",
        device_name="server",
        desired=desired,
        actual=actual,
        state=EntryState.DRIFTED,
        drifts=drifts,
    )
    catalog = Catalog(schema_version="0.0.1", entries=(entry,))

    assert len(catalog.entries[0].drifts) == 2
    with pytest.raises(FrozenInstanceError):
        catalog.schema_version = "changed"  # type: ignore[misc]


def test_drift_kind_contract_is_exact() -> None:
    assert {kind.value for kind in DriftKind} == {
        "missing",
        "path_mismatch",
        "mode_mismatch",
    }


@pytest.mark.parametrize(
    "model_type",
    [ActualFolder, Catalog, CatalogEntry, Drift, Location],
)
def test_models_have_no_credential_fields(model_type: type[object]) -> None:
    names = {field.name.lower() for field in fields(model_type)}  # type: ignore[arg-type]
    assert all("key" not in name and "auth" not in name and "header" not in name for name in names)


def test_device_os_values_are_stable() -> None:
    assert {os.value for os in DeviceOS} == {"linux", "darwin", "windows"}
