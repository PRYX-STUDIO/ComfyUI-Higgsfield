"""Authenticated SOUL style lookup with a small local cache."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

from .client import HiggsfieldClient
from .credentials import default_user_directory
from .errors import CatalogError


STYLE_ENDPOINTS = {
    "soul": "/v1/text2image/soul-styles",
    "soul-2": "/v1/text2image/soul-styles/v2",
}
STYLE_CACHE_TTL = 24 * 60 * 60


class StyleManager:
    def __init__(
        self,
        *,
        cache_path: str | os.PathLike[str] | None = None,
        clock=time.time,
    ) -> None:
        self.cache_path = Path(cache_path) if cache_path else default_user_directory() / ".pryx_comfyui_higgsfield_soul_styles.json"
        self.clock = clock

    def load(
        self,
        client: HiggsfieldClient,
        variant: str,
        *,
        refresh: bool = False,
    ) -> list[dict[str, str]]:
        if variant not in STYLE_ENDPOINTS:
            raise CatalogError(f"Unknown SOUL style variant: {variant}")
        if not refresh:
            cached = self._read_cache(variant)
            if cached is not None:
                return cached
        payload = client.get_json(STYLE_ENDPOINTS[variant])
        styles = payload.get("styles") or payload.get("items") or payload.get("data") or []
        if not isinstance(styles, list):
            raise CatalogError("The Higgsfield SOUL styles response is invalid.")
        normalized: list[dict[str, str]] = []
        for style in styles:
            if not isinstance(style, Mapping):
                continue
            style_id = style.get("style_id") or style.get("id")
            name = style.get("name") or style.get("display_name") or style_id
            if isinstance(style_id, str) and style_id and isinstance(name, str):
                normalized.append({"style_id": style_id, "name": name})
        if not normalized:
            raise CatalogError("The Higgsfield SOUL styles response contains no usable styles.")
        self._write_cache(variant, normalized)
        return normalized

    def _read_cache(self, variant: str) -> list[dict[str, str]] | None:
        if not self.cache_path.exists():
            return None
        try:
            if self.clock() - self.cache_path.stat().st_mtime >= STYLE_CACHE_TTL:
                return None
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            values = payload.get(variant)
            if isinstance(values, list) and all(
                isinstance(item, dict) and isinstance(item.get("style_id"), str) and isinstance(item.get("name"), str)
                for item in values
            ):
                return values
        except (OSError, ValueError, TypeError):
            return None
        return None

    def _write_cache(self, variant: str, styles: list[dict[str, str]]) -> None:
        payload: dict[str, Any] = {}
        if self.cache_path.exists():
            try:
                existing = json.loads(self.cache_path.read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    payload.update(existing)
            except (OSError, ValueError):
                pass
        payload[variant] = styles
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=f"{self.cache_path.name}.",
                suffix=".tmp",
                dir=self.cache_path.parent,
                delete=False,
            ) as handle:
                temporary = handle.name
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.cache_path)
        except OSError as error:
            if temporary:
                try:
                    Path(temporary).unlink(missing_ok=True)
                except OSError:
                    pass
            raise CatalogError("The SOUL style cache could not be written.") from error
