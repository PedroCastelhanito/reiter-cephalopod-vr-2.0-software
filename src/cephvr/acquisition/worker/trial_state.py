"""Authoritative mutable facts for one serialized camera trial (A08/A09)."""

from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass, field

from cephvr.acquisition.buffers.end_marker import CaptureEndMarker
from cephvr.acquisition.camera.types import PurgeEvidence, TransportCounters
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control

from .pulse_evidence import TrialPulseEvidence


@dataclass(slots=True)
class WorkerTrialState:
    """Single owner record for schedule, cutoff, terminal evidence and outputs."""

    prepared: bool = False
    schedule: acq.WorkerSchedule | None = None
    stopped_schedule: acq.WorkerSchedule | None = None
    released: bool = False
    end_marker: CaptureEndMarker | None = None
    purge_evidence: PurgeEvidence | None = None
    pulses: TrialPulseEvidence = field(default_factory=TrialPulseEvidence)
    finished_future: Future[list[control.OutputResult]] | None = None
    stop_request: acq.WorkerStop | acq.WorkerInterrupt | None = None
    finish_deadline_ns: int | None = None
    transport_start: TransportCounters | None = None
    transport_summary: dict[str, int | None] | None = None
    transport_observed_ns: int | None = None
    camera_first_frame_seen: bool = False
