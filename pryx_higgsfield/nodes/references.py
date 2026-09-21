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
    field: str = ""
    source: str = ""

    def as_dict(self) -> dict[str, Any]:
        result = {"kind": self.kind}
        if self.url:
            result["url"] = self.url
        if self.label:
            result["label"] = self.label
        if self.field:
            result["field"] = self.field
        if self.source:
            result["source"] = self.source
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
            field=str(value.get("field", "")),
            source=str(value.get("source", "")),
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


COLLECTOR_SLOTS = {"image": 30, "video": 10, "audio": 10}


def _collector_names(text: str) -> dict[str, str]:
    result = {}
    allowed = {f"{kind}_{index}" for kind, count in COLLECTOR_SLOTS.items() for index in range(1, count + 1)}
    for line in text.splitlines():
        if not line.strip():
            continue
        key, separator, label = line.partition("=")
        key, label = key.strip(), label.strip()
        if key in COLLECTOR_SLOTS:
            key += "_1"
        if not separator or key not in allowed or not label or any(char in label for char in "{}"):
            raise ValidationError("Use one name per line, e.g. image_1=person or video_1=camera. Braces are not allowed in names.")
        if key in result:
            raise ValidationError(f"Duplicate name assignment for {key}.")
        result[key] = label
    return result


class ReferenceCollectorNode:
    CATEGORY = "PRYX/Higgsfield"
    FUNCTION = "collect"
    RETURN_TYPES = (ReferenceCollection.TYPE,)
    RETURN_NAMES = ("references",)
    OUTPUT_NODE = False

    @classmethod
    def INPUT_TYPES(cls):
        inputs = {
            "optional": {
                "references": (ReferenceCollection.TYPE,),
                "image": ("IMAGE",),
                "video": ("VIDEO",),
                "audio": ("AUDIO",),
                "external_url": ("STRING", {"default": "", "multiline": False}),
                "external_type": (["url", "file"], {"default": "url"}),
                "label": ("STRING", {"default": "", "multiline": False, "tooltip": "Legacy shared label. Prefer names for separate media labels. Existing workflows retain this label."}),
                "names": ("STRING", {"default": "", "multiline": True, "tooltip": "Optional names, one per line: image_1=person, image_2=outfit, video_1=camera. Otherwise socket names become labels. Batches use name[1], name[2], etc. Reference Preview shows the final mapping."}),
            }
        }
        for kind, count in COLLECTOR_SLOTS.items():
            for index in range(2, count + 1):
                inputs["optional"][f"{kind}_{index}"] = (kind.upper(), {"tooltip": f"{kind.title()} slot {index}. Slots are collected in numeric order, not connection order. Model limits still apply."})
        return inputs

    def collect(
        self,
        references: ReferenceCollection | list[Mapping[str, Any]] | None = None,
        image: Any = None,
        video: Any = None,
        audio: Any = None,
        external_url: str = "",
        external_type: str = "url",
        label: str = "",
        names: str = "",
        **media: Any,
    ):
        label = label.strip()
        if any(char in label for char in "{}"):
            raise ValidationError("Reference labels must not contain braces.")
        result = ReferenceCollection(references or ())
        assigned = _collector_names(names)
        allowed_sockets = {f"{kind}_{index}" for kind, count in COLLECTOR_SLOTS.items() for index in range(2, count + 1)}
        unknown = [name for name, value in media.items() if name not in allowed_sockets and value is not None]
        if unknown:
            raise ValidationError("Unsupported Collector socket(s): " + ", ".join(unknown))
        first = {"image": image, "video": video, "audio": audio}
        for kind, count in COLLECTOR_SLOTS.items():
            for index in range(1, count + 1):
                value = first[kind] if index == 1 else media.get(f"{kind}_{index}")
                if value is None:
                    continue
                slot = f"{kind}_{index}"
                name = assigned.get(slot, label or slot)
                items = _split_batch(value) if kind == "image" else [value]
                for batch_index, item in enumerate(items, 1):
                    # Keep legacy shared labels unchanged for saved workflows.
                    item_name = f"{name}[{batch_index}]" if len(items) > 1 and (slot in assigned or not label) else name
                    result.append(Reference(kind, value=item, label=item_name, source=f"Collector {slot}"))
        if external_url.strip():
            url = external_url.strip()
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not parsed.netloc:
                raise ValidationError("External references must use a public HTTPS URL.")
            if external_type not in {"url", "file"}:
                raise ValidationError("External reference type must be url or file.")
            result.append(Reference(external_type, url=url, label=label))
        return (result,)
