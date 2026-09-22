import pytest

from pryx_comfyui_higgsfield.catalog import load_bundled_catalog
from pryx_comfyui_higgsfield.errors import ValidationError
from pryx_comfyui_higgsfield.validation import normalize_arguments, references_to_arguments


def test_required_fields_defaults_and_limits():
    model = load_bundled_catalog().get("seedance-2-5-text-to-video")
    normalized = normalize_arguments(model, {"prompt": "A calm ocean"})
    assert normalized["duration"] == 5
    with pytest.raises(ValidationError):
        normalize_arguments(model, {"prompt": "A calm ocean", "duration": 31})


def test_reference_order_maps_to_endpoint_fields():
    model = load_bundled_catalog().get("seedance-2-5-reference-to-video")
    arguments = references_to_arguments(
        model,
        [
            {"kind": "video", "url": "https://cdn.example/video.mp4"},
            {"kind": "image", "url": "https://cdn.example/image.png"},
            {"kind": "audio", "url": "https://cdn.example/audio.wav"},
        ],
    )
    assert arguments["video_urls"] == ["https://cdn.example/video.mp4"]
    assert arguments["image_urls"] == ["https://cdn.example/image.png"]
    assert arguments["audio_urls"] == ["https://cdn.example/audio.wav"]


def test_references_reject_non_https_urls():
    model = load_bundled_catalog().get("seedance-2-5-reference-to-video")
    with pytest.raises(ValidationError):
        references_to_arguments(model, [{"kind": "image", "url": "http://example.invalid/a.png"}])
