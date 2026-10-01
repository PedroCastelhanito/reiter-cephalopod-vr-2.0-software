"""Finite ordered tracking-result consumption and arena movement constraints."""

from cephvr.visual_stimulus.feedback.arena import (
    inset_convex_polygon,
    slide_displacement,
)
from cephvr.visual_stimulus.feedback.batch import FeedbackBatchConsumer
from cephvr.visual_stimulus.feedback.consumer import (
    FeedbackConsumer,
    FeedbackDisposition,
    FeedbackResult,
)
from cephvr.visual_stimulus.feedback.credits import FeedbackCredits
from cephvr.visual_stimulus.feedback.mapping import FeedbackMappingApplier
from cephvr.visual_stimulus.feedback.pipe_consumer import FeedbackPipeConsumer

__all__ = [
    "FeedbackConsumer",
    "FeedbackDisposition",
    "FeedbackResult",
    "FeedbackCredits",
    "FeedbackMappingApplier",
    "FeedbackBatchConsumer",
    "FeedbackPipeConsumer",
    "inset_convex_polygon",
    "slide_displacement",
]
