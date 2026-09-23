"""Every catalog endpoint is exercised with mock HTTP; no credentials or paid calls."""

import json
import re
from types import SimpleNamespace

import httpx
import pytest

from pryx_comfyui_higgsfield.catalog import load_bundled_catalog
from pryx_comfyui_higgsfield.client import HiggsfieldClient
from pryx_comfyui_higgsfield.credentials import Credentials
from pryx_comfyui_higgsfield.errors import ValidationError
from pryx_comfyui_higgsfield.nodes import generation
from pryx_comfyui_higgsfield.nodes.common import execute_generation
from pryx_comfyui_higgsfield.nodes.references import Reference, ReferenceCollection
from pryx_comfyui_higgsfield.types import Estimate
from pryx_comfyui_higgsfield.validation import normalize_arguments, references_to_arguments
from tools.sync_catalog import parse_page


CATALOG = load_bundled_catalog()
CLASSES = [generation.ImageGenerateEditNode, generation.TextToVideoNode,
           generation.ImageToVideoNode, generation.ReferenceToVideoNode,
           generation.VideoEditNode, generation.VideoExtendNode]


def sample_arguments(model):
    result = {"prompt": "Contract test"}
    def sample(schema):
        if "default" in schema:
            return schema["default"]
        if schema.get("enum"):
            return schema["enum"][0]
        kind = schema.get("type")
        if kind == "string":
            return "https://cdn.example/input.png" if schema.get("format") == "uri" else "a" * max(1, schema.get("minLength", 1))
        if kind == "integer":
            return int(schema.get("minimum", 1))
        if kind == "number":
            return float(schema.get("minimum", 1))
        if kind == "boolean":
            return False
        if kind == "array":
            return [sample(schema["items"])] * max(1, schema.get("minItems", 1))
        if kind == "object":
            return {key: sample(schema["properties"][key]) for key in schema.get("required", ())}
        raise AssertionError(f"Unsupported test schema: {schema}")
    if model.input_schema:
        schema = model.input_schema
        result.update({key: sample(schema["properties"][key]) for key in schema.get("required", ()) if key != "prompt"})
        if model.capability.value == "reference_to_video" and not any(p.media_types and p.name in result for p in model.parameters):
            media = next((p for p in model.parameters if p.name == "image_urls"),
                         next(p for p in model.parameters if p.media_types))
            result[media.name] = sample(schema["properties"][media.name])
    else:
        for p in model.parameters:
            if p.required and p.media_types:
                result[p.name] = ["https://cdn.example/input.png"] if p.type == "array" else "https://cdn.example/input.png"
        if model.capability.value == "reference_to_video":
            result["image_urls"] = ["https://cdn.example/input.png"]
    for _ in range(len(model.parameters) + 1):
        try:
            return normalize_arguments(model, result)
        except ValidationError as error:
            missing = re.search(r"'([^']+)' is a required property", str(error))
            if not missing or not model.input_schema or missing.group(1) in result:
                raise
            name = missing.group(1)
            result[name] = sample(model.input_schema["properties"][name])
    raise AssertionError(f"Could not construct a valid sample for {model.id}")


