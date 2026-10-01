"""Graphics-thread-owned preparation and trial state; transport owns no GPU state."""

from concurrent.futures import Future
from dataclasses import dataclass, field

from cephvr.control.v1 import types_pb2 as pb
from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus
from cephvr.visual_stimulus.v1 import runtime_pb2 as vp

from .timing import OutputTiming


@dataclass(frozen=True)
class TrialArtifact:
    artifact: PreparedTrial
    data: bytes
    handle: vp.PreparedHandle


@dataclass
class Trial:
    prepared: visual_stimulus.WorkerPrepareTrial
    artifact: TrialArtifact
    schedule: visual_stimulus.WorkerSchedule | None = None
    release: visual_stimulus.WorkerRelease | None = None
    begun: bool = False
    started: bool = False
    stopped: bool = False
    finished: bool = False
    recording_finish_started: bool = False
    cutoff_ns: int | None = None
    groups: int = 0
    activities: dict[str, pb.ActivityEvidence] = field(default_factory=dict)
    outputs: tuple[pb.OutputResult, ...] = ()
    finish_deadline_ns: int | None = None
    stop_command: visual_stimulus.WorkerCommand | None = None
    schedule_completion: Future[None] | None = None
    timing: dict[str, OutputTiming] = field(default_factory=dict)


@dataclass
class DriverState:
    setup: visual_stimulus.WorkerSetup | None = None
    artifacts: dict[str, TrialArtifact] = field(default_factory=dict)
    trial: Trial | None = None
    resources: dict[str, pb.ResourceObligation] = field(default_factory=dict)
    catalogue_revision: int = 0
    interrupted: bool = False
    ready: bool = False
    display_ready: bool = False
    cleaned: bool = False
    failure_deadline_ns: int | None = None
    released_threads: set[str] = field(default_factory=set)
    outputs: dict[str, pb.OutputResult] = field(default_factory=dict)
