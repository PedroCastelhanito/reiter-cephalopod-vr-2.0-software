"""Dashboard projection and placement intents for the renderer-owned review window."""

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QWidget

from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.view import PreviewView


def stimulus_preview_view(state: pb.Snapshot, pending: bool = False) -> PreviewView:
    view = state.stimulus_preview
    active = any(
        b.backend_name == "visual_stimulus" and b.enabled
        for b in state.configuration_values.current.backends
    )
    participant = next(
        (p for p in state.participants if p.process.role == "visual_stimulus"), None
    )
    current = bool(
        participant is not None
        and participant.connected
        and participant.process_running
        and participant.process.generation == view.backend.backend_generation
        and view.session == state.session.context
        and view.configuration_revision == state.configuration.revision
    )
    available = (
        current
        and view.available
        and state.session.phase
        in (pb.SESSION_PHASE_READY, pb.SESSION_PHASE_STARTING, pb.SESSION_PHASE_RUNNING)
    )
    return PreviewView(
        "stimulus",
        "Visual stimulus",
        active=active,
        available=available,
        visible=current and view.visible,
        source_fps=view.rates.source_fps
        if current and view.rates.HasField("source_fps")
        else None,
        preview_fps=view.rates.preview_fps
        if current and view.rates.HasField("preview_fps")
        else None,
        rates_observed_ns=view.rates.observed_monotonic_ns if current else 0,
        pending=pending,
        reason=view.failure
        if current and view.failure
        else ""
        if available
        else "Available after Setup",
    )


class ManagedStimulusPreview:
    def __init__(
        self,
        parent: QWidget,
        snapshot: Callable[[], pb.Snapshot | None],
        send: Callable[..., bool],
        placement: Callable[[], bytes],
        allowed: Callable[[], bool],
    ) -> None:
        self.snapshot, self.send, self.placement, self.allowed = (
            snapshot,
            send,
            placement,
            allowed,
        )
        self.pending = False
        self.last_layout: tuple[str, bytes] | None = None
        self.timer = QTimer(parent)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.relayout)
        self.timer.start()

    def request(
        self, key: str, visible: bool, *, snap: bool = False, update: bool = False
    ) -> None:
        state = self.snapshot()
        if key != "stimulus" or state is None or self.pending or not self.allowed():
            return
        view = stimulus_preview_view(state)
        if not view.active or not view.available:
            return
        try:
            hint = (
                rpc.PreviewWindowPlacement.FromString(self.placement())
                if visible
                else rpc.PreviewWindowPlacement()
            )
        except (ValueError, RuntimeError):
            return
        hint.update_existing_only = update
        hint.snap_to_grid = snap
        payload = hint.SerializeToString()
        if self.send(
            "set_stimulus_preview",
            visible=visible,
            placement=payload,
            expected_revision=state.configuration.revision,
            session_id=state.session.context.session_id,
        ):
            self.pending = True
            self.last_layout = (
                (state.session.context.session_id, payload) if visible else None
            )

    def relayout(self) -> None:
        state = self.snapshot()
        if (
            state is None
            or not stimulus_preview_view(state).visible
            or self.pending
            or not self.allowed()
        ):
            return
        try:
            hint = rpc.PreviewWindowPlacement.FromString(self.placement())
            hint.update_existing_only = True
            if self.last_layout != (
                state.session.context.session_id,
                hint.SerializeToString(),
            ):
                self.request("stimulus", True, update=True)
        except (ValueError, RuntimeError):
            return

    def finished(self, action: str, *_: Any) -> None:
        if action == "set_stimulus_preview":
            self.pending = False

    def disconnected(self) -> None:
        self.pending = False
        self.last_layout = None
