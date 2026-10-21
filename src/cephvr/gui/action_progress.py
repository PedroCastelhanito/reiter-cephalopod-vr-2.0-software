"""Action-only runtime log projection; controller evidence remains authoritative."""

from collections.abc import Callable
from typing import Any

from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.managed_status import action_label
from cephvr.gui.setup_checklist import SetupChecklist


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
        "submit_configuration": "Configuration · Applying settings…",
        "Start": "Session · Preparing to start…",
        "Stop after trial": "Session · Stopping after this trial…",
        "Cancel Setup": "Setup · Cancelling…",
        "Abort now": "Session · Stopping…",
        "spikeglx_connection": "SpikeGLX · Connecting…",
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

    def __init__(
        self,
        emit: Callable[[str, str], None],
        update: Callable[[str, tuple[str, ...], str, str, str], None] | None = None,
    ) -> None:
        self.emit = emit
        self.update = update
        self.checklist = SetupChecklist(self._update)
        self.setup_keys: set[tuple[str, ...]] = set()
        self.setup_session: str | None = None
        self.configuration = pb.ConfigurationValues()
        self.requests: dict[str, str] = {}
        self.identity: tuple[int, str] | None = None
        self.current: dict[tuple[str, ...], str] = {}

    def requested(self, action: str, message: str) -> None:
        if message:
            self.requests[action] = message
            self.publish(_target(action), ("request", action), message)

    def publish(
        self,
        target: str,
        key: tuple[str, ...],
        message: str,
        result: str = "",
        details: str = "",
    ) -> None:
        if key in self.setup_keys:
            if result:
                self.checklist.complete(key, result, details)
            elif message:
                self.checklist.progress(target, key, message)
            return
        self._update(target, key, message, result, details)

    def _update(
        self,
        target: str,
        key: tuple[str, ...],
        message: str,
        result: str = "",
        details: str = "",
    ) -> None:
        if self.update is not None:
            self.update(target, key, message, result, details)
        elif not result:
            self.emit(target, message)

    def finished(self, action: str, status: str, details: str = "") -> bool:
        message = self.requests.pop(action, "")
        if not message:
            return False
        result = (
            "Done" if status == "completed" else status.replace("_", " ").capitalize()
        )
        self.publish(_target(action), ("request", action), message, result, details)
        return True

    def install(self, epoch: int, state: pb.Snapshot) -> None:
        identity = (epoch, state.controller_generation)
        if identity != self.identity:
            self.checklist.unconfirmed()
            self.checklist = SetupChecklist(self._update)
            self.setup_keys.clear()
            self.setup_session = None
            self.configuration.Clear()
            self.current.clear()
            self.identity = identity
        if state.HasField("configuration_values"):
            self.configuration.CopyFrom(state.configuration_values)
        if state.session.phase == pb.SESSION_PHASE_SETTING_UP:
            session = state.session.context.session_id
            if self.setup_session != session:
                self.checklist.unconfirmed()
            self.setup_session = session
        final = state.last_finalization
        if (
            final.session.phase == pb.SESSION_PHASE_ENDED
            and final.session.cleanup_confirmed
            and final.session.context.controller_generation
            == state.controller_generation
        ):
            session_id = final.session.context.session_id
            for pending_key, message in list(self.current.items()):
                if pending_key[:2] not in {
                    ("session", session_id),
                    ("trial", session_id),
                }:
                    continue
                if (
                    pending_key[0] == "trial"
                    and pending_key[2] != final.trial.context.trial_id
                ):
                    continue
                result = (
                    "Interrupted"
                    if pending_key[0] == "trial"
                    and final.trial.outcome == pb.TRIAL_OUTCOME_INTERRUPTED
                    and not message.endswith("Finalizing files…")
                    else "Done"
                )
                self.publish("", pending_key, "", result, str(final))
                self.current.pop(pending_key)
        entries: dict[tuple[str, ...], tuple[str, str]] = {}
        session_id = state.session.context.session_id
        for operation in state.operations:
            key: tuple[str, ...] = ("operation", operation.context.command_id)
            if operation.command in {"Setup", "setup"}:
                self.setup_keys.add(key)
            if operation.complete and key in self.current:
                result = (
                    "Done"
                    if operation.HasField("succeeded") and operation.succeeded
                    else "Failed"
                    if operation.HasField("succeeded") or operation.HasField("failure")
                    else "Unconfirmed"
                )
                self.publish(
                    _target(operation.command), key, "", result, str(operation)
                )
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
            key = ("recovery", recovery.attempt_id)
            if recovery.HasField("completion_monotonic_ns") and key in self.current:
                result = {
                    pb.RECOVERY_OUTCOME_COMPLETED: "Done",
                    pb.RECOVERY_OUTCOME_FAILED: "Failed",
                }.get(recovery.outcome, "Unconfirmed")
                self.publish("", key, "", result, str(recovery))
            if recovery.HasField("completion_monotonic_ns") or not recovery.progress:
                continue
            entries[("recovery", recovery.attempt_id)] = (
                "",
                f"Recovery · {recovery.progress}",
            )
        phase = state.session.phase
        session_action = {
            pb.SESSION_PHASE_READY: "Setup complete; waiting for Start",
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
                "Shutdown · Releasing devices…",
            )
        trial = state.trial
        key = ("trial", trial.context.session.session_id, trial.context.trial_id)
        if trial.phase == pb.TRIAL_PHASE_ENDED and key in self.current:
            result = {
                pb.TRIAL_OUTCOME_COMPLETED: "Done",
                pb.TRIAL_OUTCOME_INTERRUPTED: "Interrupted",
            }.get(trial.outcome, "Unconfirmed")
            self.publish("", key, "", result, str(trial))
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
            entries[
                ("trial", trial.context.session.session_id, trial.context.trial_id)
            ] = (
                "",
                f"Trial {trial.context.trial_number} · {step}",
            )
        for participant in state.participants:
            name = participant.process.role
            if name not in {"acquisition", "visual_stimulus", "tracking"}:
                continue
            label = {
                "acquisition": "Cameras",
                "visual_stimulus": "Visual stimulus",
                "tracking": "Tracking",
            }[name]
            target = {"acquisition": "cameras", "visual_stimulus": "projectors"}.get(
                name, "tracking"
            )
            key = ("participant", session_id, name, participant.process.generation)
            if phase == pb.SESSION_PHASE_SETTING_UP or self.setup_session == session_id:
                self.setup_keys.add(key)
                self._camera_setup_rows(state, participant, key)
                if participant.ready.required_checks_passed and key not in self.current:
                    self.checklist.progress(
                        target, key, f"{label} · Preparing session resources…"
                    )
            if participant.ready.required_checks_passed:
                if key in self.current or key in self.checklist.rows:
                    self.publish(target, key, "", "Done")
                continue
            if phase != pb.SESSION_PHASE_SETTING_UP:
                continue
            entries[key] = (
                target,
                f"{label} · {participant.preparation_progress or 'Preparing session resources…'}",
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
        mcu_key = ("setup-mcu", session_id, mcu.observation.connection_id)
        if phase == pb.SESSION_PHASE_SETTING_UP and mcu.observation.connection_id:
            self.checklist.progress(
                "microcontroller",
                mcu_key,
                "Microcontroller · Reading connection and configuration…",
            )
            if mcu.failure:
                self.checklist.complete(mcu_key, "Failed", mcu.failure)
            elif mcu.observation.observed_monotonic_ns and not mcu.cleanup_pending:
                self.checklist.complete(mcu_key, "Done", str(mcu.observation))
        if (
            mcu.observation.connection_id
            and not mcu.cleanup_pending
            and not mcu.failure
            and phase != pb.SESSION_PHASE_SETTING_UP
            and (mcu.diagnostic.active or mcu_key not in self.checklist.finished)
        ):
            entries[("microcontroller", mcu.observation.connection_id)] = (
                "microcontroller",
                "Microcontroller · Testing pin…"
                if mcu.diagnostic.active
                else "Microcontroller · Connection and configuration observed",
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
                self.publish(target, key, message)
        if self.setup_session is not None and phase != pb.SESSION_PHASE_SETTING_UP:
            self.checklist.unconfirmed()
            self.setup_session = None
        self.current = {
            key: message for key, (_target_name, message) in entries.items()
        }

    def _camera_setup_rows(
        self, state: pb.Snapshot, participant: pb.ParticipantState, key: tuple[str, ...]
    ) -> None:
        if participant.process.role != "acquisition":
            return
        if self.configuration.revision != state.configuration.revision:
            return
        settings = next(
            (
                backend
                for backend in self.configuration.current.backends
                if backend.backend_name == "acquisition" and backend.enabled
            ),
            pb.BackendSettings(),
        )
        for role, label in (
            ("behavioral", "Behavior camera"),
            ("tracking", "Tracking camera"),
            ("eye_tracking", "Eye camera"),
        ):
            if getattr(settings.acquisition, role).enabled:
                self.checklist.progress(
                    "cameras", key, f"{label} · Preparing camera for session…"
                )
