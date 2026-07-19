"""OS-aware, purely lexical path validation and normalization."""

from __future__ import annotations

import ntpath
import posixpath
import re

from .errors import PathValidationError
from .models import DeviceOS

_ENV_REFERENCE = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*|\{[^}]+\})|%[^%]+%")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


def normalize_path(path: str, os: DeviceOS) -> str:
    """Validate and lexically normalize an absolute path for ``os``.

    No filesystem operation, environment expansion, or home-directory expansion is
    performed. Component spelling and case are preserved apart from an uppercase Windows
    drive letter.
    """

    if not path.strip():
        raise PathValidationError("path must be a non-empty string")
    if "\x00" in path:
        raise PathValidationError("path must not contain a NUL character")
    if path.startswith("~"):
        raise PathValidationError("home-directory expansion is not allowed")
    if _ENV_REFERENCE.search(path):
        raise PathValidationError("environment-variable expansion is not allowed")

    if os in {DeviceOS.LINUX, DeviceOS.DARWIN}:
        return _normalize_posix(path)
    if os is DeviceOS.WINDOWS:
        return _normalize_windows(path)
    raise PathValidationError("unsupported device OS")


def _normalize_posix(path: str) -> str:
    if not path.startswith("/"):
        raise PathValidationError("POSIX path must be absolute")
    if any(component == ".." for component in path.split("/")):
        raise PathValidationError("parent-directory components are not allowed")
    normalized = posixpath.normpath(path)
    return "/" + normalized.lstrip("/")


def _normalize_windows(path: str) -> str:
    components = re.split(r"[\\/]", path)
    if any(component == ".." for component in components):
        raise PathValidationError("parent-directory components are not allowed")

    canonical_separators = path.replace("/", "\\")
    if canonical_separators.startswith("\\\\"):
        return _normalize_unc(canonical_separators)

    drive, tail = ntpath.splitdrive(canonical_separators)
    drive_rooted = bool(_WINDOWS_DRIVE.fullmatch(drive)) and tail.startswith("\\")
    if not drive_rooted:
        raise PathValidationError("Windows path must be drive-rooted or an absolute UNC path")

    normalized = ntpath.normpath(canonical_separators)
    if _WINDOWS_DRIVE.match(normalized):
        normalized = normalized[0].upper() + normalized[1:]
    return normalized


def _normalize_unc(path: str) -> str:
    if path.startswith(("\\\\?\\", "\\\\.\\")):
        raise PathValidationError("Windows device namespace paths are not allowed")

    components = [component for component in path[2:].split("\\") if component not in {"", "."}]
    if len(components) < 2:
        raise PathValidationError("UNC path must include both a server and share name")
    return "\\\\" + "\\".join(components)
