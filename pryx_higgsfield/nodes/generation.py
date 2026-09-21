"""Catalog-driven image and video generator nodes."""

from __future__ import annotations

import json
from typing import Any, Mapping

from ..catalog import load_bundled_catalog
from ..errors import ValidationError
from ..types import Capability
from .common import execute_generation, image_output, video_output
from .references import Reference, ReferenceCollection, _split_batch


_CATALOG = load_bundled_catalog()
_RATIOS = ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive", "auto"]
_RESOLUTIONS = ["480p", "720p", "1080p", "1k", "2k"]
_OUTPUT_FORMATS = ["mp4", "mov"]


def _models(capability: Capability | tuple[Capability, ...] | None = None) -> list[str]:
    if isinstance(capability, tuple):
        values = {
            model.id
            for item in capability
            for model in _CATALOG.filter(capability=item, status="active")
        }
        return [model.id for model in _CATALOG.models if model.id in values]
    return [model.id for model in _CATALOG.filter(capability=capability, status="active")]


def _common_generation_inputs() -> dict[str, tuple[Any, dict[str, Any]]]:
    return {
        "mode": (["estimate_only", "generate"], {"default": "estimate_only"}),
        "max_usd": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 10000.0, "step": 0.01}),
        "auto_save": ("BOOLEAN", {"default": True}),
        "timeout": ("FLOAT", {"default": 1800.0, "min": 10.0, "max": 7200.0, "step": 1.0}),
    }


def _model_inputs(capability: Capability | None = None) -> tuple[str, dict[str, Any]]:
    choices = _models(capability)
    if not choices:
        raise RuntimeError(f"No catalog models are available for {capability}.")
    return ("STRING", {"default": choices[0], "choices": choices})


def _optional_widgets() -> dict[str, tuple[Any, dict[str, Any]]]:
    return {
        "prompt": ("STRING", {"default": "", "multiline": True}),
        "resolution": ("STRING", {"default": "720p", "choices": _RESOLUTIONS}),
        "aspect_ratio": ("STRING", {"default": "16:9", "choices": _RATIOS}),
        "duration": ("INT", {"default": 5, "min": 2, "max": 30}),
        "generate_audio": ("BOOLEAN", {"default": True}),
        "output_format": ("STRING", {"default": "mp4", "choices": _OUTPUT_FORMATS}),
        "style_id": ("STRING", {"default": ""}),
        "quality": ("STRING", {"default": "medium", "choices": ["low", "medium", "high"]}),
        "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
        "enhance_prompt": ("BOOLEAN", {"default": True}),
        "enable_thinking": ("BOOLEAN", {"default": False}),
        "batch_size": ("INT", {"default": 1, "min": 1, "max": 4}),
        "multi_shots": ("BOOLEAN", {"default": False}),
        "shots_json": ("STRING", {"default": "[]", "multiline": True}),
        "cfg_scale": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
    }


def _arguments_for_model(model_id: str, values: Mapping[str, Any]) -> dict[str, Any]:
    model = _CATALOG.get(model_id)
    parameters = model.parameter_map
    result: dict[str, Any] = {}
    for name, value in values.items():
        if name not in parameters or value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        result[name] = value
    if "shots_json" in values and "shots" in parameters:
        raw = values.get("shots_json") or "[]"
        try:
            shots = json.loads(raw)
        except (TypeError, ValueError) as error:
            raise ValidationError("shots_json must contain a JSON array.") from error
        if not isinstance(shots, list):
            raise ValidationError("shots_json must contain a JSON array.")
        result["shots"] = shots
    return result


def _with_reference_inputs(
    references: ReferenceCollection | None,
    *,
    image: Any = None,
    video: Any = None,
    audio: Any = None,
) -> ReferenceCollection:
    result = ReferenceCollection(references or ())
    if image is not None:
        result.extend(Reference("image", item) for item in _split_batch(image))
    if video is not None:
        result.append(Reference("video", video))
    if audio is not None:
        result.append(Reference("audio", audio))
    return result


def _image_result(outcome):
    return (
        image_output(outcome),
        json.dumps(outcome.urls, ensure_ascii=False),
        outcome.request_id,
        float(outcome.estimate.credits or 0.0),
        float(outcome.estimate.usd or 0.0),
        outcome.status_json(),
    )


def _video_result(outcome):
    local_file = str(outcome.artifacts[0].path) if outcome.artifacts else ""
    return (
        video_output(outcome),
        local_file,
        json.dumps(outcome.urls, ensure_ascii=False),
        outcome.request_id,
        float(outcome.estimate.credits or 0.0),
        float(outcome.estimate.usd or 0.0),
        outcome.status_json(),
    )


