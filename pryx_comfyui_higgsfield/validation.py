"""Explicit validation for catalog-driven request payloads."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any, Iterable
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

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
        if value is not None and not (value == "" and name in known and not known[name].required):
            normalized[str(name)] = value
    for name, spec in known.items():
        if name not in normalized and spec.default is not None and (spec.default != "" or spec.required):
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
    _validate_combinations(model, arguments)
    if model.input_schema is not None:
        try:
            validator = Draft202012Validator(model.input_schema)
            error = next(validator.iter_errors(dict(arguments)), None)
        except SchemaError as error:
            raise ValidationError(f"Invalid catalog schema for {model.display_name}.") from error
        if error is not None:
            location = ".".join(map(str, error.absolute_path)) or "request"
            raise ValidationError(f"{location}: {error.message}")


def _validate_combinations(model: ModelSpec, arguments: Mapping[str, Any]) -> None:
    if model.capability.value == "reference_to_video" and model.input_schema is None:
        fields = [p.name for p in model.parameters if p.media_types]
        if model.id == "seedance-2-reference-to-video":
            fields = ["image_urls", "video_urls"]
        if not any(arguments.get(name) for name in fields):
            raise ValidationError("Provide at least one supported reference input (" + ", ".join(fields) + ").")
    if arguments.get("file_url") and arguments.get("link_url"):
        raise ValidationError("file_url and link_url are mutually exclusive.")
    if model.id == "marketing-studio-image" and arguments.get("enhance_prompt"):
        if not arguments.get("preset_id") or not 1 <= len(arguments.get("image_urls", [])) <= 2:
            raise ValidationError("Enhanced Marketing Studio requires preset_id and 1–2 images (product, optional model).")
    if model.id.startswith("kling-"):
        if arguments.get("multi_shots") and not arguments.get("multi_prompt"):
            raise ValidationError("multi_shots requires multi_prompt shot definitions.")
        if model.input_schema is None:
            for shot in arguments.get("multi_prompt", []):
                if not isinstance(shot, Mapping) or not isinstance(shot.get("prompt"), str) or not 1 <= len(shot["prompt"]) <= 512:
                    raise ValidationError("Each multi_prompt shot requires a prompt of 1–512 characters.")
                duration = shot.get("duration")
                if type(duration) is not int or not 1 <= duration <= 15:
                    raise ValidationError("Each multi_prompt shot requires an integer duration of 1–15 seconds.")
            if any(not isinstance(item, str) for item in arguments.get("elements", [])):
                raise ValidationError("elements must contain Kling element ID strings.")
    if model.id == "recraft-v4-1-pro" and model.input_schema is None:
        colors = list(arguments.get("colors", []))
        if "background_color" in arguments:
            colors.append(arguments["background_color"])
        for color in colors:
            rgb = color.get("rgb") if isinstance(color, Mapping) else None
            if not isinstance(rgb, list) or len(rgb) != 3 or any(type(v) is not int or not 0 <= v <= 255 for v in rgb):
                raise ValidationError("Each color must contain rgb: three integers from 0 to 255.")


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
    if not math.isfinite(value):
        raise ValidationError(f"{spec.name} must be finite.")
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

    allowed_kinds = set(model.input_media)
    unsupported = [item.get("kind") for item in items if item.get("kind") not in allowed_kinds]
    if unsupported:
        raise ValidationError(
            f"{model.display_name} does not support reference type(s): {', '.join(map(str, sorted(set(unsupported))))}"
        )
    result: dict[str, Any] = {}
    params = model.parameter_map
    # Explicit frame/source sockets take priority over the ordered collector.
    remaining = []
    for item in items:
        field = item.get("field")
        if not field:
            remaining.append(item)
            continue
        spec = params.get(field)
        if not spec or item["kind"] not in spec.media_types or (spec.type != "array" and field in result):
            raise ValidationError(f"Unsupported or duplicate reference input: {field}")
        if spec.type == "array":
            result.setdefault(field, []).append(item["url"])
        else:
            result[field] = item["url"]
    singular_fields = {
        "image": ("image_url", "first_frame_url", "end_image_url", "last_image_url", "last_frame_url"),
        "video": ("video_url",), "audio": ("audio_url",),
        "file": ("file_url",), "url": ("link_url",),
    }
    for item in remaining:
        kind, url = item["kind"], item["url"]
        plural = f"{kind}_urls"
        field = next((name for name in singular_fields[kind] if name in params and name not in result and params[name].required), None)
        if field:
            result[field] = url
        elif plural in params:
            result.setdefault(plural, []).append(url)
        else:
            field = next((name for name in singular_fields[kind] if name in params and name not in result), None)
            if field:
                result[field] = url
            else:
                raise ValidationError(f"Too many {kind} references for {model.display_name}; no input may be silently discarded.")
    for name, value in result.items():
        _validate_value(params[name], value)
    return result
