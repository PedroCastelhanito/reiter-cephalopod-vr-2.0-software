"""One coordinator-owned source of Visual Stimulus lifecycle and retained artifact state."""

from __future__ import annotations

from dataclasses import dataclass, field

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.recording.recipe import PreparedRecipe
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus
from cephvr.visual_stimulus.v1 import runtime_pb2 as vp


@dataclass(frozen=True)
class Identity:
    process: pb.ProcessIdentity
    controller: pb.ProcessIdentity
    supervisor: pb.ProcessIdentity
    worker: pb.ProcessIdentity

    @property
    def backend(self) -> pb.BackendContext:
        return pb.BackendContext(
            backend_name="visual_stimulus", backend_generation=self.process.generation
        )


@dataclass
class Prepared:
    trial: pb.TrialContext
    data: bytes
    handle: vp.PreparedHandle
    recipe: PreparedRecipe
    plan: PreparedTrial


@dataclass
class CommandLink:
    method: str
    parent: wire.BackendCommand
    child: visual_stimulus.WorkerCommand
    deadline_ns: int


@dataclass
class State:
    setup: wire.SetupSessionRequest | None = None
    prepared: dict[str, Prepared] = field(default_factory=dict)
    links: dict[str, CommandLink] = field(default_factory=dict)
    reports: dict[tuple[str, str], pb.LifecycleReport] = field(default_factory=dict)
    display: pb.VisualStimulusDisplayView | None = None
    interrupted: bool = False
    sealed: bool = False
    catalogue_revision: int = 0
    resources: list[pb.ResourceObligation] = field(default_factory=list)
    worker_heartbeat: pb.HeartbeatReport | None = None
    worker_ingress_ns: int | None = None
    active_trial: str | None = None
    schedule: wire.ScheduleTrialRequest | None = None
    release: wire.ReleaseTrialRequest | None = None
    recipe_results: dict[str, pb.OutputResult] = field(default_factory=dict)
    cleanup: pb.CleanupReport | None = None
    incident_revisions: dict[str, int] = field(default_factory=dict)
