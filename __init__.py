"""ComfyUI loader for the PRYX ComfyUI Higgsfield node pack."""

from pathlib import Path
import sys


_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


try:
    from pryx_comfyui_higgsfield import (
        NODE_CLASS_MAPPINGS,
        NODE_DISPLAY_NAME_MAPPINGS,
        WEB_DIRECTORY,
    )
except Exception as _load_error:  # pragma: no cover - ComfyUI logs the detail
    NODE_CLASS_MAPPINGS = {}
    NODE_DISPLAY_NAME_MAPPINGS = {}
    WEB_DIRECTORY = None
    print(f"[PRYX ComfyUI Higgsfield] Could not load nodes: {_load_error}")


__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]
