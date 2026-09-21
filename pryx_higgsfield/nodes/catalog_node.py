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
        return {
            "required": {
                "provider": (["all", *providers], {"default": "all"}),
                "capability": (["all", *capabilities], {"default": "all"}),
                "status": (["active", "deprecated", "unavailable", "all"], {"default": "active"}),
            }
        }

    def select(self, provider="all", capability="all", status="active"):
        catalog = load_bundled_catalog()
        models = catalog.filter(provider=provider, capability=capability, status=status)
        if not models:
            return ("", json.dumps({"models": []}, ensure_ascii=False))
        selected = models[0]
        return (
            selected.id,
            json.dumps(
                {
                    "catalog_version": catalog.catalog_version,
                    "source_date": catalog.source_date,
                    "model": selected.as_dict(),
                    "matches": [model.id for model in models],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
