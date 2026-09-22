import json

from pryx_comfyui_higgsfield.nodes import NODE_CLASS_MAPPINGS
from pryx_comfyui_higgsfield.nodes.catalog_node import ModelCatalogNode
from pryx_comfyui_higgsfield.nodes.generation import ReferenceToVideoNode, TextToVideoNode
from pryx_comfyui_higgsfield.nodes.references import Reference, ReferenceCollectorNode, ReferenceCollection


def test_all_public_nodes_are_registered():
    assert "PRYXComfyUIHiggsfieldAdvancedRequest" in NODE_CLASS_MAPPINGS
    assert all(name.startswith("PRYXComfyUIHiggsfield") for name in NODE_CLASS_MAPPINGS)


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
    assert model_input[1]["choices"] == [
        "seedance-2-reference-to-video",
        "seedance-2-5-reference-to-video",
        "wan-3-reference-to-video",
    ]


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
