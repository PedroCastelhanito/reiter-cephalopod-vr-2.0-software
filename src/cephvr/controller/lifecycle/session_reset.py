"""Retire confirmed terminal session state without changing reusable settings."""

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.projections import ProjectionStore
from cephvr.controller.state import ConfigurationState, LifecycleState, MetadataState


class SessionReset:
    def __init__(
        self,
        lifecycle: LifecycleState,
        configuration: ConfigurationState,
        metadata: MetadataState,
        projections: ProjectionStore,
    ) -> None:
        self.lifecycle = lifecycle
        self.configuration = configuration
        self.metadata = metadata
        self.projections = projections

    def interrupted(self) -> None:
        """Return a safely closed interruption to Configuration; lock held."""
        session = self.lifecycle.session
        if (
            session.phase == pb.SESSION_PHASE_ENDED
            and session.outcome == pb.SESSION_OUTCOME_INTERRUPTED
            and session.cleanup_confirmed
            and not session.shutdown_requested
            and not self.lifecycle.shutdown_intent_ns
            and not self.lifecycle.authority_lost
        ):
            self.reset()

    def reset(self) -> None:
        """Caller holds lifecycle lock and has verified terminal cleanup."""
        if self.lifecycle.session.phase == pb.SESSION_PHASE_ENDED:
            self.lifecycle.last_finalization = pb.SessionFinalization(
                session=self.lifecycle.session, trial=self.lifecycle.trial
            )
        if self.projections.devices is not None:
            for role in ("behavioral", "tracking", "eye_tracking"):
                view = getattr(self.projections.devices, role)
                if view.preview_run_id == self.lifecycle.session.context.session_id:
                    view.device_open = False
                    view.preview_prepared = False
                    view.preview_running = False
                    view.preview_visible = False
                    view.cleanup_pending = False
                    view.preview_run_id = ""
        self.lifecycle.attempt = None
        self.lifecycle.session = pb.SessionState(
            phase=pb.SESSION_PHASE_CONFIGURATION, cleanup_confirmed=True
        )
        self.lifecycle.trial = pb.TrialState(phase=pb.TRIAL_PHASE_PENDING)
        self.projections.set_scope(pb.WorkContext(), self.configuration.revision)
        self.metadata.results.clear()
        self.metadata.latest_synced.clear()
