"""Session and trial-specific recording preparation (A07/A08)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cephvr.acquisition.recording.identity import RecordingIdentity
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu

if TYPE_CHECKING:
    from collections.abc import Callable

    from cephvr.acquisition.camera.basler import BaslerCameraAdapter

    from .capture_runtime import WorkerCaptureResources
    from .recording_runtime import WorkerRecordingRuntime
    from .state import WorkerBootstrap


@dataclass(frozen=True, slots=True)
class RecordingSessionIdentity:
    """Validated session identity retained for subsequent trial output plans."""

    session_id: str
    device_id: str
    session_config_reference: str
    camera_clock: camera.CameraClockDescriptor


class TrialRecordingPreparation:
    """Prepare the writer from exact camera, session, and trial evidence."""

    def __init__(
        self,
        bootstrap: WorkerBootstrap,
        adapter: BaslerCameraAdapter,
        captures: WorkerCaptureResources,
        runtime: WorkerRecordingRuntime | None,
        *,
        operation_deadline: Callable[[str], int],
        first_frame_observed: Callable[[int], None],
        warning_occurrence: Callable[
            [str, str | None, str | None, int, int | None], None
        ],
        capability_resource_released: Callable[[str, bool], None],
    ) -> None:
        self._bootstrap = bootstrap
        self._adapter = adapter
        self._captures = captures
        self._recording = runtime
        self._operation_deadline = operation_deadline
        self._first_frame_observed = first_frame_observed
        self._warning_occurrence = warning_occurrence
        self._capability_resource_released = capability_resource_released
        self._session: RecordingSessionIdentity | None = None

    def prepare_session(self, request: acq.WorkerSetupSession) -> None:
        payload = request.camera
        if not payload.HasField("recording"):
            self._session = None
            return
        runtime = self._recording
        if runtime is None:
            raise RuntimeError("recording was requested but runtime is unavailable")
        command = request.command
        if (
            not command.HasField("target")
            or not command.target.HasField("work")
            or command.target.work.WhichOneof("work") != "session"
            or not command.HasField("parent_operation")
            or not payload.HasField("camera_clock")
            or self._captures.layout is None
        ):
            raise ValueError("recording Setup lacks exact session or rate evidence")
        work = command.target.work
        settings = self._adapter.read_settings()
        if self._captures.requires_external_trigger:
            if not payload.HasField("pulse_configuration"):
                raise ValueError(
                    "external recording lacks confirmed applied pulse-rate evidence"
                )
            rate, source = self._applied_pulse_rate(
                payload.pulse_configuration, self._bootstrap.context.camera
            )
        else:
            candidate_rate = settings.frame_rate_hz
            if (
                candidate_rate is None
                or not math.isfinite(candidate_rate)
                or candidate_rate <= 0
            ):
                raise ValueError("free-running recording has no resolved frame rate")
            rate = candidate_rate
            source = "free_running_frame_rate"

        role = _camera_role_name(self._bootstrap.context.camera)
        self._session = RecordingSessionIdentity(
            work.session.session_id,
            payload.device.device_id,
            payload.recording.session_config_reference,
            camera.CameraClockDescriptor.FromString(
                payload.camera_clock.SerializeToString(deterministic=True)
            ),
        )
        runtime.prepare_session(
            payload.recording,
            payload.layout,
            self._captures.layout,
            work,
            command.parent_operation,
            session_id=self._session.session_id,
            device_id=self._session.device_id,
            camera_clock=payload.camera_clock,
            role=role,
            nominal_rate_hz=rate,
            nominal_rate_source=source,
            warning_occurrence=self._warning_occurrence,
            capability_resource_released=self._capability_resource_released,
            deadline_ns=self._operation_deadline(command.command_id),
        )

    def prepare_trial(self, request: acq.WorkerPrepareTrial, deadline_ns: int) -> None:
        runtime = self._recording
        if runtime is None or not runtime.enabled:
            return
        if not request.HasField("camera"):
            raise ValueError("recording trial preparation lacks camera output plans")
        session = self._session
        if session is None or self._captures.layout is None:
            raise ValueError(
                "trial recording preparation lacks confirmed session state"
            )
        work = request.command.target.work
        if work.WhichOneof("work") != "trial":
            raise ValueError("trial recording preparation lacks exact trial identity")
        trial = work.trial
        role = _camera_role_name(self._bootstrap.context.camera)
        identity = RecordingIdentity(
            trial.session.session_id,
            trial.trial_id,
            trial.trial_number,
            role,
            session.device_id,
            session.session_config_reference,
            session.camera_clock,
        )
        identity.validate()
        runtime.prepare_trial(
            tuple(request.camera.outputs),
            identity,
            deadline_ns,
            started_observed=self._first_frame_observed,
        )
        queue, pool = runtime.recording_queue, runtime.pixel_pool
        if queue is None or pool is None:
            raise RuntimeError("prepared recording buffers are unavailable")
        self._captures.install_recording(queue, pool)

    @staticmethod
    def _applied_pulse_rate(
        observation: mcu.MicrocontrollerObservation, camera_role: int
    ) -> tuple[float, str]:
        if (
            not observation.connection_id
            or not observation.request_id
            or not observation.HasField("observed_monotonic_ns")
            or observation.observed_monotonic_ns <= 0
            or not observation.HasField("state")
            or not observation.state.HasField("configuration_valid")
            or not observation.state.configuration_valid
        ):
            raise ValueError("external recording has no valid pulse configuration")
        role = _camera_role_name(camera_role)
        output = getattr(observation.state, role)
        if (
            not output.HasField("enabled")
            or not output.enabled
            or not output.HasField("running")
            or not output.running
            or not output.HasField("applied_frequency_hz")
            or not math.isfinite(output.applied_frequency_hz)
            or output.applied_frequency_hz <= 0
        ):
            raise ValueError("external recording pulse rate is not applied")
        return output.applied_frequency_hz, "applied_mcu_rate"


def _camera_role_name(value: int) -> str:
    name = camera.CameraRole.Name(value).lower()
    return name.removeprefix("camera_role_")
