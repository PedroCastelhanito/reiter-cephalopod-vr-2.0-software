"""Continuous camera pulse ownership and exact session-scope stop evidence."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from cephvr.acquisition.coordinator.commands import (
    retain_worker_command,
    wait_child_operation,
)
from cephvr.acquisition.identity import camera_role_name
from cephvr.acquisition.state import SessionRecord, WorkerRecord
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import types_pb2 as control


def capture_output_roles(session: SessionRecord) -> tuple[int, ...]:
    settings = session.confirmed_settings
    if settings is None:
        raise RuntimeError("continuous capture requires confirmed camera settings")
    return tuple(
        role
        for role in sorted(session.required_cameras)
        if getattr(settings, camera_role_name(role)).device.frame_timing
        == camera.FRAME_TIMING_EXTERNAL_TRIGGER
    )


def session_output_roles(session: SessionRecord) -> tuple[int | str, ...]:
    if session.confirmed_settings is None:
        # Failed Setup still needs safety OFF before camera settings were adopted.
        return (
            camera.CAMERA_ROLE_BEHAVIORAL,
            camera.CAMERA_ROLE_TRACKING,
            camera.CAMERA_ROLE_EYE_TRACKING,
            "trial_state",
        )
    roles: tuple[int | str, ...] = capture_output_roles(session)
    if (
        session.confirmed_settings is not None
        and session.confirmed_settings.pulses.trial_state_enabled
    ):
        roles += ("trial_state",)
    return roles


def capture_outputs_running(
    session: SessionRecord, state: mcu.MicrocontrollerState
) -> bool:
    return all(
        state.HasField(camera_role_name(role))
        and getattr(state, camera_role_name(role)).HasField("running")
        and getattr(state, camera_role_name(role)).running
        for role in capture_output_roles(session)
    )


def session_off_failure(
    roles: tuple[int | str, ...],
    connection_id: str,
    issued_ns: int,
    outcome: mcu.PulseCommandOutcome,
) -> mcu.PulseCommandEvidence:
    """Retain a failed host attempt without inventing serial dispatch or ACK proof."""
    return mcu.PulseCommandEvidence(
        connection_id=connection_id,
        command=mcu.PULSE_BOUNDARY_COMMAND_OFF,
        behavioral_selected=camera.CAMERA_ROLE_BEHAVIORAL in roles,
        tracking_selected=camera.CAMERA_ROLE_TRACKING in roles,
        eye_tracking_selected=camera.CAMERA_ROLE_EYE_TRACKING in roles,
        trial_state_selected="trial_state" in roles,
        stop_issued_monotonic_ns=issued_ns,
        outcome=outcome,
    )


async def deliver_session_pulse_evidence(
    session: SessionRecord,
    workers: dict[int, WorkerRecord],
    evidence: mcu.PulseCommandEvidence,
    *,
    deadline_ns: int,
    lock: asyncio.Lock,
    clock: Callable[[], int],
) -> None:
    """Await retained worker admission before safety cleanup can overtake the proof."""

    async def deliver(role: int) -> None:
        worker = workers.get(role)
        if worker is None or worker.setup_operation is None:
            return  # No session capture can exist before worker Setup was dispatched.
        if worker.port is None:
            raise RuntimeError("armed camera worker endpoint is unavailable")
        if worker.context.work != session.work:
            raise RuntimeError("session pulse evidence targets another worker session")
        command, operation, port = retain_worker_command(
            worker,
            work=session.work,
            parent_operation=session.operation,
            kind="record_pulse_evidence",
            deadline_ns=deadline_ns,
            configuration_revision=session.configuration_revision,
        )
        receipt = await port.record_pulse_evidence(
            acq.WorkerPulseEvidence(
                command=command, camera=worker.context.camera, evidence=evidence
            ),
            deadline_ns=deadline_ns,
        )
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError("worker rejected session pulse-stop evidence")
        result = await wait_child_operation(operation, deadline_ns, lock, clock)
        if not result.succeeded:
            raise RuntimeError("worker could not retain session pulse-stop evidence")

    outcomes = await asyncio.gather(
        *(
            deliver(role)
            for role in sorted(session.required_cameras)
            if getattr(evidence, camera_role_name(role) + "_selected")
        ),
        return_exceptions=True,
    )
    failures = [str(item) for item in outcomes if isinstance(item, BaseException)]
    if failures:
        raise RuntimeError(
            "session pulse evidence delivery failed: " + "; ".join(failures)
        )
