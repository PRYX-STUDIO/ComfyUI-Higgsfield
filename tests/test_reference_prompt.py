import pytest
from types import SimpleNamespace

from pryx_higgsfield.catalog import load_bundled_catalog
from pryx_higgsfield.errors import ValidationError
from pryx_higgsfield.nodes.common import execute_generation
from pryx_higgsfield.nodes.generation import ReferencePreviewNode, _with_reference_inputs
from pryx_higgsfield.nodes.references import Reference, ReferenceCollectorNode
from pryx_higgsfield.reference_prompt import reference_prompt
from pryx_higgsfield.types import Estimate


CATALOG = load_bundled_catalog()
WAN = CATALOG.get("wan-3-reference-to-video")


def test_mapping_matches_direct_inputs_and_collector_order():
    refs = ReferenceCollectorNode().collect(image=["person"], label="person")[0]
    refs = ReferenceCollectorNode().collect(references=refs, video="camera", label="camera")[0]
    refs = _with_reference_inputs(refs, image=["background"], audio="music", model_id=WAN.id)
    prompt, manifest, info = reference_prompt(WAN, refs, "Use {{ref:person}} with {{ref:camera}} and Audio 1.")
    assert prompt == "Use Image 2 with Video 1 and Audio 1."
    assert [entry["input"] for entry in manifest] == ["Image 1", "Audio 1", "Image 2", "Video 1"]
    assert "Image 2 ← person" in info


@pytest.mark.parametrize("refs,prompt,match", [
    ([Reference("image", label="person")], "{{ref:missing}}", "Unknown"),
    ([Reference("image", label="person")] * 2, "{{ref:person}}", "Ambiguous"),
    ([Reference("image")], "Image 2", "missing media"),
    ([Reference("image")], "Video 1", "missing media"),
    ([Reference("image")], "{{ref:broken}", "Malformed"),
])
def test_invalid_mentions_fail(refs, prompt, match):
    with pytest.raises(ValidationError, match=match):
        reference_prompt(WAN, refs, prompt)


@pytest.mark.parametrize("model_id", ["seedance-2-reference-to-video", "seedance-2-5-reference-to-video"])
def test_unconfirmed_syntax_is_not_invented(model_id):
    model = CATALOG.get(model_id)
    refs = [Reference("image", label="person")]
    with pytest.raises(ValidationError, match="not documented"):
        reference_prompt(model, refs, "{{ref:person}}")
    _, manifest, info = reference_prompt(model, refs, "A person walking")
    assert manifest[0]["prompt_token"] is None
    assert "NOT confirmed" in info


def test_preview_is_local_and_preserves_aliases():
    refs = [Reference("image", value="image", label="person")]
    result = ReferencePreviewNode().preview(WAN.id, "Use {{ref:person}}", refs)
    assert result["result"][0] == "Use {{ref:person}}"
    assert result["result"][1][0].value == "image"
    assert result["result"][2] == WAN.id
    assert "Use Image 1" in result["ui"]["text"][0]


def test_generator_resolves_before_api_and_rejects_before_upload(monkeypatch):
    uploaded, sent = [], []
    monkeypatch.setattr("pryx_higgsfield.nodes.common.upload_reference",
                        lambda client, ref: uploaded.append(ref) or "https://cdn.example/image.png")
    client = SimpleNamespace(estimate=lambda model, args: sent.append(args) or Estimate(1, 0.01))
    refs = [Reference("image", value="image", label="person")]
    options = dict(mode="estimate_only", max_usd=0, auto_save=False, timeout=60, references=refs, client=client)
    outcome = execute_generation(WAN.id, {"prompt": "Use {{ref:person}}"}, **options)
    assert outcome.reference_manifest[0]["prompt_token"] == "Image 1"
    assert sent[0]["prompt"] == "Use Image 1"
    assert sent[0]["image_urls"] == ["https://cdn.example/image.png"]
    with pytest.raises(ValidationError):
        execute_generation(WAN.id, {"prompt": "{{ref:missing}}"}, **options)
    assert len(uploaded) == 1


def test_labelled_batch_is_not_silently_assigned_to_first_image():
    refs = ReferenceCollectorNode().collect(image=["one", "two"], label="person")[0]
    with pytest.raises(ValidationError, match="Ambiguous"):
        reference_prompt(WAN, refs, "{{ref:person}}")
    prompt, entries, _ = reference_prompt(WAN, refs, "Use Image 2")
    assert prompt == "Use Image 2"
    assert len(entries) == 2


def test_changing_direct_inputs_recomputes_named_reference_index():
    refs = [Reference("image", label="person")]
    original, _, _ = reference_prompt(WAN, refs, "{{ref:person}}")
    combined = _with_reference_inputs(refs, image=["first", "second"], model_id=WAN.id)
    changed, entries, _ = reference_prompt(WAN, combined, "{{ref:person}}")
    assert (original, changed) == ("Image 1", "Image 3")
    assert entries[0]["label"] == "Direct image 1"
