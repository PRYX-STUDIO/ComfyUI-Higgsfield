"""ComfyUI node registrations."""

from .catalog_node import ModelCatalogNode
from .generation import (
    AdvancedRequestNode,
    ImageGenerateEditNode,
    ImageToVideoNode,
    ReferenceToVideoNode,
    ReferencePreviewNode,
    TextToVideoNode,
    VideoEditNode,
    VideoExtendNode,
)
from .references import ReferenceCollectorNode


NODE_CLASS_MAPPINGS = {
    "PRYXComfyUIHiggsfieldModelCatalog": ModelCatalogNode,
    "PRYXComfyUIHiggsfieldReferenceCollector": ReferenceCollectorNode,
    "PRYXComfyUIHiggsfieldReferencePreview": ReferencePreviewNode,
    "PRYXComfyUIHiggsfieldImageGenerateEdit": ImageGenerateEditNode,
    "PRYXComfyUIHiggsfieldTextToVideo": TextToVideoNode,
    "PRYXComfyUIHiggsfieldImageToVideo": ImageToVideoNode,
    "PRYXComfyUIHiggsfieldReferenceToVideo": ReferenceToVideoNode,
    "PRYXComfyUIHiggsfieldVideoEdit": VideoEditNode,
    "PRYXComfyUIHiggsfieldVideoExtend": VideoExtendNode,
    "PRYXComfyUIHiggsfieldAdvancedRequest": AdvancedRequestNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PRYXComfyUIHiggsfieldModelCatalog": "PRYX ComfyUI Higgsfield Model Catalog",
    "PRYXComfyUIHiggsfieldReferenceCollector": "PRYX ComfyUI Higgsfield Reference Collector",
    "PRYXComfyUIHiggsfieldReferencePreview": "PRYX ComfyUI Higgsfield Reference Preview",
    "PRYXComfyUIHiggsfieldImageGenerateEdit": "PRYX ComfyUI Higgsfield Image Generate & Edit",
    "PRYXComfyUIHiggsfieldTextToVideo": "PRYX ComfyUI Higgsfield Text to Video",
    "PRYXComfyUIHiggsfieldImageToVideo": "PRYX ComfyUI Higgsfield Image to Video",
    "PRYXComfyUIHiggsfieldReferenceToVideo": "PRYX ComfyUI Higgsfield Reference to Video",
    "PRYXComfyUIHiggsfieldVideoEdit": "PRYX ComfyUI Higgsfield Video Edit",
    "PRYXComfyUIHiggsfieldVideoExtend": "PRYX ComfyUI Higgsfield Video Extend",
    "PRYXComfyUIHiggsfieldAdvancedRequest": "PRYX ComfyUI Higgsfield Advanced Request",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
