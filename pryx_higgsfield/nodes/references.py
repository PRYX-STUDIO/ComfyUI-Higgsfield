"""Ordered reference collection for multimodal Higgsfield nodes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from ..errors import ValidationError


@dataclass
class Reference:
    kind: str
    value: Any = None
    url: str | None = None
    label: str = ""

    def as_dict(self) -> dict[str, Any]:
        result = {"kind": self.kind}
        if self.url:
            result["url"] = self.url
        if self.label:
            result["label"] = self.label
        return result


class ReferenceCollection(list):
    """A list-like ComfyUI value that preserves user-specified order."""

    TYPE = "PRYX_HF_REFERENCES"

    def __init__(self, values: Iterable[Reference | Mapping[str, Any]] = ()) -> None:
        super().__init__(_coerce_reference(value) for value in values)

    def serializable(self) -> list[dict[str, Any]]:
        return [item.as_dict() for item in self]


def _coerce_reference(value: Reference | Mapping[str, Any]) -> Reference:
    if isinstance(value, Reference):
        return value
    if isinstance(value, Mapping):
        return Reference(
            kind=str(value.get("kind", "")),
            value=value.get("value"),
            url=value.get("url"),
            label=str(value.get("label", "")),
        )
    raise ValidationError("Invalid PRYX Higgsfield reference collection.")


def _split_batch(value: Any) -> list[Any]:
    if value is None:
        return []
    shape = getattr(value, "shape", None)
    if shape is not None and len(shape) >= 1:
        try:
            return [value[index : index + 1] for index in range(int(shape[0]))]
        except Exception:
            pass
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


class ReferenceCollectorNode:
    CATEGORY = "PRYX/Higgsfield"
    FUNCTION = "collect"
    RETURN_TYPES = (ReferenceCollection.TYPE,)
    RETURN_NAMES = ("references",)
    OUTPUT_NODE = False

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "optional": {
                "references": (ReferenceCollection.TYPE,),
                "image": ("IMAGE",),
                "video": ("VIDEO",),
                "audio": ("AUDIO",),
                "external_url": ("STRING", {"default": "", "multiline": False}),
                "external_type": (["url", "file"], {"default": "url"}),
                "label": ("STRING", {"default": "", "multiline": False}),
            }
        }

    def collect(
        self,
        references: ReferenceCollection | list[Mapping[str, Any]] | None = None,
        image: Any = None,
        video: Any = None,
        audio: Any = None,
        external_url: str = "",
        external_type: str = "url",
        label: str = "",
    ):
        result = ReferenceCollection(references or ())
        if image is not None:
            result.extend(Reference("image", value=item, label=label) for item in _split_batch(image))
        if video is not None:
            result.append(Reference("video", value=video, label=label))
        if audio is not None:
            result.append(Reference("audio", value=audio, label=label))
        if external_url.strip():
            url = external_url.strip()
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not parsed.netloc:
                raise ValidationError("External references must use a public HTTPS URL.")
            if external_type not in {"url", "file"}:
                raise ValidationError("External reference type must be url or file.")
            result.append(Reference(external_type, url=url, label=label))
        return (result,)
