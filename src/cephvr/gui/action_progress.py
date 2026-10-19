"""Action-only runtime log projection; controller evidence remains authoritative."""

from collections.abc import Callable
from typing import Any

from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.managed_status import action_label


def requested_action(action: str, options: dict[str, Any]) -> str:
    """Describe dispatched work, excluding background polls and routine edits."""
    if action in {"camera", "prepare_camera"}:
        role = options.get("camera_role", options.get("role", 0))
        label = {1: "Behavior camera", 2: "Tracking camera", 3: "Eye camera"}.get(
            role, "Camera"
        )
        step = {
            rpc.CAMERA_COMMAND_KIND_START_PREVIEW: "Connecting…",
            rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW: "Disconnecting…",
            rpc.CAMERA_COMMAND_KIND_FINISH_EDITING: "Releasing camera…",
            rpc.CAMERA_COMMAND_KIND_TEST_CONNECTION: "Checking camera identity…",
        }.get(options.get("kind", 0), "")
        return f"{label} · {step}" if step else ""
    if action in {"mcu", "prepare_mcu_connection", "prepare_mcu_test"}:
        step = {
            rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT: "Opening port…",
            rpc.MICROCONTROLLER_COMMAND_KIND_START: "Preparing pin test…",
            rpc.MICROCONTROLLER_COMMAND_KIND_STOP: "Stopping pin test…",
            rpc.MICROCONTROLLER_COMMAND_KIND_DISCONNECT: "Releasing port…",
        }.get(options.get("kind", 0), "")
        return f"Microcontroller · {step}" if step else ""
    return {
        "Setup": "Setup · Validating configuration…",
        "submit_configuration": "Configuration · Applying current settings…",
        "Start": "Session · Preparing to start…",
        "Stop after trial": "Session · Waiting for current trial to finish…",
        "Cancel Setup": "Setup · Cancelling preparation…",
        "Abort now": "Session · Stopping active work…",
        "spikeglx_connection": "SpikeGLX · Connecting…",
        "get_spikeglx_inventory": "SpikeGLX · Reading device inventory…",
        "mcu_upload": "Microcontroller · Preparing firmware upload…",
        "begin_tracking_diagnostic": "Tracking · Preparing pipeline…",
        "close_tracking_diagnostic": "Tracking · Releasing pipeline…",
        "open_display_calibration": "Visual stimulus · Preparing projector outputs…",
        "close_display_calibration": "Visual stimulus · Restoring idle output…",
        "save_configuration_history": "Shutdown · Saving configuration…",
    }.get(action, "")


def _target(command: str) -> str:
    if "Camera" in command or command in {"camera", "prepare_camera"}:
        return "cameras"
    if "Microcontroller" in command or command in {
        "mcu",
        "prepare_mcu_connection",
        "prepare_mcu_test",
        "mcu_upload",
    }:
        return "microcontroller"
    if "SpikeGLX" in command or "spikeglx" in command:
        return "spikeglx"
    if "Display" in command or "display" in command:
        return "projectors"
    if "Tracking" in command or "tracking" in command:
        return "tracking"
    return ""


