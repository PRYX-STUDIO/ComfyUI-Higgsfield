"""Catalog-driven image and video generator nodes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ..catalog import runtime_catalog
from ..errors import ValidationError
from ..reference_prompt import reference_prompt
from ..types import Capability, ParameterSpec
from .common import execute_generation, image_output, video_output
from .references import Reference, ReferenceCollection, _split_batch


_CATALOG = runtime_catalog()

# URL fields are populated from native ComfyUI media inputs and the ordered
# reference collection. They must never appear as editable text widgets.
_MEDIA_PARAMETER_NAMES = {
    "image_url",
    "end_image_url",
    "last_image_url",
    "image_urls",
    "video_url",
    "video_urls",
    "audio_url",
    "audio_urls",
    "file_url",
    "link_url",
}

_PARAMETER_HINTS = {
    "aspect_ratio": "Output framing. Use the exact format shown in the choices.",
    "batch_size": "Number of images to generate in one request.",
    "cfg_scale": "How strongly the model follows the prompt. The catalog defines the valid range.",
    "duration": "Video duration in seconds. The selected model defines the valid range.",
    "enable_thinking": "Allow the model's reasoning mode when the selected model supports it.",
    "enhance_prompt": "Ask the provider to improve the prompt before generation.",
    "generate_audio": "Generate or include audio when the selected video model supports it.",
    "multi_shots": "Generate multiple shots when supported by the selected model.",
    "output_format": "Output container format supported by the selected model.",
    "preset_id": "Optional provider preset identifier.",
    "quality": "Image quality tier supported by the selected model.",
    "resolution": "Output resolution supported by the selected model.",
    "seed": "Optional deterministic seed. The provider may ignore it.",
    "shots": "JSON array of shot descriptions. The selected model defines the maximum count.",
    "style": "Optional provider style value.",
    "style_id": "Optional SOUL style identifier from the Higgsfield style catalog.",
}


def _models(capability: Capability | tuple[Capability, ...] | None = None) -> list[str]:
    if isinstance(capability, tuple):
        allowed = {item.value for item in capability}
        return [
            model.id
            for model in _CATALOG.models
            if model.status.value == "active" and model.capability.value in allowed
        ]
    return [model.id for model in _CATALOG.filter(capability=capability, status="active")]


def _common_generation_inputs() -> dict[str, tuple[Any, dict[str, Any]]]:
    return {
        "mode": (
            ["estimate_only", "generate"],
            {
                "default": "estimate_only",
                "tooltip": "Estimate cost without generating, or submit the paid generation request.",
            },
        ),
        "max_usd": (
            "FLOAT",
            {
                "default": 0.0,
                "min": 0.0,
                "max": 10000.0,
                "step": 0.01,
                "tooltip": "Hard USD limit. Zero disables the limit; no generation is submitted above this value.",
            },
        ),
        "auto_save": (
            "BOOLEAN",
            {
                "default": True,
                "tooltip": "Save completed media in ComfyUI output; disable to keep it in the temporary directory.",
            },
        ),
        "timeout": (
            "FLOAT",
            {
                "default": 1800.0,
                "min": 10.0,
                "max": 7200.0,
                "step": 1.0,
                "tooltip": "Maximum local wait time in seconds. A timed-out remote generation is never submitted again.",
            },
        ),
    }


def _model_inputs(capability: Capability | tuple[Capability, ...] | None = None) -> tuple[str, dict[str, Any]]:
    choices = _models(capability)
    if not choices:
        raise RuntimeError(f"No catalog models are available for {capability}.")
    return (
        "STRING",
        {
            "default": choices[0],
            "choices": choices,
            "options": choices,
            "widgetType": "COMBO",
            # Current ComfyUI frontends keep the dropdown and expose the
            # required STRING socket side by side; defaultInput is deprecated.
            "tooltip": "Catalog model ID. Connect PRYX Higgsfield Model Catalog or choose a model from the dropdown.",
        },
    )


def _parameter_hint(spec: ParameterSpec) -> str:
    hint = spec.description or _PARAMETER_HINTS.get(spec.name, "Catalog-defined model parameter.")
    details: list[str] = []
    if spec.choices:
        details.append("Choices: " + ", ".join(map(str, spec.choices)))
    if spec.minimum is not None or spec.maximum is not None:
        lower = str(spec.minimum) if spec.minimum is not None else "-∞"
        upper = str(spec.maximum) if spec.maximum is not None else "∞"
        details.append(f"Range: {lower}–{upper}")
    if spec.min_items is not None or spec.max_items is not None:
        lower = str(spec.min_items) if spec.min_items is not None else "0"
        upper = str(spec.max_items) if spec.max_items is not None else "∞"
        details.append(f"Items: {lower}–{upper}")
    return hint if not details else hint + " " + " ".join(details) + "."


def _widget_name(spec: ParameterSpec) -> str:
    return "shots_json" if spec.name == "shots" else spec.name


def _parameter_input(spec: ParameterSpec) -> tuple[str, dict[str, Any]]:
    options: dict[str, Any] = {"tooltip": _parameter_hint(spec)}
    if spec.choices:
        options["choices"] = list(spec.choices)
        options["options"] = list(spec.choices)
        options["widgetType"] = "COMBO"
    if spec.default is not None:
        options["default"] = spec.default
    elif spec.choices:
        options["default"] = spec.choices[0]
    if spec.choices:
        return list(spec.choices), options

    type_name = spec.type.lower()
    if type_name in {"integer", "int"}:
        options.setdefault("default", spec.minimum if spec.minimum is not None else 0)
        if spec.minimum is not None:
            options["min"] = spec.minimum
        if spec.maximum is not None:
            options["max"] = spec.maximum
        options.setdefault("step", 1)
        if spec.name == "seed":
            options.update(default=-1, min=-1, control_after_generate=False)
            options["tooltip"] += " Use -1 to omit the seed and let the provider choose randomly."
        return "INT", options
    if type_name in {"number", "float"}:
        options.setdefault("default", 0.0)
        if spec.minimum is not None:
            options["min"] = spec.minimum
        if spec.maximum is not None:
            options["max"] = spec.maximum
        options.setdefault("step", 0.01)
        return "FLOAT", options
    if type_name in {"boolean", "bool"}:
        options.setdefault("default", False)
        return "BOOLEAN", options
    if type_name in {"array", "list", "object", "json"} or spec.name == "shots":
        options["default"] = json.dumps(spec.default) if spec.default is not None else ""
        options["tooltip"] += " Enter valid JSON; leave blank to omit this optional field."
        options["multiline"] = True
        return "STRING", options
    options.setdefault("default", "")
    return "STRING", options


def _catalog_parameter_inputs(capability: Capability | tuple[Capability, ...]) -> dict[str, tuple[Any, dict[str, Any]]]:
    """Return the union of editable, non-media fields for one node capability."""

    specs: dict[str, ParameterSpec] = {}
    for model_id in _models(capability):
        model = _CATALOG.get(model_id)
        for spec in model.parameters:
            if spec.name == "prompt" or spec.name in _MEDIA_PARAMETER_NAMES:
                continue
            existing = specs.get(spec.name)
            if existing is None:
                specs[spec.name] = spec
                continue
            choices = tuple(dict.fromkeys((*existing.choices, *spec.choices)))
            specs[spec.name] = ParameterSpec(
                name=existing.name,
                type=existing.type,
                required=existing.required or spec.required,
                default=existing.default if existing.default is not None else spec.default,
                choices=choices,
                minimum=(
                    min(value for value in (existing.minimum, spec.minimum) if value is not None)
                    if existing.minimum is not None or spec.minimum is not None
                    else None
                ),
                maximum=(
                    max(value for value in (existing.maximum, spec.maximum) if value is not None)
                    if existing.maximum is not None or spec.maximum is not None
                    else None
                ),
                min_items=(
                    min(value for value in (existing.min_items, spec.min_items) if value is not None)
                    if existing.min_items is not None or spec.min_items is not None
                    else None
                ),
                max_items=(
                    max(value for value in (existing.max_items, spec.max_items) if value is not None)
                    if existing.max_items is not None or spec.max_items is not None
                    else None
                ),
                description=existing.description or spec.description,
                media_types=tuple(dict.fromkeys((*existing.media_types, *spec.media_types))),
            )
    return {_widget_name(spec): _parameter_input(spec) for spec in specs.values()}


def _prompt_input() -> tuple[str, dict[str, Any]]:
    return (
        "STRING",
        {
            "forceInput": True,
            "tooltip": "Prompt text. Connect a Config UI Prompt node for long prompts.",
        },
    )


def _generator_inputs(
    capability: Capability,
    *,
    optional: dict[str, tuple[Any, dict[str, Any]]] | None = None,
):
    values = _catalog_parameter_inputs(capability)
    values["prompt"] = _prompt_input()
    values.update(_common_generation_inputs())
    if optional:
        values.update(optional)
    return {
        "required": {"model": _model_inputs(capability)},
        "optional": values,
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
        if name == "seed" and value == -1:
            continue
        if parameters[name].type in {"array", "list", "object", "json"} and isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError as error:
                raise ValidationError(f"{name} must contain valid JSON.") from error
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
    end_image: Any = None,
    model_id: str | None = None,
) -> ReferenceCollection:
    result = ReferenceCollection()
    params = _CATALOG.get(model_id).parameter_map if model_id else {}
    if image is not None:
        frames = _split_batch(image)
        if "image_url" in params and len(frames) != 1:
            raise ValidationError("The start image socket accepts exactly one image; use references for ordered batches.")
        result.extend(Reference("image", item, label=f"Direct image {index}", field="image_url" if "image_url" in params else "") for index, item in enumerate(frames, 1))
    if end_image is not None:
        field = next((name for name in ("end_image_url", "last_image_url") if name in params), None)
        frames = _split_batch(end_image)
        if not field or len(frames) != 1:
            raise ValidationError("The selected model must support an end frame, supplied as exactly one image.")
        result.append(Reference("image", frames[0], label="Direct end image", field=field))
    if video is not None:
        result.append(Reference("video", video, label="Direct video", field="video_url" if "video_url" in params else ""))
    if audio is not None:
        result.append(Reference("audio", audio, label="Direct audio"))
    result.extend(ReferenceCollection(references or ()))
    return result


class CatalogGeneratorNode:
    CAPABILITIES: tuple[Capability, ...] = ()

    @classmethod
    def VALIDATE_INPUTS(cls, model):
        try:
            spec = _CATALOG.get(model)
            if spec.capability not in cls.CAPABILITIES or spec.status.value != "active":
                return "The selected model is incompatible with this node."
        except Exception:
            return "Unknown model ID."
        return True


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


class ImageGenerateEditNode(CatalogGeneratorNode):
    CAPABILITIES = (Capability.IMAGE_GENERATE, Capability.IMAGE_EDIT)
    CATEGORY = "PRYX/Higgsfield"
    FUNCTION = "generate"
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("images", "image_urls", "request_id", "credits", "usd", "status")

    @classmethod
    def INPUT_TYPES(cls):
        values = _catalog_parameter_inputs(cls.CAPABILITIES)
        values["prompt"] = _prompt_input()
        values.update(_common_generation_inputs())
        values.update(
            {
                "references": (
                    ReferenceCollection.TYPE,
                    {"tooltip": "Optional ordered image references; the selected model defines the limit."},
                ),
                "image": ("IMAGE", {"tooltip": "Optional source image for image-edit models."}),
            }
        )
        return {"required": {"model": _model_inputs(cls.CAPABILITIES)}, "optional": values}

    def generate(self, model, prompt="", **kwargs):
        valid = self.VALIDATE_INPUTS(model)
        if valid is not True:
            raise ValidationError(valid)
        values = dict(kwargs)
        values["prompt"] = prompt
        references = _with_reference_inputs(values.pop("references", None), image=values.pop("image", None), end_image=values.pop("end_image", None), model_id=model)
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
        return _image_result(outcome)


class TextToVideoNode(CatalogGeneratorNode):
    CAPABILITIES = (Capability.TEXT_TO_VIDEO,)
    CATEGORY = "PRYX/Higgsfield"
    FUNCTION = "generate"
    RETURN_TYPES = ("VIDEO", "STRING", "STRING", "STRING", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("video", "local_file", "remote_url", "request_id", "credits", "usd", "status")

    @classmethod
    def INPUT_TYPES(cls):
        return _generator_inputs(Capability.TEXT_TO_VIDEO)

    def generate(self, model, prompt="", **kwargs):
        valid = self.VALIDATE_INPUTS(model)
        if valid is not True:
            raise ValidationError(valid)
        values = dict(kwargs)
        values["prompt"] = prompt
        outcome = execute_generation(
            model,
            _arguments_for_model(model, values),
            mode=values.get("mode", "estimate_only"),
            max_usd=float(values.get("max_usd", 0.0)),
            auto_save=bool(values.get("auto_save", True)),
            timeout=float(values.get("timeout", 1800.0)),
        )
        return _video_result(outcome)


class ImageToVideoNode(CatalogGeneratorNode):
    CAPABILITIES = (Capability.IMAGE_TO_VIDEO,)
    CATEGORY = "PRYX/Higgsfield"
    FUNCTION = "generate"
    RETURN_TYPES = ("VIDEO", "STRING", "STRING", "STRING", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("video", "local_file", "remote_url", "request_id", "credits", "usd", "status")

    @classmethod
    def INPUT_TYPES(cls):
        return _generator_inputs(
            Capability.IMAGE_TO_VIDEO,
            optional={
                "image": ("IMAGE", {"tooltip": "Start image. The selected model defines whether it is required."}),
                "end_image": ("IMAGE", {"tooltip": "Optional last frame. Exactly one image; available only for models supporting end frames."}),
                "references": (ReferenceCollection.TYPE, {"tooltip": "Optional ordered references; the selected model defines the limit."}),
            },
        )

    def generate(self, model, prompt="", **kwargs):
        valid = self.VALIDATE_INPUTS(model)
        if valid is not True:
            raise ValidationError(valid)
        values = dict(kwargs)
        values["prompt"] = prompt
        references = _with_reference_inputs(values.pop("references", None), image=values.pop("image", None), end_image=values.pop("end_image", None), model_id=model)
        outcome = execute_generation(
            model,
            _arguments_for_model(model, values),
            mode=values.get("mode", "estimate_only"),
            max_usd=float(values.get("max_usd", 0.0)),
            auto_save=bool(values.get("auto_save", True)),
            timeout=float(values.get("timeout", 1800.0)),
            references=references,
        )
        return _video_result(outcome)


class ReferencePreviewNode:
    CATEGORY = "PRYX/Higgsfield"
    FUNCTION = "preview"
    RETURN_TYPES = ("STRING", ReferenceCollection.TYPE, "STRING", "STRING")
    RETURN_NAMES = ("prompt", "references", "model", "reference_info")
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model": (_models(Capability.REFERENCE_TO_VIDEO),)},
                "optional": {
                    "prompt": ("STRING", {"forceInput": True, "tooltip": "Use {{ref:label}} for named references where supported. This preview never uploads or generates."}),
                    "references": (ReferenceCollection.TYPE,),
                    "image": ("IMAGE",), "video": ("VIDEO",), "audio": ("AUDIO",),
                }}

    def preview(self, model, prompt="", references=None, image=None, video=None, audio=None):
        refs = _with_reference_inputs(references, image=image, video=video, audio=audio, model_id=model)
        _, _, info = reference_prompt(_CATALOG.get(model), refs, prompt)
        # Preserve aliases so the receiving generator validates the final mapping again.
        return {"ui": {"text": [info]}, "result": (prompt, refs, model, info)}


class ReferenceToVideoNode(CatalogGeneratorNode):
    CAPABILITIES = (Capability.REFERENCE_TO_VIDEO,)
    CATEGORY = "PRYX/Higgsfield"
    FUNCTION = "generate"
    RETURN_TYPES = ("VIDEO", "STRING", "STRING", "STRING", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("video", "local_file", "remote_url", "request_id", "credits", "usd", "status")

    @classmethod
    def INPUT_TYPES(cls):
        return _generator_inputs(
            Capability.REFERENCE_TO_VIDEO,
            optional={
                "references": (ReferenceCollection.TYPE, {"tooltip": "Ordered references. Hover the model field to see supported media and limits."}),
                "image": ("IMAGE", {"tooltip": "Optional image reference; batches are split into ordered references."}),
                "video": ("VIDEO", {"tooltip": "Optional video reference."}),
                "audio": ("AUDIO", {"tooltip": "Optional audio reference."}),
            },
        )

    def generate(self, model, prompt="", **kwargs):
        valid = self.VALIDATE_INPUTS(model)
        if valid is not True:
            raise ValidationError(valid)
        values = dict(kwargs)
        values["prompt"] = prompt
        references = _with_reference_inputs(
            values.pop("references", None),
            image=values.pop("image", None),
            video=values.pop("video", None),
            audio=values.pop("audio", None),
            model_id=model,
        )
        outcome = execute_generation(
            model,
            _arguments_for_model(model, values),
            mode=values.get("mode", "estimate_only"),
            max_usd=float(values.get("max_usd", 0.0)),
            auto_save=bool(values.get("auto_save", True)),
            timeout=float(values.get("timeout", 1800.0)),
            references=references,
        )
        return _video_result(outcome)


class VideoEditNode(CatalogGeneratorNode):
    CAPABILITIES = (Capability.VIDEO_EDIT,)
    CATEGORY = "PRYX/Higgsfield"
    FUNCTION = "generate"
    RETURN_TYPES = ("VIDEO", "STRING", "STRING", "STRING", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("video", "local_file", "remote_url", "request_id", "credits", "usd", "status")

    @classmethod
    def INPUT_TYPES(cls):
        return _generator_inputs(
            Capability.VIDEO_EDIT,
            optional={
                "video": ("VIDEO", {"tooltip": "Video to edit. The selected model defines whether it is required."}),
                "references": (ReferenceCollection.TYPE, {"tooltip": "Optional ordered edit references."}),
            },
        )

    def generate(self, model, prompt="", **kwargs):
        valid = self.VALIDATE_INPUTS(model)
        if valid is not True:
            raise ValidationError(valid)
        values = dict(kwargs)
        values["prompt"] = prompt
        references = _with_reference_inputs(values.pop("references", None), video=values.pop("video", None), model_id=model)
        outcome = execute_generation(
            model,
            _arguments_for_model(model, values),
            mode=values.get("mode", "estimate_only"),
            max_usd=float(values.get("max_usd", 0.0)),
            auto_save=bool(values.get("auto_save", True)),
            timeout=float(values.get("timeout", 1800.0)),
            references=references,
        )
        return _video_result(outcome)


class VideoExtendNode(CatalogGeneratorNode):
    CAPABILITIES = (Capability.VIDEO_EXTEND,)
    CATEGORY = "PRYX/Higgsfield"
    FUNCTION = "generate"
    RETURN_TYPES = ("VIDEO", "STRING", "STRING", "STRING", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("video", "local_file", "remote_url", "request_id", "credits", "usd", "status")

    @classmethod
    def INPUT_TYPES(cls):
        return _generator_inputs(
            Capability.VIDEO_EXTEND,
            optional={
                "video": ("VIDEO", {"tooltip": "Video to extend. The selected model defines the valid duration."}),
                "references": (ReferenceCollection.TYPE, {"tooltip": "Optional ordered extension references."}),
            },
        )

    def generate(self, model, prompt="", **kwargs):
        valid = self.VALIDATE_INPUTS(model)
        if valid is not True:
            raise ValidationError(valid)
        values = dict(kwargs)
        values["prompt"] = prompt
        references = _with_reference_inputs(values.pop("references", None), video=values.pop("video", None), model_id=model)
        outcome = execute_generation(
            model,
            _arguments_for_model(model, values),
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
        return {
            "required": {
                "model": (
                    "STRING",
                    {
                        "default": all_models[0],
                        "choices": all_models,
                        "options": all_models,
                        "widgetType": "COMBO",
                        "tooltip": "Catalog model ID for an advanced request. The endpoint remains catalog-controlled.",
                    },
                ),
                "arguments_json": (
                    "STRING",
                    {
                        "default": "{}",
                        "multiline": True,
                        "tooltip": "JSON object with catalog arguments. The API endpoint cannot be overridden.",
                    },
                ),
            },
            "optional": _common_generation_inputs(),
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
