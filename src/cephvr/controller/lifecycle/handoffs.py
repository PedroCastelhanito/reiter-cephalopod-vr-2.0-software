"""Acquisition/tracking/VR Setup handoffs with exact attempt identity."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.lifecycle.evidence_wait import EvidenceWaiter
from cephvr.controller.lifecycle.preparation_context import PreparationContext
from cephvr.controller.preparation import PreparationError
from cephvr.controller.state import Attempt, LifecycleState
from cephvr.tracking.v1 import services_pb2 as tracking_svc


class PreparationHandoffs:
    """Dispatch and admit bounded preparation descriptors during SettingUp."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        preparation_context: PreparationContext,
        evidence_waiter: EvidenceWaiter,
        clock: Callable[[], int],
    ) -> None:
        self.lifecycle = lifecycle
        self.preparation_context = preparation_context
        self.evidence_waiter = evidence_waiter
        self.clock = clock

    async def complete_preparation_handoff(
        self, attempt: Attempt, deadline_ns: int
    ) -> None:
        handoff = attempt.handoff
        assert handoff is not None
        vr_sent = not handoff.closed_loop
        while True:
            async with self.lifecycle.lock:
                if (
                    self.lifecycle.attempt is not attempt
                    or attempt.cancel_requested
                    or self.lifecycle.session.phase != pb.SESSION_PHASE_SETTING_UP
                ):
                    raise RuntimeError("Setup handoff retired")
                action: str | None = None
                request: object | None = None
                if handoff.can_bind_input:
                    frames, tracking = handoff.frames, handoff.tracking
                    assert frames is not None and tracking is not None
                    command_id = str(uuid.uuid4())
                    handoff.input_binding_command = command_id
                    request = tracking_svc.TrackingDataBinding(
                        command=self.preparation_context.handoff_command(
                            attempt, "tracking", command_id
                        ),
                        configuration_revision=attempt.prepared.configuration_revision,
                        preparation_generation=tracking.preparation_generation,
                        frames=frames,
                    )
                    action = "bind"
                elif handoff.can_confirm_input:
                    evidence = handoff.reports["tracking"]
                    command_id = str(uuid.uuid4())
                    handoff.input_confirmation_command = command_id
                    request = svc.TrackingInputConfirmation(
                        command=self.preparation_context.handoff_command(
                            attempt, "acquisition", command_id
                        ),
                        configuration_revision=attempt.prepared.configuration_revision,
                        tracking_evidence=evidence,
                    )
                    action = "confirm"
                elif not vr_sent and handoff.can_prepare_vr:
                    request = self.preparation_context.setup_request(
                        attempt, attempt.required["vr"], attempt.setup_operations["vr"]
                    )
                    vr_sent = True
                    action = "vr"
                elif (
                    handoff.input_binding_command
                    and handoff.input_confirmation_command
                    and vr_sent
                ):
                    return
            if action is None:
                vr_pending = not vr_sent

                def actionable(pending: bool = vr_pending) -> bool:
                    return (
                        handoff.can_bind_input
                        or handoff.can_confirm_input
                        or (pending and handoff.can_prepare_vr)
                    )

                await self.evidence_waiter.wait_evidence(
                    actionable,
                    deadline_ns,
                    attempt,
                )
                continue
            remaining = max(0, (deadline_ns - self.clock()) / 1e9)
            if action == "bind":
                assert isinstance(request, tracking_svc.TrackingDataBinding)
                response = await asyncio.wait_for(
                    attempt.required["tracking"].bind_tracking_data(
                        request, deadline_ns=deadline_ns
                    ),
                    remaining,
                )
            elif action == "confirm":
                assert isinstance(request, svc.TrackingInputConfirmation)
                response = await asyncio.wait_for(
                    attempt.required["acquisition"].confirm_tracking_input(
                        request, deadline_ns=deadline_ns
                    ),
                    remaining,
                )
            else:
                assert isinstance(request, svc.SetupSessionRequest)
                response = await asyncio.wait_for(
                    attempt.required["vr"].setup_session(
                        request, deadline_ns=deadline_ns
                    ),
                    remaining,
                )
            if response.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(
                    f"{action} handoff rejected: {response.failure.message}"
                )

    async def report_data_preparation(
        self, report: svc.DataPreparationReport, ingress_ns: int
    ) -> pb.ReportReceipt:
        async with self.lifecycle.lock:
            attempt = self.lifecycle.attempt
            if (
                attempt is None
                or attempt.handoff is None
                or attempt.cancel_requested
                or self.lifecycle.session.phase != pb.SESSION_PHASE_SETTING_UP
                or ingress_ns > attempt.setup_deadline_ns
            ):
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(
                        code="STALE", message="no matching live Setup handoff"
                    ),
                )
            if "acquisition" in attempt.required and not attempt.resolution_confirmed:
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(
                        code="ORDER",
                        message="acquisition readback was not adopted before resource allocation",
                    ),
                )
            try:
                changed = attempt.handoff.accept(report)
            except (PreparationError, ValueError) as exc:
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(code="EVIDENCE", message=str(exc)),
                )
            if changed:
                attempt.changed.set()
            return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