class ActionProgress:
    """Emit changes once per current scope without replaying old successes."""

    def __init__(self, emit: Callable[[str, str], None]) -> None:
        self.emit = emit
        self.identity: tuple[int, str] | None = None
        self.current: dict[tuple[str, ...], str] = {}

    def requested(self, action: str, message: str) -> None:
        if message:
            self.emit(_target(action), message)

    def install(self, epoch: int, state: pb.Snapshot) -> None:
        identity = (epoch, state.controller_generation)
        if identity != self.identity:
            self.current.clear()
            self.identity = identity
        entries: dict[tuple[str, ...], tuple[str, str]] = {}
        session_id = state.session.context.session_id
        for operation in state.operations:
            if (
                operation.complete
                or not operation.progress
                or operation.progress
                in {
                    "accepted",
                    "acquisition command pending",
                    "controller Microcontroller command pending",
                }
            ):
                continue
            entries[("operation", operation.context.command_id)] = (
                _target(operation.command),
                operation.progress
                if " · " in operation.progress
                else f"{action_label(operation.command)} · {operation.progress}",
            )
        for recovery in state.recoveries:
            if recovery.HasField("completion_monotonic_ns") or not recovery.progress:
                continue
            entries[("recovery", recovery.attempt_id)] = (
                "",
                f"Recovery · {recovery.progress}",
            )
        phase = state.session.phase
        session_action = {
            pb.SESSION_PHASE_READY: "Ready",
            pb.SESSION_PHASE_STARTING: "Preparing to start…",
            pb.SESSION_PHASE_FINALIZING: "Finalizing session…",
        }.get(phase, "")
        if phase == pb.SESSION_PHASE_ENDED and state.session.cleanup_confirmed:
            session_action = "Idle"
        if session_action:
            entries[("session", session_id)] = ("", f"Session · {session_action}")
        if state.session.shutdown_requested:
            entries[("shutdown",)] = (
                "",
                "Shutdown · Stopping backends and releasing devices…",
            )
        trial = state.trial
        step = {
            pb.TRIAL_PHASE_PREPARING: "Preparing recording…",
            pb.TRIAL_PHASE_READY: "Waiting to start…",
            pb.TRIAL_PHASE_STARTING: "Starting recording…",
            pb.TRIAL_PHASE_RUNNING: "Recording",
            pb.TRIAL_PHASE_FINALIZING: "Finalizing files…",
        }.get(trial.phase, "")
        if (
            trial.context.trial_id
            and step
            and phase in {pb.SESSION_PHASE_RUNNING, pb.SESSION_PHASE_FINALIZING}
        ):
            entries[("trial", trial.context.trial_id)] = (
                "",
                f"Trial {trial.context.trial_number} · {step}",
            )
        for participant in state.participants:
            if phase != pb.SESSION_PHASE_SETTING_UP:
                continue
            name = participant.process.role
            if name not in {"acquisition", "visual_stimulus", "tracking"}:
                continue
            if participant.ready.required_checks_passed:
                continue
            label = {
                "acquisition": "Cameras",
                "visual_stimulus": "Visual stimulus",
                "tracking": "Tracking",
            }[name]
            target = {"acquisition": "cameras", "visual_stimulus": "projectors"}.get(
                name, "tracking"
            )
            entries[
                ("participant", session_id, name, participant.process.generation)
            ] = (
                target,
                f"{label} · {participant.preparation_progress or 'Preparing…'}",
            )
        for name, label in (
            ("behavioral", "Behavior camera"),
            ("tracking", "Tracking camera"),
            ("eye_tracking", "Eye camera"),
        ):
            device = getattr(state.acquisition_devices, name)
            if device.preview_running and not device.cleanup_pending:
                entries[("camera", name, device.preview_run_id)] = (
                    "cameras",
                    f"{label} · Live",
                )
        mcu = state.microcontroller
        if (
            mcu.observation.connection_id
            and not mcu.cleanup_pending
            and not mcu.failure
        ):
            entries[("microcontroller", mcu.observation.connection_id)] = (
                "microcontroller",
                "Microcontroller · Testing pin…"
                if mcu.diagnostic.active
                else "Microcontroller · Ready",
            )
        diagnostic = state.tracking_diagnostic
        if diagnostic.active and not diagnostic.failure:
            entries[("tracking", diagnostic.diagnostic_id)] = (
                "tracking",
                "Tracking · Processing frames"
                if diagnostic.evaluated_frames
                else "Tracking · Waiting for frames…",
            )
        for key, (target, message) in entries.items():
            if self.current.get(key) != message:
                self.emit(target, message)
        self.current = {
            key: message for key, (_target_name, message) in entries.items()
        }
