"""Model catalog inspection node."""

from __future__ import annotations

import json

from ..catalog import load_bundled_catalog


class ModelCatalogNode:
    CATEGORY = "PRYX/Higgsfield"
    FUNCTION = "select"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("model_id", "model_info")

    @classmethod
    def INPUT_TYPES(cls):
        catalog = load_bundled_catalog()
        providers = sorted({model.provider for model in catalog.models})
        capabilities = sorted({model.capability.value for model in catalog.models})
        model_ids = [model.id for model in catalog.models]
        return {
            "required": {
                "model_id": (
                    "STRING",
                    {
                        "default": model_ids[0],
                        "choices": model_ids,
                        "options": model_ids,
                        "widgetType": "COMBO",
                        "tooltip": "Select a catalog model. This STRING output can drive a generator model input.",
                    },
                ),
                "provider": (["all", *providers], {"default": "all"}),
                "capability": (["all", *capabilities], {"default": "all"}),
                "status": (["active", "deprecated", "unavailable", "all"], {"default": "active"}),
            }
        }

    def select(self, model_id="", provider="all", capability="all", status="active"):
        catalog = load_bundled_catalog()
        models = catalog.filter(provider=provider, capability=capability, status=status)
        if not models:
            return ("", json.dumps({"models": []}, ensure_ascii=False))
        selected = next((model for model in models if model.id == model_id), models[0])
        return (
            selected.id,
            json.dumps(
                {
                    "catalog_version": catalog.catalog_version,
                    "source_date": catalog.source_date,
                    "model": selected.as_dict(),
                    "supported_media": list(selected.input_media),
                    "max_references": selected.max_references,
                    "matches": [model.id for model in models],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
