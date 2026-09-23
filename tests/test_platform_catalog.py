"""Fail-closed catalog discovery without paid requests or credentials."""

import copy
import json

import pytest

from pryx_comfyui_higgsfield.catalog import load_bundled_catalog
from tools import sync_platform_catalog as platform


def test_official_flight_reference_extracts_matching_endpoint_and_family(monkeypatch):
    slug = "minimax/h3/reference-to-video"
    schema = {"type": "object", "properties": {"prompt": {"type": "string"}}}
    data = (f"https://api.higgsfield.ai/{slug} ### Input JSON Schema\n"
            f"```json\n{json.dumps(schema)}\n```\n"
            f'"family":[{{"slug":"{slug}","title":"MiniMax H3"}},'
            '{"slug":"minimax/h3/image-to-video"}]')
    page = f"<script>self.__next_f.push([1,{json.dumps(data)}])</script>"
    monkeypatch.setattr(platform, "fetch_public", lambda url: page)
    variants, item = platform.inspect_family(slug)
    assert variants == {slug, "minimax/h3/image-to-video"}
    assert item["schema"] == schema


def test_missing_reference_fails_instead_of_generating_partial_catalog(monkeypatch):
    monkeypatch.setattr(platform, "fetch_public", lambda url: "<html></html>")
    with pytest.raises(ValueError, match="No model links"):
        platform.audit()
    monkeypatch.setattr(platform, "fetch_public", lambda url: '<a href="/models/example/playground">Test</a>')
    monkeypatch.setattr(platform, "inspect_family", lambda slug: (
        {slug}, {"slug": slug, "schema": {"type": "object", "properties": {}},
                  "source": "https://open.higgsfield.ai/models/example/api-reference",
                  "title": "Example", "variant_title": "", "operation_type": "text2image"}))
    with pytest.raises(ValueError, match="partial platform catalog"):
        platform.audit()


def test_disappeared_endpoint_requires_manual_review():
    bundled = load_bundled_catalog().as_payload()
    slug = bundled["models"][0]["endpoint"]
    item = {"slug": slug, "schema": copy.deepcopy(bundled["models"][0]["input_schema"]),
            "source": bundled["models"][0]["docs_source"], "title": "Example",
            "variant_title": "", "operation_type": "image2video"}
    with pytest.raises(ValueError, match="Previously cataloged endpoints missing"):
        platform.build_catalog({slug: item}, bundled)
