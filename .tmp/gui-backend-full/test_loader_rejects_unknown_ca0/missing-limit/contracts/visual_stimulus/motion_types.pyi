"""V27 local declaration types; no scheduler, runtime, IPC or GPU implementation.

Numeric tuples contain finite values in the target's prepared units/frame. These
records describe the existing renderer/type-handler boundary, not a plugin framework.
See motion-composition.md for order, conflicts and the distinction from wire schemas.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class MotionTarget:
    instance_id: str
    state_field: str
    unit: str
    frame_id: str
    component_count: int

@dataclass(frozen=True)
class PreparedWriter:
    writer_id: str
    target: MotionTarget
    kind: Literal["programmed_rate", "feedback_increment", "absolute_trajectory", "direct_feedback"]
    definition_index: int  # Index into the immutable prepared epoch definitions.

@dataclass(frozen=True)
class PreparedTargetWriters:
    target: MotionTarget
    writers: tuple[PreparedWriter, ...]  # Validated for overlap and conflicts at Setup.

@dataclass(frozen=True)
class FeedbackReference:
    stream_id: str
    process_generation: str
    reset_generation: str
    result_id: str
    source_frame_id: str
    source_host_receipt_ns: int
    application_check_ns: int

@dataclass(frozen=True)
class MotionIncrement:
    target: MotionTarget
    writer_id: str
    logical_application_ns: int  # Trial-relative, current update under V24.
    source: Literal["programmed", "feedback"]
    delta: tuple[float, ...]
    feedback: FeedbackReference | None  # Present exactly for feedback increments.

@dataclass(frozen=True)
class AppliedMotion:
    increment: MotionIncrement
    before: tuple[float, ...]
    after: tuple[float, ...]  # Effective state, after type-specific constraints.
    constrained: bool

@dataclass
class RetainedMotionState:
    target: MotionTarget
    value: tuple[float, ...]  # One authoritative reached state, not one per source.
    programmed_anchor_trial_ns: int
    active: bool
