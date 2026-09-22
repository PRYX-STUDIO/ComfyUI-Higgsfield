"""Catalog loading, validation, filtering, and offline-safe refresh."""

from __future__ import annotations

import json
import os
import tempfile
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

from ..credentials import default_user_directory
from ..errors import CatalogError, CatalogUnavailableError
from ..types import API_BASE_URL, CATALOG_SCHEMA_VERSION, Capability, ModelSpec, ModelStatus


CATALOG_REMOTE_URL = (
    "https://raw.githubusercontent.com/PRYX-STUDIO/pryx-comfyui-higgsfield/"
    "main/pryx_comfyui_higgsfield/catalog/models.json"
)
MAX_REMOTE_BYTES = 2 * 1024 * 1024
REFRESH_INTERVAL_SECONDS = 24 * 60 * 60


class Catalog:
    def __init__(
        self,
        models: Iterable[ModelSpec],
        *,
        catalog_version: str,
        source_date: str,
        source: str = "bundled",
    ) -> None:
        self.models = tuple(models)
        self.catalog_version = catalog_version
        self.source_date = source_date
        self.source = source
        self._by_id = {model.id: model for model in self.models}

    def get(self, model_id: str) -> ModelSpec:
        try:
            return self._by_id[model_id]
        except KeyError as error:
            raise CatalogError(f"Unknown Higgsfield model ID: {model_id}") from error

    def filter(
        self,
        *,
        provider: str | None = None,
        capability: Capability | str | None = None,
        status: ModelStatus | str | None = ModelStatus.ACTIVE,
    ) -> tuple[ModelSpec, ...]:
        capability_value = capability.value if isinstance(capability, Capability) else capability
        status_value = status.value if isinstance(status, ModelStatus) else status
        return tuple(
            model
            for model in self.models
            if (not provider or provider == "all" or model.provider == provider)
            and (
                not capability_value
                or capability_value == "all"
                or model.capability.value == capability_value
            )
            and (
                not status_value
                or status_value == "all"
                or model.status.value == status_value
            )
        )

    def as_payload(self) -> dict[str, Any]:
        return {
            "schema_version": CATALOG_SCHEMA_VERSION,
            "catalog_version": self.catalog_version,
            "source_date": self.source_date,
            "models": [model.as_dict() for model in self.models],
        }


def load_bundled_catalog() -> Catalog:
    path = Path(__file__).with_name("models.json")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CatalogError("The bundled Higgsfield catalog could not be read.") from error
    return catalog_from_payload(payload, source="bundled")


def catalog_from_payload(payload: Mapping[str, Any], *, source: str) -> Catalog:
    validate_catalog_payload(payload)
    return Catalog(
        [ModelSpec.from_dict(item) for item in payload["models"]],
        catalog_version=str(payload["catalog_version"]),
        source_date=str(payload["source_date"]),
        source=source,
    )


@lru_cache(maxsize=1)
def runtime_catalog() -> Catalog:
    """One immutable schema for frontend, node definitions, and requests per process."""
    bundled = load_bundled_catalog()
    cached = CatalogManager(auto_refresh=False)._read_cache()
    def version(catalog):
        return tuple(int(part) for part in catalog.catalog_version.replace("-", ".").split("."))
    try:
        return cached if cached and version(cached) > version(bundled) else bundled
    except ValueError:
        return bundled