class ImageGenerateEditNode:
    CATEGORY = "PRYX/Higgsfield"
    FUNCTION = "generate"
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("images", "image_urls", "request_id", "credits", "usd", "status")

    @classmethod
    def INPUT_TYPES(cls):
        optional = _optional_widgets()
        optional.update(_common_generation_inputs())
        optional.update({
            "references": (ReferenceCollection.TYPE,),
            "image": ("IMAGE",),
        })
        return {"required": {"model": ("STRING", {"default": _models((Capability.IMAGE_GENERATE, Capability.IMAGE_EDIT))[0], "choices": _models((Capability.IMAGE_GENERATE, Capability.IMAGE_EDIT))}), "prompt": ("STRING", {"multiline": True})}, "optional": optional}

    def generate(self, model, prompt, **kwargs):
        values = dict(kwargs)
        values["prompt"] = prompt
        references = _with_reference_inputs(values.pop("references", None), image=values.pop("image", None))
        options = _arguments_for_model(model, values)
        outcome = execute_generation(
            model,
            options,
            mode=values.pop("mode", "estimate_only"),
            max_usd=float(values.pop("max_usd", 0.0)),
            auto_save=bool(values.pop("auto_save", True)),
            timeout=float(values.pop("timeout", 1800.0)),
            references=references,
        )
        return _image_result(outcome)


