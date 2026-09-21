from pryx_higgsfield.nodes import NODE_CLASS_MAPPINGS
from pryx_higgsfield.nodes.generation import ReferenceToVideoNode
from pryx_higgsfield.nodes.references import Reference, ReferenceCollectorNode, ReferenceCollection


def test_all_public_nodes_are_registered():
    assert "PRYXHiggsfieldAdvancedRequest" in NODE_CLASS_MAPPINGS
    assert all(name.startswith("PRYXHiggsfield") for name in NODE_CLASS_MAPPINGS)


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
