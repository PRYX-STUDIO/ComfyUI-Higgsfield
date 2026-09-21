"""Explicit validation for catalog-driven request payloads."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Iterable
from urllib.parse import urlsplit

from .errors import ValidationError
from .types import ModelSpec, ParameterSpec


_FORBIDDEN_ADVANCED_KEYS = {"base_url", "endpoint", "api_url", "host", "url_override"}


def normalize_arguments(
    model: ModelSpec,
    arguments: Mapping[str, Any],
    *,
    allow_unknown: bool = False,
) -> dict[str, Any]:
    if not isinstance(arguments, Mapping):
        raise ValidationError("Request arguments must be a JSON object.")
    known = model.parameter_map
    unknown = set(arguments) - set(known)
    if unknown and not allow_unknown:
        raise ValidationError(
            f"Unknown parameter(s) for {model.display_name}: {', '.join(sorted(map(str, unknown)))}"
        )
    if allow_unknown:
        _validate_json_object(arguments)
        forbidden = _FORBIDDEN_ADVANCED_KEYS.intersection(str(key) for key in arguments)
        if forbidden:
            raise ValidationError(
                f"Advanced Request cannot override the API endpoint: {', '.join(sorted(forbidden))}"
            )

    normalized: dict[str, Any] = {}
    for name, value in arguments.items():
        if value is not None:
            normalized[str(name)] = value
    for name, spec in known.items():
        if name not in normalized and spec.default is not None:
            normalized[name] = spec.default
    validate_arguments(model, normalized, allow_unknown=allow_unknown)
    return normalized


def validate_arguments(
    model: ModelSpec,
    arguments: Mapping[str, Any],
    *,
    allow_unknown: bool = False,
) -> None:
    if not isinstance(arguments, Mapping):
        raise ValidationError("Request arguments must be a JSON object.")
    known = model.parameter_map
    unknown = set(arguments) - set(known)
    if unknown and not allow_unknown:
        raise ValidationError(
            f"Unknown parameter(s) for {model.display_name}: {', '.join(sorted(map(str, unknown)))}"
        )
    for name, spec in known.items():
        if spec.required and (name not in arguments or arguments[name] in (None, "")):
            raise ValidationError(f"Missing required parameter: {name}")
        if name not in arguments or arguments[name] is None:
            continue
        _validate_value(spec, arguments[name])


def _validate_value(spec: ParameterSpec, value: Any) -> None:
    type_name = spec.type.lower()
    if type_name in {"string", "url"}:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{spec.name} must be a non-empty string.")
        if type_name == "url" or spec.name.endswith("_url") or spec.name.endswith("_urls"):
            if isinstance(value, str):
                _validate_public_url(value, spec.name)
    elif type_name in {"integer", "int"}:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValidationError(f"{spec.name} must be an integer.")
        _validate_number_limits(spec, value)
    elif type_name in {"number", "float"}:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValidationError(f"{spec.name} must be a number.")
        _validate_number_limits(spec, value)
    elif type_name in {"boolean", "bool"}:
        if not isinstance(value, bool):
            raise ValidationError(f"{spec.name} must be a boolean.")
    elif type_name in {"array", "list"}:
        if not isinstance(value, list):
            raise ValidationError(f"{spec.name} must be an array.")
        if spec.min_items is not None and len(value) < spec.min_items:
            raise ValidationError(f"{spec.name} requires at least {spec.min_items} item(s).")
        if spec.max_items is not None and len(value) > spec.max_items:
            raise ValidationError(f"{spec.name} accepts at most {spec.max_items} item(s).")
        if spec.name.endswith("_urls"):
            for item in value:
                _validate_public_url(item, spec.name)
    elif type_name in {"object", "json"}:
        if not isinstance(value, Mapping):
            raise ValidationError(f"{spec.name} must be a JSON object.")
        _validate_json_object(value)
    else:
        raise ValidationError(f"Unsupported catalog parameter type: {spec.type}")

    if spec.choices and value not in spec.choices:
        raise ValidationError(f"{spec.name} must be one of: {', '.join(map(str, spec.choices))}.")


def _validate_number_limits(spec: ParameterSpec, value: int | float) -> None:
    if spec.minimum is not None and value < spec.minimum:
        raise ValidationError(f"{spec.name} must be at least {spec.minimum}.")
    if spec.maximum is not None and value > spec.maximum:
        raise ValidationError(f"{spec.name} must be at most {spec.maximum}.")


def _validate_public_url(value: Any, field_name: str) -> None:
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must contain URL strings.")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValidationError(f"{field_name} only accepts public HTTPS URLs.")


def _validate_json_object(value: Any) -> None:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValidationError("Advanced arguments must be JSON-serializable.") from error


def references_to_arguments(
    model: ModelSpec,
    references: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Map an ordered local reference collection to the model's URL fields."""

    items = list(references)
    if model.max_references is not None and len(items) > model.max_references:
        raise ValidationError(
            f"{model.display_name} accepts at most {model.max_references} reference(s)."
        )
    by_kind: dict[str, list[str]] = {"image": [], "video": [], "audio": [], "file": [], "url": []}
    for item in items:
        kind = str(item.get("kind", ""))
        url = item.get("url")
        if kind not in by_kind or not url:
            raise ValidationError("Every reference must contain a supported kind and URL.")
        _validate_public_url(url, "reference URL")
        by_kind[kind].append(str(url))

    result: dict[str, Any] = {}
    params = model.parameter_map
    if "image_url" in params and by_kind["image"]:
        result["image_url"] = by_kind["image"][0]
        image_values = by_kind["image"][1:]
    else:
        image_values = by_kind["image"]
    if "video_url" in params and by_kind["video"]:
        result["video_url"] = by_kind["video"][0]
        video_values = by_kind["video"][1:]
    else:
        video_values = by_kind["video"]
    if "audio_url" in params and by_kind["audio"]:
        result["audio_url"] = by_kind["audio"][0]
        audio_values = by_kind["audio"][1:]
    else:
        audio_values = by_kind["audio"]
    for kind in ("image", "video", "audio"):
        field = f"{kind}_urls"
        values = {
            "image": image_values,
            "video": video_values,
            "audio": audio_values,
        }[kind]
        if field in params and values:
            result[field] = values
    if "file_url" in params and by_kind["file"]:
        result["file_url"] = by_kind["file"][0]
    if "link_url" in params and by_kind["url"]:
        result["link_url"] = by_kind["url"][0]

    allowed_kinds = set(model.input_media)
    unsupported = [item.get("kind") for item in items if item.get("kind") not in allowed_kinds]
    if unsupported:
        raise ValidationError(
            f"{model.display_name} does not support reference type(s): {', '.join(map(str, sorted(set(unsupported))))}"
        )
    return result
