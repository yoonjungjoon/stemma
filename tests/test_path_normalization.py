from __future__ import annotations

import pytest

from stemma import CatalogError, DeviceOS, PathValidationError, normalize_path


@pytest.mark.parametrize("os", [DeviceOS.LINUX, DeviceOS.DARWIN])
def test_normalizes_posix_paths_and_preserves_case(os: DeviceOS) -> None:
    source = "//Data///Team/./Docs/"

    assert normalize_path(source, os) == "/Data/Team/Docs"
    assert normalize_path("/Data", os) != normalize_path("/data", os)
    assert source == "//Data///Team/./Docs/"


def test_normalizes_windows_paths_without_using_host_os() -> None:
    assert normalize_path("c:/Users//Editor/./Docs/", DeviceOS.WINDOWS) == (
        "C:\\Users\\Editor\\Docs"
    )
    assert normalize_path("\\\\server\\share\\\\Docs\\", DeviceOS.WINDOWS) == (
        r"\\server\share\Docs"
    )


def test_normalizes_unc_share_root_and_duplicate_server_separator() -> None:
    assert normalize_path(r"\\server\share", DeviceOS.WINDOWS) == r"\\server\share"
    assert normalize_path(r"\\server\\share\Docs", DeviceOS.WINDOWS) == (r"\\server\share\Docs")


def test_path_validation_error_uses_catalog_error_hierarchy() -> None:
    with pytest.raises(CatalogError) as raised:
        normalize_path("relative", DeviceOS.LINUX)
    assert isinstance(raised.value, PathValidationError)


@pytest.mark.parametrize(
    ("path", "os"),
    [
        ("relative/path", DeviceOS.LINUX),
        ("/srv/../secret", DeviceOS.LINUX),
        ("~/docs", DeviceOS.LINUX),
        ("/$STEMMA_ROOT/docs", DeviceOS.LINUX),
        (r"C:\Users\..\secret", DeviceOS.WINDOWS),
        (r"C:relative", DeviceOS.WINDOWS),
        (r"\root-relative", DeviceOS.WINDOWS),
        (r"\\server", DeviceOS.WINDOWS),
        (r"%USERPROFILE%\docs", DeviceOS.WINDOWS),
    ],
)
def test_rejects_non_lexical_or_non_absolute_paths(path: str, os: DeviceOS) -> None:
    with pytest.raises(PathValidationError):
        normalize_path(path, os)
