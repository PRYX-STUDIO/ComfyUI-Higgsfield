import copy

import pytest

from pryx_comfyui_higgsfield.catalog import load_bundled_catalog
from pryx_comfyui_higgsfield.catalog.catalog import CatalogError, validate_catalog_payload


def test_bundled_catalog_has_documented_model_families():
    catalog = load_bundled_catalog()
    assert len(catalog.models) >= 25
    assert catalog.get("soul-2").endpoint == "higgsfield-ai/soul/v2/standard"
    assert catalog.get("seedance-2-5-video-edit").capability.value == "video_edit"
    assert set(catalog.get("wan-3-reference-to-video").input_media) == {"image", "video", "audio", "file", "url"}


def test_genjutsu_modes_are_video_edit_models_with_their_documented_inputs():
    catalog = load_bundled_catalog()
    motion_transfer = catalog.get("higgsfiled-genjutsu-motion-transfer-v1-0")
    object_swap = catalog.get("higgsfiled-genjutsu-object-swap-v1-0")

    for model in (motion_transfer, object_swap):
        assert model.capability.value == "video_edit"
        assert model.display_name.startswith("Genjutsu ·")
        assert model.endpoint.startswith("higgsfiled/genjutsu/")
        parameters = model.parameter_map
        assert parameters["video_url"].required is True
        assert parameters["image_urls"].required is True
        assert parameters["image_urls"].min_items == 1
        assert parameters["image_urls"].max_items == 8
        assert parameters["resolution"].choices == ("720p", "480p")


def test_catalog_rejects_duplicate_ids():
    payload = load_bundled_catalog().as_payload()
    payload["models"].append(copy.deepcopy(payload["models"][0]))
    with pytest.raises(CatalogError):
        validate_catalog_payload(payload)


def test_catalog_rejects_non_api_endpoint():
    payload = load_bundled_catalog().as_payload()
    payload["models"][0]["endpoint"] = "https://example.invalid/generation"
    with pytest.raises(CatalogError):
        validate_catalog_payload(payload)


def test_catalog_rejects_video_capability_with_image_output():
    payload = load_bundled_catalog().as_payload()
    video = next(model for model in payload["models"] if model["capability"] == "image_to_video")
    video["output"] = "image"
    with pytest.raises(CatalogError):
        validate_catalog_payload(payload)


def test_catalog_rejects_invalid_or_remote_json_schema():
    payload = load_bundled_catalog().as_payload()
    payload["models"][0]["input_schema"]["properties"]["prompt"]["type"] = "imaginary"
    with pytest.raises(CatalogError):
        validate_catalog_payload(payload)
    payload = load_bundled_catalog().as_payload()
    payload["models"][0]["input_schema"]["properties"]["prompt"]["$ref"] = "https://evil.invalid/schema"
    with pytest.raises(CatalogError):
        validate_catalog_payload(payload)
