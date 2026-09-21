"""ComfyUI node registrations."""

from .catalog_node import ModelCatalogNode
from .generation import (
    AdvancedRequestNode,
    ImageGenerateEditNode,
    ImageToVideoNode,
    ReferenceToVideoNode,
    TextToVideoNode,
    VideoEditNode,
    VideoExtendNode,
)
from .references import ReferenceCollectorNode


NODE_CLASS_MAPPINGS = {
    "PRYXHiggsfieldModelCatalog": ModelCatalogNode,
    "PRYXHiggsfieldReferenceCollector": ReferenceCollectorNode,
    "PRYXHiggsfieldImageGenerateEdit": ImageGenerateEditNode,
    "PRYXHiggsfieldTextToVideo": TextToVideoNode,
    "PRYXHiggsfieldImageToVideo": ImageToVideoNode,
    "PRYXHiggsfieldReferenceToVideo": ReferenceToVideoNode,
    "PRYXHiggsfieldVideoEdit": VideoEditNode,
    "PRYXHiggsfieldVideoExtend": VideoExtendNode,
    "PRYXHiggsfieldAdvancedRequest": AdvancedRequestNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PRYXHiggsfieldModelCatalog": "PRYX Higgsfield Model Catalog",
    "PRYXHiggsfieldReferenceCollector": "PRYX Higgsfield Reference Collector",
    "PRYXHiggsfieldImageGenerateEdit": "PRYX Higgsfield Image Generate & Edit",
    "PRYXHiggsfieldTextToVideo": "PRYX Higgsfield Text to Video",
    "PRYXHiggsfieldImageToVideo": "PRYX Higgsfield Image to Video",
    "PRYXHiggsfieldReferenceToVideo": "PRYX Higgsfield Reference to Video",
    "PRYXHiggsfieldVideoEdit": "PRYX Higgsfield Video Edit",
    "PRYXHiggsfieldVideoExtend": "PRYX Higgsfield Video Extend",
    "PRYXHiggsfieldAdvancedRequest": "PRYX Higgsfield Advanced Request",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
