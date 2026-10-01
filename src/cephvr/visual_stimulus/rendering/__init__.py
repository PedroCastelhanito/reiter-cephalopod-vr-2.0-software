"""GL-thread renderer orchestration and deterministic render math."""

from cephvr.visual_stimulus.rendering.engine import (
    PreparedSession,
    RendererEngine,
    RendererStateError,
)
from cephvr.visual_stimulus.rendering.types import (
    DisplayInitialization,
    EvidenceStateSnapshot,
    InstanceSnapshot,
    MediaSnapshot,
    OutputActivity,
    PoseSnapshot,
    RenderedOutput,
    RenderGroup,
    RenderPassResult,
    RenderUpdate,
    ResourceReleaseReport,
    SubmissionSnapshot,
    UniformSnapshot,
)

__all__ = [
    "DisplayInitialization",
    "EvidenceStateSnapshot",
    "InstanceSnapshot",
    "MediaSnapshot",
    "OutputActivity",
    "PreparedSession",
    "RenderGroup",
    "RenderPassResult",
    "RenderUpdate",
    "RenderedOutput",
    "RendererEngine",
    "RendererStateError",
    "ResourceReleaseReport",
    "PoseSnapshot",
    "SubmissionSnapshot",
    "UniformSnapshot",
]
