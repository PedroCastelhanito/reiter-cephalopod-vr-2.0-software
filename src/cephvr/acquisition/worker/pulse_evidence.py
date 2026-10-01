"""Validate and retain exact MCU ON/OFF outcomes for one camera trial (A08)."""

from __future__ import annotations

from cephvr.acquisition.recording.session_contracts import PulseEvidence
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu

from .ports import command_from


class TrialPulseEvidence:
    """Keep the selected camera's immutable terminal ON/OFF evidence pair."""

    def __init__(self) -> None:
        self.required = False
        self.connection_id: str | None = None
        self.off_boundary_ns: int | None = None
        self.on: PulseEvidence | None = None
        self.off: PulseEvidence | None = None
        self._on_wire: bytes | None = None
        self._off_wire: bytes | None = None

    def reset(self, required: bool) -> None:
        self.required = required
        self.connection_id = None
        self.off_boundary_ns = None
        self.on = None
        self.off = None
        self._on_wire = None
        self._off_wire = None

    def record(
        self,
        request: object,
        schedule: acq.WorkerSchedule | None,
        camera_role: camera.CameraRole,
    ) -> None:
        if not isinstance(request, acq.WorkerPulseEvidence) or not request.HasField(
            "evidence"
        ):
            raise ValueError("pulse evidence is missing")
        if request.camera != camera_role:
            raise ValueError("pulse evidence names another camera role")
        command = command_from(request)
        if (
            schedule is None
            or not command.target.HasField("work")
            or not schedule.command.target.HasField("work")
            or command.target.work.SerializeToString(deterministic=True)
            != schedule.command.target.work.SerializeToString(deterministic=True)
        ):
            raise ValueError("pulse evidence differs from the exact scheduled trial")
        pulse = request.evidence
        selected = (
            pulse.behavioral_selected
            if camera_role == camera.CAMERA_ROLE_BEHAVIORAL
            else pulse.tracking_selected
        )
        if (
            not pulse.connection_id
            or pulse.outcome == mcu.PULSE_COMMAND_OUTCOME_UNSPECIFIED
            or selected is not True
        ):
            raise ValueError("pulse evidence lacks exact selected terminal outcome")
        if pulse.outcome == mcu.PULSE_COMMAND_OUTCOME_NOT_DISPATCHED:
            if (
                pulse.HasField("dispatched_monotonic_ns")
                or pulse.HasField("acknowledged_monotonic_ns")
                or pulse.HasField("applied")
            ):
                raise ValueError(
                    "not-dispatched pulse evidence contains execution proof"
                )
        elif not pulse.request_id:
            raise ValueError("dispatched pulse evidence lacks its request identity")
        if pulse.outcome == mcu.PULSE_COMMAND_OUTCOME_APPLIED:
            if (
                not pulse.HasField("applied")
                or not pulse.applied
                or not pulse.HasField("dispatched_monotonic_ns")
                or not pulse.HasField("acknowledged_monotonic_ns")
            ):
                raise ValueError("applied pulse evidence lacks complete host proof")
        elif pulse.HasField("applied") and pulse.applied:
            raise ValueError("failed pulse outcome claims application")
        if pulse.HasField("acknowledged_monotonic_ns") and not pulse.HasField(
            "dispatched_monotonic_ns"
        ):
            raise ValueError("pulse ACK has no dispatch attempt")
        if (
            pulse.HasField("dispatched_monotonic_ns")
            and pulse.HasField("acknowledged_monotonic_ns")
            and pulse.acknowledged_monotonic_ns < pulse.dispatched_monotonic_ns
        ):
            raise ValueError("pulse ACK precedes dispatch")
        if self.connection_id is not None and self.connection_id != pulse.connection_id:
            raise ValueError("pulse evidence changed MCU connection within a trial")
        outcome = mcu.PulseCommandOutcome.Name(pulse.outcome)
        off_boundary: int | None = None
        if pulse.command == mcu.PULSE_BOUNDARY_COMMAND_ON:
            if (
                not pulse.HasField("scheduled_boundary_monotonic_ns")
                or pulse.scheduled_boundary_monotonic_ns != schedule.start_monotonic_ns
                or pulse.HasField("stop_issued_monotonic_ns")
            ):
                raise ValueError("ON pulse evidence differs from scheduled T")
            value = PulseEvidence(
                on_outcome=outcome,
                on_dispatched_monotonic_ns=_optional_time(
                    pulse, "dispatched_monotonic_ns"
                ),
                on_acknowledged_monotonic_ns=_optional_time(
                    pulse, "acknowledged_monotonic_ns"
                ),
                required=self.required,
            )
        elif pulse.command == mcu.PULSE_BOUNDARY_COMMAND_OFF:
            if pulse.HasField("stop_issued_monotonic_ns"):
                if pulse.HasField("scheduled_boundary_monotonic_ns"):
                    raise ValueError("interruption OFF has a scheduled boundary")
                off_boundary = pulse.stop_issued_monotonic_ns
            else:
                if (
                    not pulse.HasField("scheduled_boundary_monotonic_ns")
                    or pulse.scheduled_boundary_monotonic_ns
                    != schedule.end_monotonic_ns
                ):
                    raise ValueError("normal OFF differs from scheduled end")
                off_boundary = _optional_time(pulse, "dispatched_monotonic_ns")
            value = PulseEvidence(
                off_outcome=outcome,
                off_dispatched_monotonic_ns=_optional_time(
                    pulse, "dispatched_monotonic_ns"
                ),
                off_acknowledged_monotonic_ns=_optional_time(
                    pulse, "acknowledged_monotonic_ns"
                ),
                required=self.required,
            )
        else:
            raise ValueError("pulse boundary command is unspecified")
        encoded = request.SerializeToString(deterministic=True)
        prior = (
            self._on_wire
            if pulse.command == mcu.PULSE_BOUNDARY_COMMAND_ON
            else self._off_wire
        )
        if prior is not None:
            if prior != encoded:
                raise ValueError("terminal pulse evidence changed after retention")
            return
        self.connection_id = pulse.connection_id
        if pulse.command == mcu.PULSE_BOUNDARY_COMMAND_ON:
            self.on = value
            self._on_wire = encoded
        else:
            self.off = value
            self.off_boundary_ns = off_boundary
            self._off_wire = encoded

    def combined(self) -> PulseEvidence:
        on, off = self.on, self.off
        return PulseEvidence(
            on_outcome=on.on_outcome if on else None,
            on_dispatched_monotonic_ns=on.on_dispatched_monotonic_ns if on else None,
            on_acknowledged_monotonic_ns=(
                on.on_acknowledged_monotonic_ns if on else None
            ),
            off_outcome=off.off_outcome if off else None,
            off_dispatched_monotonic_ns=off.off_dispatched_monotonic_ns
            if off
            else None,
            off_acknowledged_monotonic_ns=(
                off.off_acknowledged_monotonic_ns if off else None
            ),
            required=self.required,
        )


def _optional_time(pulse: mcu.PulseCommandEvidence, field: str) -> int | None:
    return getattr(pulse, field) if pulse.HasField(field) else None