@pytest.mark.parametrize("model", CATALOG.models, ids=lambda m: m.id)
def test_every_model_node_schema_and_http_payload(model, monkeypatch):
    cls = next(cls for cls in CLASSES if model.capability in cls.CAPABILITIES)
    inputs = cls.INPUT_TYPES()
    assert model.id in inputs["required"]["model"][1]["choices"]
    assert cls.VALIDATE_INPUTS(model.id) is True
    for p in model.parameters:
        if p.media_types or p.name == "prompt":
            continue
        widget = inputs["optional"][generation._widget_name(p)]
        if p.choices:
            assert isinstance(widget[0], list)
            assert set(p.choices) <= set(widget[0])
        assert widget[1]["tooltip"]

    expected = sample_arguments(model)
    captured = []
    def handler(request):
        captured.append((request.url.path, json.loads(request.content)))
        if request.url.path.startswith("/estimate/"):
            return httpx.Response(200, json={"credits": 1, "usd": 0.01})
        return httpx.Response(200, json={"status": "queued", "request_id": "test",
            "status_url": "https://api.higgsfield.ai/requests/test/status",
            "cancel_url": "https://api.higgsfield.ai/requests/test/cancel"})
    client = HiggsfieldClient(Credentials("mock", "mock", "test"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        upload_client=httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        client.estimate(model, expected)
        client.submit(model, expected)
    finally:
        client.close()
    assert captured == [("/estimate/" + model.endpoint, expected), ("/" + model.endpoint, expected)]

    calls = []
    monkeypatch.setattr(generation, "execute_generation", lambda *args, **kw: calls.append((args, kw)) or None)
    monkeypatch.setattr(generation, "_image_result", lambda outcome: ())
    monkeypatch.setattr(generation, "_video_result", lambda outcome: ())
    values = {p.name: (json.dumps(expected[p.name]) if p.type in {"array", "object"} else expected[p.name])
              for p in model.parameters if p.name in expected and not p.media_types and p.name != "prompt"}
    refs = ReferenceCollection()
    for spec in model.parameters:
        if spec.name not in expected or not spec.media_types:
            continue
        kind = spec.media_types[0]
        urls = expected[spec.name] if spec.type == "array" else [expected[spec.name]]
        refs.extend(Reference(kind, url=url, field=spec.name) for url in urls)
    cls().generate(model.id, "Contract test", references=refs, **values)
    args, kw = calls[0]
    mapped = references_to_arguments(model, [r.as_dict() for r in kw.get("references", [])])
    assert normalize_arguments(model, {**args[1], **mapped}) == expected
    assert kw["mode"] == "estimate_only"


@pytest.mark.parametrize("model", CATALOG.models, ids=lambda m: m.id)
def test_all_documented_defaults_and_invalid_choices(model):
    valid = sample_arguments(model)
    for spec in model.parameters:
        if spec.default is not None and spec.default != "":
            assert valid[spec.name] == spec.default
        if spec.choices:
            for choice in spec.choices:
                # A choice can activate another conditional requirement.
                if model.input_schema and any(key in model.input_schema for key in ("if", "oneOf", "anyOf")):
                    continue
                normalize_arguments(model, {**valid, spec.name: choice})
            with pytest.raises(ValidationError):
                normalize_arguments(model, {**valid, spec.name: "invalid-choice"})
        if spec.maximum is not None:
            with pytest.raises(ValidationError):
                normalize_arguments(model, {**valid, spec.name: spec.maximum + 1})


def test_required_images_validate_before_upload_and_reach_estimate(monkeypatch):
    uploads, seen = [], []
    monkeypatch.setattr("pryx_comfyui_higgsfield.nodes.common.upload_reference",
        lambda client, ref: uploads.append(ref) or "https://cdn.example/start.png")
    client = SimpleNamespace(estimate=lambda model, args: seen.append(args) or Estimate(1, 0.01))
    execute_generation("seedance-2-5-image-to-video", {}, mode="estimate_only",
        max_usd=0, auto_save=False, timeout=60, client=client,
        references=[Reference("image", b"mock")])
    assert len(uploads) == 1
    assert seen[0]["image_url"] == "https://cdn.example/start.png"
    assert "prompt" not in seen[0]
    with pytest.raises(ValidationError):
        execute_generation("seedance-2-5-image-to-video", {}, mode="estimate_only",
            max_usd=0, auto_save=False, timeout=60, client=client,
            references=[Reference("image", b"mock") for _ in range(3)])
    assert len(uploads) == 1


def test_reference_limits_are_per_field_not_invented_shared_maximum():
    model = CATALOG.get("seedance-2-5-reference-to-video")
    refs = [{"kind": kind, "url": f"https://cdn.example/{kind}/{i}"}
            for kind, count in (("image", 30), ("video", 10), ("audio", 10)) for i in range(count)]
    normalize_arguments(model, references_to_arguments(model, refs))
    with pytest.raises(ValidationError, match="at most 30"):
        references_to_arguments(model, refs + [{"kind": "image", "url": "https://cdn.example/extra"}])


def test_explicit_start_end_and_source_are_not_swapped_with_collector():
    model = CATALOG.get("seedance-2-5-image-to-video")
    mapped = references_to_arguments(model, [
        {"kind": "image", "url": "https://cdn.example/end", "field": "end_image_url"},
        {"kind": "image", "url": "https://cdn.example/start", "field": "image_url"}])
    assert mapped["image_url"].endswith("/start")
    assert mapped["end_image_url"].endswith("/end")
    model = CATALOG.get("seedance-2-5-video-edit")
    mapped = references_to_arguments(model, [
        {"kind": "video", "url": "https://cdn.example/ref"},
        {"kind": "video", "url": "https://cdn.example/source", "field": "video_url"}])
    assert mapped["video_url"].endswith("/source")
    assert mapped["video_urls"] == ["https://cdn.example/ref"]


def test_collector_images_go_to_reference_array_when_source_is_optional():
    model = CATALOG.get("kling-video-o3-image-reference")
    mapped = references_to_arguments(model, [
        {"kind": "image", "url": "https://cdn.example/one"},
        {"kind": "image", "url": "https://cdn.example/two"},
    ])
    assert mapped == {"image_urls": ["https://cdn.example/one", "https://cdn.example/two"]}
    assert references_to_arguments(model, [{"kind": "image", "url": "https://cdn.example/start", "field": "first_frame_url"}]) == {"first_frame_url": "https://cdn.example/start"}


def test_minimax_h3_reference_branches_and_field_limits():
    model = CATALOG.get("minimax-h3-reference-to-video")
    image = {"prompt": "test", "image_urls": ["https://cdn.example/image"]}
    video = {"prompt": "test", "video_urls": ["https://cdn.example/video"]}
    normalize_arguments(model, image)
    normalize_arguments(model, video)
    with pytest.raises(ValidationError):
        normalize_arguments(model, {"prompt": "test"})
    for field, limit in (("image_urls", 9), ("video_urls", 3), ("audio_urls", 3)):
        with pytest.raises(ValidationError):
            normalize_arguments(model, {**image, field: ["https://cdn.example/item"] * (limit + 1)})


def test_provider_mode_does_not_select_paid_generation():
    model = CATALOG.get("kling-video-o3-first-last-frame")
    inputs = generation.ImageToVideoNode.INPUT_TYPES()["optional"]
    assert "mode" in inputs and "request_mode" in inputs
    assert set(inputs["mode"][0]) >= {"std", "pro", "4k"}
    assert generation._arguments_for_model(model.id, {"mode": "4k", "request_mode": "estimate_only"}) == {"mode": "4k"}
    assert generation._arguments_for_model("pixverse-v6-image-to-video", {"duration": 2.5}) == {"duration": 2.5}
    assert generation._arguments_for_model(model.id, {"duration": 5.0}) == {"duration": 5}


def test_json_seed_and_model_capability_guard():
    assert "seed" not in generation._arguments_for_model("soul-2", {"seed": -1})
    assert generation._arguments_for_model("recraft-v4-1-pro", {"colors": '[{"rgb":[0,1,2]}]'})["colors"] == [{"rgb": [0, 1, 2]}]
    with pytest.raises(ValidationError):
        generation._arguments_for_model("recraft-v4-1-pro", {"colors": "not json"})
    with pytest.raises(ValidationError, match="incompatible"):
        generation.TextToVideoNode().generate("soul-2", "test")


@pytest.mark.parametrize("model_id,arguments", [
    ("wan-3-reference-to-video", {"file_url": "https://cdn.example/file", "link_url": "https://cdn.example/link"}),
    ("marketing-studio-image", {"enhance_prompt": True}),
    ("kling-3-pro-text-to-video", {"multi_shots": True}),
    ("kling-3-pro-text-to-video", {"multi_prompt": [{"prompt": "test", "duration": 16}]}),
    ("recraft-v4-1-pro", {"colors": [{"rgb": [256, 0, 0]}]}),
    ("soul-2", {"seed": 0}),
    ("soul-2", {"batch_size": 2}),
])
def test_invalid_combinations_are_rejected(model_id, arguments):
    with pytest.raises(ValidationError):
        normalize_arguments(CATALOG.get(model_id), {"prompt": "test", **arguments})


def test_doc_parser_choices_limits_and_notes():
    page = '''# Test API
**Endpoint ID:** `test/model`
<ParamField body="output_format" type="string" default="mp4">Supported values: `mp4`, `mov`.</ParamField>
<ParamField body="image_urls" type="array">Accepts `1`–`30` URLs when provided.</ParamField>
<ParamField body="seed" type="integer">Seed from `1` to `1000000`.</ParamField>
<ParamField body="batch_size" type="integer" default="1">Supported values: `1`, `4`.</ParamField>
<Note>Provide at least one reference.</Note>'''
    model = parse_page("https://docs.higgsfield.ai/docs/models/test/reference-to-video.md", page)
    params = {p["name"]: p for p in model["parameters"]}
    assert params["output_format"]["choices"] == ["mp4", "mov"]
    assert params["image_urls"]["max_items"] == 30
    assert params["image_urls"]["min_items"] == 1
    assert params["seed"]["minimum"] == 1
    assert params["batch_size"]["choices"] == [1, 4]
    assert model["max_references"] is None
    assert model["notes"] == ["Provide at least one reference."]
