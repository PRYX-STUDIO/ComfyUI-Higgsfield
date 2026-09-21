"""Shared data contracts for the catalog and request lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping


API_BASE_URL = "https://api.higgsfield.ai"
CATALOG_SCHEMA_VERSION = 1


class Capability(str, Enum):
    IMAGE_GENERATE = "image_generate"
    IMAGE_EDIT = "image_edit"
    TEXT_TO_VIDEO = "text_to_video"
    IMAGE_TO_VIDEO = "image_to_video"
    REFERENCE_TO_VIDEO = "reference_to_video"
    VIDEO_EDIT = "video_edit"
    VIDEO_EXTEND = "video_extend"


class OutputType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


class ModelStatus(str, Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    UNAVAILABLE = "unavailable"


class RequestStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NSFW = "nsfw"
    CANCELED = "canceled"

    @property
    def terminal(self) -> bool:
        return self in {
            RequestStatus.COMPLETED,
            RequestStatus.FAILED,
            RequestStatus.NSFW,
            RequestStatus.CANCELED,
        }


class Phase(str, Enum):
    VALIDATE = "validate"
    UPLOAD = "upload"
    ESTIMATE = "estimate"
    QUEUED = "queued"
    GENERATING = "generating"
    DOWNLOAD = "download"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class ParameterSpec:
    """A catalog-described request field.

    The catalog is data only. Validation uses this small, explicit contract
    instead of evaluating expressions from a remote file.
    """

    name: str
    type: str
    required: bool = False
    default: Any = None
    choices: tuple[Any, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    min_items: int | None = None
    max_items: int | None = None
    description: str = ""
    media_types: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ParameterSpec":
        choices = data.get("choices") or data.get("enum") or ()
        if not isinstance(choices, (list, tuple)):
            raise ValueError(f"Parameter choices must be a list: {data.get('name')}")
        media_types = data.get("media_types") or data.get("mediaTypes") or ()
        if not isinstance(media_types, (list, tuple)):
            raise ValueError(f"Parameter media_types must be a list: {data.get('name')}")
        return cls(
            name=str(data["name"]),
            type=str(data["type"]),
            required=bool(data.get("required", False)),
            default=data.get("default"),
            choices=tuple(choices),
            minimum=data.get("minimum", data.get("min")),
            maximum=data.get("maximum", data.get("max")),
            min_items=data.get("min_items", data.get("minItems")),
            max_items=data.get("max_items", data.get("maxItems")),
            description=str(data.get("description", "")),
            media_types=tuple(str(item) for item in media_types),
        )

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "required": self.required,
        }
        if self.default is not None:
            result["default"] = self.default
        if self.choices:
            result["choices"] = list(self.choices)
        if self.minimum is not None:
            result["minimum"] = self.minimum
        if self.maximum is not None:
            result["maximum"] = self.maximum
        if self.min_items is not None:
            result["min_items"] = self.min_items
        if self.max_items is not None:
            result["max_items"] = self.max_items
        if self.description:
            result["description"] = self.description
        if self.media_types:
            result["media_types"] = list(self.media_types)
        return result


@dataclass(frozen=True)
class ModelSpec:
    id: str
    display_name: str
    provider: str
    family: str
    endpoint: str
    capability: Capability
    output: OutputType
    parameters: tuple[ParameterSpec, ...]
    input_media: tuple[str, ...] = ()
    max_references: int | None = None
    result_field: str = ""
    docs_source: str = ""
    docs_checked: str = ""
    status: ModelStatus = ModelStatus.ACTIVE

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ModelSpec":
        parameters = data.get("parameters")
        if not isinstance(parameters, list):
            raise ValueError(f"Model parameters must be a list: {data.get('id')}")
        return cls(
            id=str(data["id"]),
            display_name=str(data["display_name"]),
            provider=str(data["provider"]),
            family=str(data["family"]),
            endpoint=str(data["endpoint"]),
            capability=Capability(str(data["capability"])),
            output=OutputType(str(data["output"])),
            parameters=tuple(ParameterSpec.from_dict(item) for item in parameters),
            input_media=tuple(str(item) for item in data.get("input_media", ())),
            max_references=data.get("max_references"),
            result_field=str(data.get("result_field", "")),
            docs_source=str(data.get("docs_source", "")),
            docs_checked=str(data.get("docs_checked", "")),
            status=ModelStatus(str(data.get("status", ModelStatus.ACTIVE.value))),
        )

    @property
    def url(self) -> str:
        return f"{API_BASE_URL}/{self.endpoint.lstrip('/')}"

    @property
    def parameter_map(self) -> dict[str, ParameterSpec]:
        return {item.name: item for item in self.parameters}

    def supports(self, capability: Capability | str) -> bool:
        value = capability.value if isinstance(capability, Capability) else str(capability)
        return self.capability.value == value

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "provider": self.provider,
            "family": self.family,
            "endpoint": self.endpoint,
            "capability": self.capability.value,
            "output": self.output.value,
            "parameters": [item.as_dict() for item in self.parameters],
            "input_media": list(self.input_media),
            "max_references": self.max_references,
            "result_field": self.result_field,
            "docs_source": self.docs_source,
            "docs_checked": self.docs_checked,
            "status": self.status.value,
        }


@dataclass(frozen=True)
class Estimate:
    credits: float | None
    usd: float | None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "Estimate":
        def number(value: Any) -> float | None:
            if value is None or value == "":
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        return cls(
            credits=number(payload.get("credits")),
            usd=number(payload.get("usd")),
            raw=dict(payload),
        )


@dataclass(frozen=True)
class AcceptedRequest:
    request_id: str
    status_url: str
    cancel_url: str
    status: RequestStatus
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "AcceptedRequest":
        try:
            status = RequestStatus(str(payload.get("status", RequestStatus.QUEUED.value)))
        except ValueError:
            status = RequestStatus.QUEUED
        return cls(
            request_id=str(payload["request_id"]),
            status_url=str(payload["status_url"]),
            cancel_url=str(payload["cancel_url"]),
            status=status,
            raw=dict(payload),
        )


@dataclass(frozen=True)
class StatusSnapshot:
    status: RequestStatus
    request_id: str | None = None
    status_url: str | None = None
    cancel_url: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "StatusSnapshot":
        try:
            status = RequestStatus(str(payload["status"]))
        except (KeyError, ValueError) as error:
            raise ValueError(f"Unknown Higgsfield request status: {payload.get('status')}") from error
        return cls(
            status=status,
            request_id=payload.get("request_id"),
            status_url=payload.get("status_url"),
            cancel_url=payload.get("cancel_url"),
            payload=dict(payload),
        )


@dataclass(frozen=True)
class ProgressEvent:
    node_id: str | None
    phase: Phase
    request_id: str | None
    elapsed_seconds: float
    estimate: Estimate | None = None
    status: RequestStatus | None = None
    message: str = ""

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "node_id": self.node_id,
            "phase": self.phase.value,
            "request_id": self.request_id,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "message": self.message,
        }
        if self.status is not None:
            result["status"] = self.status.value
        if self.estimate is not None:
            result["credits"] = self.estimate.credits
            result["usd"] = self.estimate.usd
        return result


def model_infos(models: Iterable[ModelSpec]) -> list[dict[str, Any]]:
    return [item.as_dict() for item in models]
