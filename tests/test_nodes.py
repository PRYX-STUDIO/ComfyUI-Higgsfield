from pryx_higgsfield.nodes import NODE_CLASS_MAPPINGS
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
