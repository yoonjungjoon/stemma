"""JSON Schema loading and secret-safe diagnostic formatting."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class SchemaViolation:
    pointer: str
    detail: str


type JsonValue = str | int | float | bool | None | dict[str, JsonValue] | list[JsonValue]


def _pointer(parts: list[str | int]) -> str:
    if not parts:
        return "/"
    escaped = (str(part).replace("~", "~0").replace("/", "~1") for part in parts)
    return "/" + "/".join(escaped)


@lru_cache(maxsize=2)
def _load_schema(filename: str) -> dict[str, JsonValue]:
    source_schema = Path(__file__).resolve().parents[2] / "schemas" / filename
    if source_schema.is_file():
        raw = source_schema.read_text(encoding="utf-8")
    else:
        raw = files("stemma").joinpath("_schemas", filename).read_text(encoding="utf-8")
    document = cast(object, json.loads(raw))
    if not isinstance(document, dict):  # pragma: no cover - schemas are release artifacts
        raise RuntimeError(f"invalid bundled schema: {filename}")
    return cast(dict[str, JsonValue], document)


def find_schema_violation(document: object, filename: str) -> SchemaViolation | None:
    """Return the first deterministic validation failure without retaining input data."""

    validator = Draft202012Validator(_load_schema(filename), format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(  # pyright: ignore[reportUnknownMemberType]
            cast(JsonValue, document)
        ),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if not errors:
        return None

    error = errors[0]
    path = list(error.absolute_path)
    detail = _safe_detail(error)

    instance = cast(object, error.instance)
    if error.validator == "required" and isinstance(instance, dict):
        instance_mapping = cast(dict[object, object], instance)
        required = cast(object, error.validator_value)
        if isinstance(required, list):
            required_names = cast(list[object], required)
            missing = next(
                (
                    name
                    for name in required_names
                    if isinstance(name, str) and name not in instance_mapping
                ),
                None,
            )
            if isinstance(missing, str):
                path.append(missing)

    return SchemaViolation(pointer=_pointer(path), detail=detail)


def _safe_detail(error: ValidationError) -> str:
    """Describe a schema rule without interpolating the rejected value."""

    keyword = cast(object, error.validator)
    if not isinstance(keyword, str):
        return "does not satisfy the document schema"
    if keyword == "required":
        return "required property is missing"
    if keyword == "additionalProperties":
        instance = cast(object, error.instance)
        schema = cast(object, error.schema)
        if isinstance(instance, dict) and isinstance(schema, dict):
            instance_mapping = cast(dict[object, object], instance)
            schema_mapping = cast(dict[object, object], schema)
            properties = schema_mapping.get("properties", {})
            allowed: set[str] = (
                {key for key in cast(dict[object, object], properties) if isinstance(key, str)}
                if isinstance(properties, dict)
                else set[str]()
            )
            unexpected = sorted(
                key for key in instance_mapping if isinstance(key, str) and key not in allowed
            )
            if unexpected:
                return f"unexpected property: {unexpected[0]}"
        return "unexpected property"
    if keyword == "enum":
        enum_allowed = cast(object, error.validator_value)
        if isinstance(enum_allowed, list):
            allowed_values = cast(list[object], enum_allowed)
            return "must be one of: " + ", ".join(str(value) for value in allowed_values)
        return "value is not allowed"
    if keyword == "const":
        return f"must equal {cast(object, error.validator_value)}"
    if keyword == "type":
        return f"must have type {cast(object, error.validator_value)}"
    if keyword == "minLength":
        return "must not be empty"
    if keyword == "minItems":
        return f"must contain at least {cast(object, error.validator_value)} item(s)"
    if keyword == "format":
        return f"must match format {cast(object, error.validator_value)}"
    if keyword == "pattern":
        return "must contain a non-whitespace character"
    return f"does not satisfy schema rule {keyword}"
