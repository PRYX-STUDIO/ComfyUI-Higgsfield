"""Local ComfyUI routes for credentials, catalog management, and progress."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from .catalog import CatalogManager, runtime_catalog
from .credentials import CredentialStore, Credentials, default_user_directory, mask_key_id, resolve_credentials
from .errors import HiggsfieldError, redact_secrets
from .styles import StyleManager
from .types import ProgressEvent


_registered = False
_prompt_server: Any = None


@lru_cache(maxsize=1)
def catalog_manager() -> CatalogManager:
    return CatalogManager(cache_path=default_user_directory() / ".pryx_comfyui_higgsfield_catalog.json")


@lru_cache(maxsize=1)
def credential_store() -> CredentialStore:
    return CredentialStore(default_user_directory() / ".pryx_comfyui_higgsfield_credentials.json")


@lru_cache(maxsize=1)
def style_manager() -> StyleManager:
    return StyleManager(cache_path=default_user_directory() / ".pryx_comfyui_higgsfield_soul_styles.json")


def register_routes() -> None:
    global _registered, _prompt_server
    if _registered:
        return
    try:
        from aiohttp import web
        from server import PromptServer
    except ImportError:
        return

    _prompt_server = PromptServer.instance
    routes = _prompt_server.routes

    async def get_settings(request):
        return web.json_response(credential_store().metadata())

    async def put_settings(request):
        try:
            data = await request.json()
            key_id = data.get("key_id")
            secret = data.get("secret")
            credential_store().save(key_id, secret)
            return web.json_response(credential_store().metadata())
        except (HiggsfieldError, AttributeError, TypeError, ValueError) as error:
            return web.json_response({"error": redact_secrets(str(error))}, status=400)

    async def delete_settings(request):
        try:
            credential_store().delete()
            return web.json_response({"configured": False, "source": "none", "key_id": None})
        except HiggsfieldError as error:
            return web.json_response({"error": redact_secrets(str(error))}, status=400)

    async def validate_settings(request):
        try:
            data = await request.json()
        except Exception:
            data = {}
        try:
            credentials = _credentials_from_request(data)
            from .catalog import load_bundled_catalog
            from .client import HiggsfieldClient

            model = load_bundled_catalog().get("soul-2")
            client = HiggsfieldClient(credentials, timeout=60)
            try:
                estimate = client.validate_credentials(model)
            finally:
                client.close()
            return web.json_response(
                {
                    "valid": True,
                    "key_id": mask_key_id(credentials.key_id),
                    "credits": estimate.credits,
                    "usd": estimate.usd,
                }
            )
        except HiggsfieldError as error:
            return web.json_response({"valid": False, "error": redact_secrets(str(error))}, status=400)

    async def get_catalog(request):
        try:
            catalog = runtime_catalog()
            return web.json_response(
                {
                    "schema_version": 1,
                    "catalog_version": catalog.catalog_version,
                    "source_date": catalog.source_date,
                    "source": catalog.source,
                    "last_sync_status": catalog_manager().last_sync_status,
                    "models": catalog.as_payload()["models"],
                }
            )
        except HiggsfieldError as error:
            return web.json_response({"error": redact_secrets(str(error))}, status=503)

    async def refresh_catalog(request):
        try:
            catalog = catalog_manager().refresh()
            return web.json_response(
                {
                    "catalog_version": catalog.catalog_version,
                    "source_date": catalog.source_date,
                    "source": catalog.source,
                    "models": catalog.as_payload()["models"],
                }
            )
        except HiggsfieldError as error:
            return web.json_response({"error": redact_secrets(str(error))}, status=502)

    async def get_styles(request):
        variant = request.query.get("variant", "soul-2")
        refresh = request.query.get("refresh", "false").lower() == "true"
        try:
            credentials = resolve_credentials(credential_store())
            from .client import HiggsfieldClient

            client = HiggsfieldClient(credentials, timeout=60)
            try:
                styles = style_manager().load(client, variant, refresh=refresh)
            finally:
                client.close()
            return web.json_response({"variant": variant, "styles": styles})
        except HiggsfieldError as error:
            return web.json_response({"error": redact_secrets(str(error))}, status=400)

    routes.get("/pryx-comfyui-higgsfield/settings")(get_settings)
    routes.put("/pryx-comfyui-higgsfield/settings")(put_settings)
    routes.delete("/pryx-comfyui-higgsfield/settings")(delete_settings)
    routes.post("/pryx-comfyui-higgsfield/settings/validate")(validate_settings)
    routes.get("/pryx-comfyui-higgsfield/catalog")(get_catalog)
    routes.post("/pryx-comfyui-higgsfield/catalog/refresh")(refresh_catalog)
    routes.get("/pryx-comfyui-higgsfield/styles")(get_styles)
    _registered = True


def _credentials_from_request(data: Any) -> Credentials:
    if isinstance(data, dict) and data.get("key_id") and data.get("secret"):
        return Credentials(str(data["key_id"]), str(data["secret"]), "settings:validation")
    return resolve_credentials(credential_store())


def emit_progress(event: ProgressEvent | dict[str, Any]) -> None:
    """Send a non-secret progress event to the active ComfyUI websocket."""

    if _prompt_server is None:
        return
    payload = event.as_dict() if isinstance(event, ProgressEvent) else dict(event)
    try:
        _prompt_server.send_sync("pryx_comfyui_higgsfield.progress", payload)
    except Exception:
        # Progress is auxiliary. A websocket incompatibility must not fail a
        # generation that is otherwise running correctly.
        return
