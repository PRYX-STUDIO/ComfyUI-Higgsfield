"""PRYX ComfyUI Higgsfield."""

from pathlib import Path

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
from .server import register_routes


WEB_DIRECTORY = str(Path(__file__).resolve().parent / "web")
register_routes()


__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]
