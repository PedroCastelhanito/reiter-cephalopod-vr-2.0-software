"""Protected stimulus resources and media preparation."""

from cephvr.visual_stimulus.resources.assets import (
    PreparedAsset,
    PreparedAssetSet,
    prepare_assets,
)
from cephvr.visual_stimulus.resources.budget import (
    BoundedBudget,
    PreparationBudget,
    ResourceUsage,
)
from cephvr.visual_stimulus.resources.glb import (
    GLBError,
    GLBPrimitive,
    GLBScene,
    parse_glb,
)
from cephvr.visual_stimulus.resources.media import (
    ImagePixels,
    MediaPreparationError,
    decode_image,
)
from cephvr.visual_stimulus.resources.video_index import (
    SourceFrame,
    VideoIndex,
    index_video,
)

__all__ = [
    "BoundedBudget",
    "GLBError",
    "GLBPrimitive",
    "GLBScene",
    "ImagePixels",
    "MediaPreparationError",
    "PreparedAsset",
    "PreparedAssetSet",
    "PreparationBudget",
    "ResourceUsage",
    "SourceFrame",
    "VideoIndex",
    "decode_image",
    "index_video",
    "parse_glb",
    "prepare_assets",
]
