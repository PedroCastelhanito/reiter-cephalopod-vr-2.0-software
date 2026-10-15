"""Leased live diagnostic updates without replacing protected display resources."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.device.ports import DeviceHooks
from cephvr.controller.ports import BackendPort
from cephvr.controller.projections import ProjectionStore
from cephvr.controller.state import (
    ConfigurationState,
    DeviceState,
    LifecycleState,
    LimitsState,
)
from cephvr.shared.deadlines import remaining_seconds
from cephvr.visual_stimulus.config.calibration_adjustments import (
    LIVE_ADJUSTABLE_VIEWS,
    validated_update,
)
from cephvr.visual_stimulus.v1 import runtime_pb2 as vp


async def update_calibration(
    request: svc.UpdateDisplayCalibrationRequest,
    *,
    lifecycle: LifecycleState,
    configuration: ConfigurationState,
    device: DeviceState,
    projections: ProjectionStore,
    backend: BackendPort | None,
    generation: str,
    limits: LimitsState,
    hooks: DeviceHooks,
    clock: Callable[[], int],
    dispatch_lock: asyncio.Lock,
    track: Callable[[asyncio.Task[pb.CommandAdmission]], None],
    failed: Callable[[str, str], Awaitable[None]],
    expire: Callable[[str, int], Coroutine[Any, Any, None]],
) -> pb.CommandAdmission:
    command_id = request.command.operator.command_id
    async with lifecycle.lock:
        error = hooks.authorized(request.command)
        if error:
            return hooks.admission(command_id, error=error)
        view = projections.display
        evidence = (
            view.calibration
            if view is not None and view.HasField("calibration")
            else None
        )
        if (
            request.expected_configuration_revision != configuration.revision
            or lifecycle.session.phase != pb.SESSION_PHASE_CONFIGURATION
            or lifecycle.session.shutdown_requested
            or lifecycle.attempt is not None
            or device.calibration_pending is not None
            or backend is None
            or view is None
            or view.backend != backend.context
            or evidence is None
            or evidence.state != vp.DISPLAY_CALIBRATION_STATE_ACTIVE
            or evidence.calibration_view not in LIVE_ADJUSTABLE_VIEWS
            or evidence.diagnostic_id != request.diagnostic_id
            or evidence.configuration_revision != configuration.revision
            or evidence.controller_generation != generation
            or request.adjustment_sequence <= evidence.adjustment_sequence
        ):
            return hooks.admission(
                command_id, error="Live calibration targets a stale or unavailable grid"
            )
        try:
            validated_update(
                evidence.calibration_view,
                (
                    (item.mapping_id, item.destination_xy)
                    for item in request.adjustments
                ),
                request.placement_json,
            )
        except ValueError as exc:
            return hooks.admission(command_id, error=str(exc))
        assert view is not None
        deadline = clock() + limits.current.setup_ns + limits.current.recovery_ns
        dispatch = svc.VisualStimulusDisplayCalibrationUpdateRequest(
            command_id=command_id,
            issuer=pb.ProcessIdentity(role="controller", generation=generation),
            target=backend.context,
            configuration_revision=configuration.revision,
            diagnostic_id=request.diagnostic_id,
            deadline_monotonic_ns=deadline,
            adjustment_sequence=request.adjustment_sequence,
            adjustments=request.adjustments,
            placement_json=request.placement_json,
        )
        try:
            await asyncio.wait_for(
                dispatch_lock.acquire(), remaining_seconds(deadline, clock=clock)
            )
        except TimeoutError:
            return hooks.admission(
                command_id, error="Live calibration dispatch deadline expired"
            )
        try:
            hooks.operation(
                command_id,
                "UpdateDisplayCalibration",
                progress="grid presentation pending",
            )
        except RuntimeError as exc:
            dispatch_lock.release()
            return hooks.admission(command_id, error=str(exc))
        device.calibration_blocked = True
        device.calibration_pending = (
            command_id,
            configuration.revision,
            deadline,
            request.diagnostic_id,
            vp.DISPLAY_CALIBRATION_STATE_ACTIVE,
            frozenset(item.output_id for item in view.outputs),
        )
        projections.expect_display(command_id, configuration.revision)
        hooks.publish()
    try:
        task = asyncio.create_task(
            backend.update_display_calibration(dispatch, deadline_ns=deadline)
        )
        track(task)
        await asyncio.sleep(0)
    finally:
        dispatch_lock.release()
    try:
        reply = await asyncio.wait_for(
            asyncio.shield(task), remaining_seconds(deadline, clock=clock)
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        await failed(command_id, str(exc))
        return hooks.admission(command_id, error=str(exc))
    if reply.result != pb.COMMAND_RESULT_ACCEPTED:
        message = reply.failure.message or "Renderer rejected live calibration"
        await failed(command_id, message)
        return hooks.admission(command_id, error=message)
    hooks.spawn(expire(command_id, deadline))
    return hooks.admission(command_id)
