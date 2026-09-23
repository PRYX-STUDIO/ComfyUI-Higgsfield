import json
import sys
from pathlib import Path
from types import ModuleType

from pryx_comfyui_higgsfield.catalog import runtime_catalog
from pryx_comfyui_higgsfield.nodes import NODE_CLASS_MAPPINGS, generation
from pryx_comfyui_higgsfield.nodes.catalog_node import ModelCatalogNode
from pryx_comfyui_higgsfield.nodes.generation import (
    AdvancedRequestNode,
    ImageGenerateEditNode,
    ImageToVideoNode,
    ReferenceToVideoNode,
    TextToVideoNode,
    VideoEditNode,
    VideoExtendNode,
)
from pryx_comfyui_higgsfield.nodes.references import Reference, ReferenceCollectorNode, ReferenceCollection
from pryx_comfyui_higgsfield.media import _load_native_video
from pryx_comfyui_higgsfield.types import Capability


def test_all_public_nodes_are_registered():
    assert "PRYXComfyUIHiggsfieldAdvancedRequest" in NODE_CLASS_MAPPINGS
    assert all(name.startswith("PRYXComfyUIHiggsfield") for name in NODE_CLASS_MAPPINGS)


def test_native_video_output_uses_comfy_video_from_file(monkeypatch):
    module = ModuleType("comfy_api.latest")
    class FakeVideoFromFile:
        def __init__(self, path):
            self.path = path
    module.VideoFromFile = FakeVideoFromFile
    monkeypatch.setitem(sys.modules, "comfy_api.latest", module)
    video = _load_native_video(Path("example.mp4"))
    assert isinstance(video, FakeVideoFromFile)
    assert video.path == "example.mp4"


def test_reference_collector_preserves_order_and_splits_image_batch():
    node = ReferenceCollectorNode()
    result = node.collect(
        image=[[1], [2]],
        external_url="https://example.invalid/reference.pdf",
        external_type="file",
    )[0]
    assert isinstance(result, ReferenceCollection)
    assert [item.kind for item in result] == ["image", "image", "file"]
    assert result[-1].url == "https://example.invalid/reference.pdf"


def test_reference_to_video_exposes_catalog_model_choices():
    model_input = ReferenceToVideoNode.INPUT_TYPES()["required"]["model"]
    assert model_input[0] == "STRING"
    assert "minimax-h3-reference-to-video" in model_input[1]["choices"]
    assert "seedance-2-5-reference-to-video" in model_input[1]["choices"]


def test_every_active_model_parameter_and_media_kind_has_a_node_input():
    nodes = (
        (ImageGenerateEditNode, {Capability.IMAGE_GENERATE, Capability.IMAGE_EDIT}),
        (TextToVideoNode, {Capability.TEXT_TO_VIDEO}),
        (ImageToVideoNode, {Capability.IMAGE_TO_VIDEO}),
        (ReferenceToVideoNode, {Capability.REFERENCE_TO_VIDEO}),
        (VideoEditNode, {Capability.VIDEO_EDIT, Capability.VIDEO_MOTION}),
        (VideoExtendNode, {Capability.VIDEO_EXTEND}),
        (AdvancedRequestNode, set(Capability)),
    )
    media_parameters = {
        "image_url", "end_image_url", "last_image_url", "first_frame_url", "last_frame_url",
        "image_urls", "video_url", "video_urls", "audio_url", "audio_urls", "file_url", "link_url",
    }
    end_frame_parameters = {"end_image_url", "last_image_url", "last_frame_url"}
    catalog = runtime_catalog()

    for node_class, capabilities in nodes:
        input_types = node_class.INPUT_TYPES()
        optional = input_types.get("optional", {})
        available = set(input_types.get("required", {})) | set(optional)
        models = [
            model for model in catalog.models
            if model.status.value == "active" and model.capability in capabilities
        ]
        assert models, node_class.__name__

        for model in models:
            if node_class is not AdvancedRequestNode:
                expected = {
                    "shots_json" if parameter.name == "shots" else parameter.name
                    for parameter in model.parameters
                    if parameter.name != "prompt" and parameter.name not in media_parameters
                }
                assert expected <= available, f"{node_class.__name__} / {model.id}: {expected - available}"

            media = set(model.input_media)
            for kind in ("image", "video", "audio"):
                if kind in media:
                    assert kind in optional, f"{node_class.__name__} / {model.id} lacks direct {kind} input"
                    assert optional[kind][0] == kind.upper()
            if media:
                assert "references" in optional, f"{node_class.__name__} / {model.id} lacks a collector input"
            if end_frame_parameters.intersection(model.parameter_map):
                assert "end_image" in optional, f"{node_class.__name__} / {model.id} lacks end_image input"


