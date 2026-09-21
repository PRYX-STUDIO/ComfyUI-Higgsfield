import copy

import pytest

from pryx_higgsfield.catalog import load_bundled_catalog
from pryx_higgsfield.catalog.catalog import CatalogError, validate_catalog_payload


def test_bundled_catalog_has_documented_model_families():
    catalog = load_bundled_catalog()
    assert len(catalog.models) >= 25
    assert catalog.get("soul-2").endpoint == "higgsfield-ai/soul/v2/standard"
    assert catalog.get("seedance-2-5-video-edit").capability.value == "video_edit"
    assert catalog.get("wan-3-reference-to-video").input_media == ("image", "video", "audio", "file", "url")


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
