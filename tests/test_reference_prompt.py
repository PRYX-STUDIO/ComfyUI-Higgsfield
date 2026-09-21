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


def test_one_collector_accepts_multiple_media_in_numeric_order():
    refs = ReferenceCollectorNode().collect(
        image=["one"], image_10=["ten"], image_2=["two"],
        video="clip", audio_2="sound", names="image_1=person\nimage_2=outfit\nvideo_1=camera",
    )[0]
    assert [ref.value for ref in refs] == ["one", "two", "ten", "clip", "sound"]
    assert [ref.label for ref in refs] == ["person", "outfit", "image_10", "camera", "audio_2"]
    prompt, _, info = reference_prompt(WAN, refs, "{{ref:outfit}} and {{ref:camera}}")
    assert prompt == "Image 2 and Video 1"
    assert "Collector image_2" in info


def test_numbered_collector_batches_get_unique_labels():
    refs = ReferenceCollectorNode().collect(image=["one", "two"], names="image_1=person")[0]
    assert [ref.label for ref in refs] == ["person[1]", "person[2]"]
    assert reference_prompt(WAN, refs, "{{ref:person[2]}}")[0] == "Image 2"


@pytest.mark.parametrize("names", ["image_1 person", "image_31=person", "image_1=", "image_1=a\nimage_1=b", "image_1={person}"])
def test_invalid_collector_names_are_rejected(names):
    with pytest.raises(ValidationError):
        ReferenceCollectorNode().collect(names=names)


def test_preview_lists_every_reference_model_and_preserves_end_frame():
    choices = ReferencePreviewNode.INPUT_TYPES()["required"]["model"][0]
    assert set(choices) == {m.id for m in CATALOG.models if m.input_media and m.status.value == "active"}
    assert "grok-image-2" in choices
    result = ReferencePreviewNode().preview("seedance-2-5-image-to-video", image=["start"], end_image=["end"])
    refs = result["result"][1]
    assert [ref.field for ref in refs] == ["image_url", "end_image_url"]
    assert "End image" in result["result"][3]


def test_image_edit_preview_lists_multiple_images_without_claiming_prompt_tokens():
    refs = ReferenceCollectorNode().collect(image=["one"], image_2=["two"])[0]
    result = ReferencePreviewNode().preview("grok-image-2", references=refs)
    info = result["result"][3]
    assert "Image 1 ← image_1" in info
    assert "Image 2 ← image_2" in info
    assert "NOT confirmed" in info


def test_legacy_collector_chain_remains_compatible():
    first = ReferenceCollectorNode().collect(image=["one"], label="person")[0]
    second = ReferenceCollectorNode().collect(references=first, image=["two"], label="outfit")[0]
    assert [ref.value for ref in second] == ["one", "two"]
    assert reference_prompt(WAN, second, "{{ref:outfit}}")[0] == "Image 2"
