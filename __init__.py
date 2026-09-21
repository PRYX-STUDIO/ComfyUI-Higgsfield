"""ComfyUI loader for the Higgsfield node pack."""

try:
    from pryx_higgsfield import (
        NODE_CLASS_MAPPINGS,
        NODE_DISPLAY_NAME_MAPPINGS,
        WEB_DIRECTORY,
    )
except Exception as _load_error:  # pragma: no cover - ComfyUI logs the detail
    NODE_CLASS_MAPPINGS = {}
    NODE_DISPLAY_NAME_MAPPINGS = {}
    WEB_DIRECTORY = None
    print(f"[Higgsfield] Could not load nodes: {_load_error}")


__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]