def test_reference_to_video_duration_is_declared_for_every_active_model():
    input_types = ReferenceToVideoNode.INPUT_TYPES()
    available = set(input_types.get("required", {})) | set(input_types.get("optional", {}))
    models = [
        model for model in runtime_catalog().models
        if model.status.value == "active" and model.capability is Capability.REFERENCE_TO_VIDEO
    ]

    assert models
    assert "duration" in available
    assert all("duration" in model.parameter_map for model in models)


def test_text_to_video_direct_audio_is_submitted_as_a_model_reference(monkeypatch):
    audio = object()
    captured = {}
    outcome = object()

    def fake_execute(model_id, arguments, **kwargs):
        captured.update(model_id=model_id, arguments=arguments, **kwargs)
        return outcome

    monkeypatch.setattr(generation, "execute_generation", fake_execute)
    monkeypatch.setattr(generation, "_video_result", lambda value: value)
    result = TextToVideoNode().generate(
        "wan-v2-6-text-to-video",
        prompt="Synthetic audio-conditioned video test",
        audio=audio,
    )

    assert result is outcome
    assert captured["model_id"] == "wan-v2-6-text-to-video"
    assert [reference.kind for reference in captured["references"]] == ["audio"]
    assert captured["references"][0].value is audio
    assert "audio" not in captured["arguments"]
    assert captured["arguments"]["prompt"] == "Synthetic audio-conditioned video test"


def test_genjutsu_modes_are_selectable_in_video_edit_and_usd_cap_defaults_to_zero():
    model_input = VideoEditNode.INPUT_TYPES()["required"]["model"][1]["choices"]
    optional = VideoEditNode.INPUT_TYPES()["optional"]

    assert "higgsfiled-genjutsu-motion-transfer-v1-0" in model_input
    assert "higgsfiled-genjutsu-object-swap-v1-0" in model_input
    assert optional["max_usd"][1]["default"] == 0.0


def test_generator_uses_connected_prompt_and_model_inputs():
    required = TextToVideoNode.INPUT_TYPES()["required"]
    prompt = TextToVideoNode.INPUT_TYPES()["optional"]["prompt"]
    assert prompt[1]["forceInput"] is True
    assert "defaultInput" not in required["model"][1]
    assert required["model"][1]["widgetType"] == "COMBO"
    assert "tooltip" in prompt[1]


def test_generator_signature_is_catalog_union_without_media_url_widgets():
    optional = TextToVideoNode.INPUT_TYPES()["optional"]
    assert "resolution" in optional
    assert "aspect_ratio" in optional
    assert "output_format" in optional
    assert optional["resolution"][1]["widgetType"] == "COMBO"
    assert optional["aspect_ratio"][1]["widgetType"] == "COMBO"
    assert optional["output_format"][1]["widgetType"] == "COMBO"
    assert isinstance(optional["output_format"][0], list)
    assert "image_url" not in optional
    assert "video_urls" not in optional


def test_model_catalog_selects_requested_model_and_returns_limits():
    node = ModelCatalogNode()
    model_id, info = node.select(model_id="wan-3-reference-to-video", capability="reference_to_video")
    assert model_id == "wan-3-reference-to-video"
    parsed = json.loads(info)
    assert parsed["max_references"] is None
    assert set(parsed["supported_media"]) == {"image", "video", "audio", "file", "url"}
    params = {p["name"]: p for p in parsed["model"]["parameters"]}
    assert params["image_urls"]["max_items"] == 10
    assert params["video_urls"]["max_items"] == 5
