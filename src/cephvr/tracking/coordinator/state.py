"""Retained Tracking lifecycle facts, independent of native method owners."""

from __future__ import annotations

from dataclasses import dataclass, field

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.tracking.v1.preparation_pb2 import TrackingPreparationState


@dataclass(frozen=True)
class Identity:
    process: pb.ProcessIdentity
    controller: pb.ProcessIdentity
    supervisor: pb.ProcessIdentity

    @property
    def backend(self) -> pb.BackendContext:
        return pb.BackendContext(
            backend_name="tracking", backend_generation=self.process.generation
        )


@dataclass
class State:
    setup: wire.SetupSessionRequest | None = None
    preparation: TrackingPreparationState = field(
        default_factory=TrackingPreparationState
    )
    preparation_report: wire.DataPreparationReport | None = None
    frames_digest: bytes | None = None
    trial: wire.PrepareTrialRequest | None = None
    schedule: wire.ScheduleTrialRequest | None = None
    release: wire.ReleaseTrialRequest | None = None
    ready: pb.ReadyReport | None = None
    started: pb.StartedReport | None = None
    stopped: pb.StoppedReport | None = None
    finished: pb.FinishedReport | None = None
    cleanup: pb.CleanupReport | None = None
    error: pb.ErrorReport | None = None
    resources: list[pb.ResourceObligation] = field(default_factory=list)
    resource_revision: int = 0
    outputs: list[pb.OutputResult] = field(default_factory=list)
    retained: dict[str, pb.LifecycleReport] = field(default_factory=dict)
    incident_revisions: dict[str, int] = field(default_factory=dict)
    interrupted: bool = False
    cutoff: int | None = None
    session_phase: pb.SessionPhase = pb.SESSION_PHASE_CONFIGURATION
    trial_phase: pb.TrialPhase = pb.TRIAL_PHASE_PENDING

    def work(self) -> pb.WorkContext:
        if self.trial is not None:
            return pb.WorkContext(trial=self.trial.plan.context)
        return (
            pb.WorkContext()
            if self.setup is None
            else pb.WorkContext(session=self.setup.plan.context)
        )
