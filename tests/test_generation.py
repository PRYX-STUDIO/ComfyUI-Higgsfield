import pytest

from pryx_comfyui_higgsfield.catalog import load_bundled_catalog
from pryx_comfyui_higgsfield.errors import ValidationError
from pryx_comfyui_higgsfield.nodes.common import execute_generation
from pryx_comfyui_higgsfield.nodes.references import Reference
from pryx_comfyui_higgsfield.types import Estimate


class EstimateOnlyClient:
    def __init__(self):
        self.estimate_calls = 0
        self.submit_calls = 0

    def estimate(self, model, arguments):
        self.estimate_calls += 1
        return Estimate(credits=2.0, usd=0.12, raw={"credits": "2.0", "usd": "0.12"})

    def submit(self, model, arguments):
        self.submit_calls += 1
        raise AssertionError("submit must not be called by the cost guard")


def test_max_usd_blocks_generation_after_estimate():
    client = EstimateOnlyClient()
    model_id = "soul-2"
    with pytest.raises(ValidationError, match="no generation request was sent"):
        execute_generation(
            model_id,
            {"prompt": "safe test"},
            mode="generate",
            max_usd=0.10,
            auto_save=True,
            timeout=60,
            client=client,
            catalog=load_bundled_catalog(),
        )
    assert client.estimate_calls == 1
    assert client.submit_calls == 0


def test_estimate_only_returns_without_request_id():
    client = EstimateOnlyClient()
    outcome = execute_generation(
        "soul-2",
        {"prompt": "safe test"},
        mode="estimate_only",
        max_usd=0,
        auto_save=True,
        timeout=60,
        client=client,
        catalog=load_bundled_catalog(),
    )
    assert outcome.request_id == ""
    assert outcome.status == "estimated"
    assert client.submit_calls == 0


def test_description_based_usd_passes_max_usd_and_status_reports_unknown_credits():
    class DescriptionEstimateClient(EstimateOnlyClient):
        def estimate(self, model, arguments):
            self.estimate_calls += 1
            return Estimate(
                credits=None,
                usd=0.65,
                raw={"type": "description", "pricing_description": "2K costs $0.13 per generated second."},
                usd_source="pricing_description",
            )

    client = DescriptionEstimateClient()
    outcome = execute_generation(
        "minimax-h3-reference-to-video",
        {"prompt": "synthetic reference test", "duration": 5, "resolution": "2K"},
        mode="estimate_only",
        max_usd=1.0,
        auto_save=False,
        timeout=60,
        references=[Reference("image", url="https://cdn.example/synthetic.png")],
        client=client,
        catalog=load_bundled_catalog(),
    )

    import json

    status = json.loads(outcome.status_json())
    assert outcome.status == "estimated"
    assert status["estimate"] == {
        "credits": None,
        "pricing_description": "2K costs $0.13 per generated second.",
        "usd": 0.65,
        "usd_source": "pricing_description",
    }
    assert client.estimate_calls == 1
    assert client.submit_calls == 0