class TextToVideoNode:
    CATEGORY = "PRYX/Higgsfield"
    FUNCTION = "generate"
    RETURN_TYPES = ("VIDEO", "STRING", "STRING", "STRING", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("video", "local_file", "remote_url", "request_id", "credits", "usd", "status")

    @classmethod
    def INPUT_TYPES(cls):
        optional = _optional_widgets()
        optional.update(_common_generation_inputs())
        return {"required": {"model": _model_inputs(Capability.TEXT_TO_VIDEO)[0], "prompt": ("STRING", {"multiline": True})}, "optional": optional}

    def generate(self, model, prompt, **kwargs):
        values = dict(kwargs)
        values["prompt"] = prompt
        options = _arguments_for_model(model, values)
        outcome = execute_generation(
            model,
            options,
            mode=values.get("mode", "estimate_only"),
            max_usd=float(values.get("max_usd", 0.0)),
            auto_save=bool(values.get("auto_save", True)),
            timeout=float(values.get("timeout", 1800.0)),
        )
        return _video_result(outcome)


class ImageToVideoNode:
    CATEGORY = "PRYX/Higgsfield"
    FUNCTION = "generate"
    RETURN_TYPES = ("VIDEO", "STRING", "STRING", "STRING", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("video", "local_file", "remote_url", "request_id", "credits", "usd", "status")

    @classmethod
    def INPUT_TYPES(cls):
        optional = _optional_widgets()
        optional.update(_common_generation_inputs())
        optional.update({"image": ("IMAGE",), "references": (ReferenceCollection.TYPE,)})
        return {"required": {"model": _model_inputs(Capability.IMAGE_TO_VIDEO)[0], "prompt": ("STRING", {"default": "", "multiline": True})}, "optional": optional}

    def generate(self, model, prompt="", **kwargs):
        values = dict(kwargs)
        values["prompt"] = prompt
        references = _with_reference_inputs(values.pop("references", None), image=values.pop("image", None))
        options = _arguments_for_model(model, values)
        outcome = execute_generation(
            model,
            options,
            mode=values.get("mode", "estimate_only"),
            max_usd=float(values.get("max_usd", 0.0)),
            auto_save=bool(values.get("auto_save", True)),
            timeout=float(values.get("timeout", 1800.0)),
            references=references,
        )
        return _video_result(outcome)


class ReferenceToVideoNode:
    CATEGORY = "PRYX/Higgsfield"
    FUNCTION = "generate"
    RETURN_TYPES = ("VIDEO", "STRING", "STRING", "STRING", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("video", "local_file", "remote_url", "request_id", "credits", "usd", "status")

    @classmethod
    def INPUT_TYPES(cls):
        optional = _optional_widgets()
        optional.update(_common_generation_inputs())
        optional.update({
            "references": (ReferenceCollection.TYPE,),
            "image": ("IMAGE",),
            "video": ("VIDEO",),
            "audio": ("AUDIO",),
        })
        return {"required": {"model": _model_inputs(Capability.REFERENCE_TO_VIDEO)[0], "prompt": ("STRING", {"default": "", "multiline": True})}, "optional": optional}

    def generate(self, model, prompt="", **kwargs):
        values = dict(kwargs)
        values["prompt"] = prompt
        references = _with_reference_inputs(
            values.pop("references", None),
            image=values.pop("image", None),
            video=values.pop("video", None),
            audio=values.pop("audio", None),
        )
        options = _arguments_for_model(model, values)
        outcome = execute_generation(
            model,
            options,
            mode=values.get("mode", "estimate_only"),
            max_usd=float(values.get("max_usd", 0.0)),
            auto_save=bool(values.get("auto_save", True)),
            timeout=float(values.get("timeout", 1800.0)),
            references=references,
        )
        return _video_result(outcome)


class VideoEditNode:
    CATEGORY = "PRYX/Higgsfield"
    FUNCTION = "generate"
    RETURN_TYPES = ("VIDEO", "STRING", "STRING", "STRING", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("video", "local_file", "remote_url", "request_id", "credits", "usd", "status")

    @classmethod
    def INPUT_TYPES(cls):
        optional = _optional_widgets()
        optional.update(_common_generation_inputs())
        optional.update({"video": ("VIDEO",), "references": (ReferenceCollection.TYPE,)})
        return {"required": {"model": _model_inputs(Capability.VIDEO_EDIT)[0], "prompt": ("STRING", {"multiline": True})}, "optional": optional}

    def generate(self, model, prompt, **kwargs):
        values = dict(kwargs)
        values["prompt"] = prompt
        references = _with_reference_inputs(values.pop("references", None), video=values.pop("video", None))
        options = _arguments_for_model(model, values)
        outcome = execute_generation(
            model,
            options,
            mode=values.get("mode", "estimate_only"),
            max_usd=float(values.get("max_usd", 0.0)),
            auto_save=bool(values.get("auto_save", True)),
            timeout=float(values.get("timeout", 1800.0)),
            references=references,
        )
        return _video_result(outcome)


class VideoExtendNode:
    CATEGORY = "PRYX/Higgsfield"
    FUNCTION = "generate"
    RETURN_TYPES = ("VIDEO", "STRING", "STRING", "STRING", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("video", "local_file", "remote_url", "request_id", "credits", "usd", "status")

    @classmethod
    def INPUT_TYPES(cls):
        optional = _optional_widgets()
        optional.update(_common_generation_inputs())
        optional.update({"video": ("VIDEO",), "references": (ReferenceCollection.TYPE,)})
        return {"required": {"model": _model_inputs(Capability.VIDEO_EXTEND)[0], "prompt": ("STRING", {"multiline": True})}, "optional": optional}

    def generate(self, model, prompt, **kwargs):
        values = dict(kwargs)
        values["prompt"] = prompt
        references = _with_reference_inputs(values.pop("references", None), video=values.pop("video", None))
        options = _arguments_for_model(model, values)
        outcome = execute_generation(
            model,
            options,
            mode=values.get("mode", "estimate_only"),
            max_usd=float(values.get("max_usd", 0.0)),
            auto_save=bool(values.get("auto_save", True)),
            timeout=float(values.get("timeout", 1800.0)),
            references=references,
        )
        return _video_result(outcome)


class AdvancedRequestNode:
    CATEGORY = "PRYX/Higgsfield"
    FUNCTION = "generate"
    RETURN_TYPES = ("IMAGE", "VIDEO", "STRING", "STRING", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("image", "video", "remote_urls", "request_id", "credits", "usd", "status")

    @classmethod
    def INPUT_TYPES(cls):
        all_models = _models()
        optional = _common_generation_inputs()
        return {
            "required": {
                "model": ("STRING", {"default": all_models[0], "choices": all_models}),
                "arguments_json": ("STRING", {"default": "{}", "multiline": True}),
            },
            "optional": optional,
        }

    def generate(self, model, arguments_json, **kwargs):
        try:
            arguments = json.loads(arguments_json)
        except (TypeError, ValueError) as error:
            raise ValidationError("arguments_json must contain a JSON object.") from error
        if not isinstance(arguments, dict):
            raise ValidationError("arguments_json must contain a JSON object.")
        outcome = execute_generation(
            model,
            arguments,
            mode=kwargs.get("mode", "estimate_only"),
            max_usd=float(kwargs.get("max_usd", 0.0)),
            auto_save=bool(kwargs.get("auto_save", True)),
            timeout=float(kwargs.get("timeout", 1800.0)),
            allow_unknown=True,
        )
        image = image_output(outcome) if outcome.model.output.value == "image" else None
        video = video_output(outcome) if outcome.model.output.value == "video" else None
        return (
            image,
            video,
            json.dumps(outcome.urls, ensure_ascii=False),
            outcome.request_id,
            float(outcome.estimate.credits or 0.0),
            float(outcome.estimate.usd or 0.0),
            outcome.status_json(),
        )
