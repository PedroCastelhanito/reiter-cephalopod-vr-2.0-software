"""E13/V12 local timing declarations; no wire, storage or GPU binding.

Nanoseconds use E08 host_time_ns. Review-video frames carry no timestamps of their
own: frame n is the n-th admitted render group (encoding-options.md); real timing
lives in the V28 evidence lines.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class TrialClock:
    prepared_generation: str
    renderer_generation: str
    session_id: str
    trial_id: str
    trial_start_host_ns: int
    scheduled_end_host_ns: int  # Strictly greater than trial_start_host_ns.

@dataclass(frozen=True)
class RenderGroupTime:
    trial: TrialClock
    render_group_id: int  # Nonnegative, unique and increasing within this trial.
    state_evaluation_host_ns: int  # Exact shared state time, before per-output swaps.

@dataclass(frozen=True)
class RendererRecordingCutoff:
    trial: TrialClock
    cutoff_host_ns: int | None  # None means unknown; never substitute planned end.
    last_render_group_id: int | None  # None when no group was evaluated.
    admission_sealed: bool  # Independent of later draining or file closure.