def validate_catalog_payload(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise CatalogError("The Higgsfield catalog must be a JSON object.")
    if payload.get("schema_version") != CATALOG_SCHEMA_VERSION:
        raise CatalogError(
            f"Unsupported catalog schema version: {payload.get('schema_version')}"
        )
    for key in ("catalog_version", "source_date", "models"):
        if key not in payload:
            raise CatalogError(f"Catalog field is missing: {key}")
    if not isinstance(payload["models"], list) or not payload["models"]:
        raise CatalogError("The Higgsfield catalog contains no models.")

    ids: set[str] = set()
    for model in payload["models"]:
        if not isinstance(model, Mapping):
            raise CatalogError("Every catalog model must be an object.")
        required = (
            "id",
            "display_name",
            "provider",
            "family",
            "endpoint",
            "capability",
            "output",
            "parameters",
            "docs_source",
            "docs_checked",
            "status",
        )
        missing = [key for key in required if key not in model]
        if missing:
            raise CatalogError(f"Catalog model is missing fields: {', '.join(missing)}")
        model_id = model["id"]
        if not isinstance(model_id, str) or not model_id or model_id in ids:
            raise CatalogError(f"Catalog model IDs must be unique: {model_id}")
        ids.add(model_id)
        _validate_endpoint(model["endpoint"])
        try:
            Capability(str(model["capability"]))
            ModelStatus(str(model["status"]))
            output = str(model["output"])
            if output not in {"image", "video"}:
                raise ValueError(output)
        except ValueError as error:
            raise CatalogError(f"Unsupported catalog enum in {model_id}.") from error
        parameters = model["parameters"]
        if not isinstance(parameters, list):
            raise CatalogError(f"Parameters must be a list: {model_id}")
        parameter_names: set[str] = set()
        for parameter in parameters:
            if not isinstance(parameter, Mapping) or not parameter.get("name") or not parameter.get("type"):
                raise CatalogError(f"Invalid parameter in catalog model: {model_id}")
            name = str(parameter["name"])
            if name in parameter_names:
                raise CatalogError(f"Duplicate parameter {name} in {model_id}.")
            parameter_names.add(name)
            for key in ("minimum", "maximum", "min_items", "max_items"):
                if key in parameter and not isinstance(parameter[key], (int, float)):
                    raise CatalogError(f"Invalid {key} in {model_id}.{name}.")
        docs_source = str(model["docs_source"])
        if not docs_source.startswith("https://docs.higgsfield.ai/"):
            raise CatalogError(f"Catalog docs source is not official: {model_id}")


def _validate_endpoint(endpoint: Any) -> None:
    if not isinstance(endpoint, str) or not endpoint:
        raise CatalogError("Catalog endpoints must be non-empty strings.")
    if "://" in endpoint or any(value in endpoint for value in ("?", "#", "..")) or chr(92) in endpoint:
        raise CatalogError(f"Catalog endpoint is not a relative API path: {endpoint}")
    if not endpoint.startswith("/") and endpoint.startswith("http"):
        raise CatalogError(f"Catalog endpoint is not allowed: {endpoint}")
    url = urlsplit(f"{API_BASE_URL}/{endpoint.lstrip('/')}")
    if url.scheme != "https" or url.netloc != urlsplit(API_BASE_URL).netloc:
        raise CatalogError(f"Catalog endpoint host is not allowed: {endpoint}")
    if not all(part and all(char.isalnum() or char in "-._~" for char in part) for part in endpoint.split("/")):
        raise CatalogError(f"Catalog endpoint contains unsafe characters: {endpoint}")


class CatalogManager:
    def __init__(
        self,
        *,
        cache_path: str | os.PathLike[str] | None = None,
        remote_url: str = CATALOG_REMOTE_URL,
        auto_refresh: bool = True,
        clock: callable = time.time,
    ) -> None:
        self.cache_path = Path(cache_path) if cache_path else default_user_directory() / ".pryx_comfyui_higgsfield_catalog.json"
        self.remote_url = remote_url
        self.auto_refresh = auto_refresh
        self._clock = clock
        self.last_sync_status = "bundled"

    def load(self) -> Catalog:
        bundled = load_bundled_catalog()
        cached = self._read_cache()
        if cached and not self.auto_refresh:
            self.last_sync_status = "cache:automatic-refresh-disabled"
            return cached
        if cached and self._cache_is_fresh():
            self.last_sync_status = "cache:fresh"
            return cached
        if self.auto_refresh:
            try:
                refreshed = self.refresh()
                self.last_sync_status = "remote:updated"
                return refreshed
            except CatalogError:
                self.last_sync_status = "remote:failed"
        if cached:
            self.last_sync_status = "cache:stale-fallback"
            return cached
        self.last_sync_status = "bundled:fallback"
        return bundled

    def refresh(self) -> Catalog:
        if self.remote_url != CATALOG_REMOTE_URL:
            raise CatalogError("Remote catalog URL is not the approved PRYX catalog URL.")
        request = Request(self.remote_url, headers={"User-Agent": "PRYX-ComfyUI-Higgsfield-Catalog/1.0"})
        try:
            with urlopen(request, timeout=15) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_REMOTE_BYTES:
                    raise CatalogError("Remote catalog exceeds the permitted size.")
                content = response.read(MAX_REMOTE_BYTES + 1)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
            raise CatalogUnavailableError("The remote Higgsfield catalog could not be fetched.") from error
        if len(content) > MAX_REMOTE_BYTES:
            raise CatalogError("Remote catalog exceeds the permitted size.")
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise CatalogError("The remote Higgsfield catalog is not valid JSON.") from error
        catalog = catalog_from_payload(payload, source="remote")
        self._write_cache(payload)
        return catalog

    def metadata(self) -> dict[str, Any]:
        catalog = self._read_cache()
        bundled = load_bundled_catalog()
        return {
            "catalog_version": catalog.catalog_version if catalog else bundled.catalog_version,
            "source_date": catalog.source_date if catalog else bundled.source_date,
            "source": catalog.source if catalog else "bundled",
            "last_sync_status": self.last_sync_status,
            "cache_path": str(self.cache_path),
        }

    def _read_cache(self) -> Catalog | None:
        if not self.cache_path.exists():
            return None
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return catalog_from_payload(payload, source="cache")
        except (OSError, ValueError, CatalogError):
            return None

    def _cache_is_fresh(self) -> bool:
        try:
            return self._clock() - self.cache_path.stat().st_mtime < REFRESH_INTERVAL_SECONDS
        except OSError:
            return False

    def _write_cache(self, payload: Mapping[str, Any]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f"{self.cache_path.name}.",
                suffix=".tmp",
                dir=self.cache_path.parent,
                delete=False,
            ) as handle:
                temporary = handle.name
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.cache_path)
        except OSError as error:
            if temporary:
                try:
                    Path(temporary).unlink(missing_ok=True)
                except OSError:
                    pass
            raise CatalogError("The validated catalog could not be cached.") from error
