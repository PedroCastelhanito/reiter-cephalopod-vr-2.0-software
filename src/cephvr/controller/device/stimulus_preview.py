"""Lease-authorized display-only preview commands and renderer-attested visibility."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from uuid import uuid4

from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.device.ports import DeviceHooks
from cephvr.controller.ports import BackendPort
from cephvr.controller.state import ConfigurationState, LifecycleState, LimitsState
from cephvr.shared.deadlines import remaining_seconds
from cephvr.shared.preview_rates import valid_rates


class StimulusPreviewController:
    def __init__(
        self,
        lifecycle: LifecycleState,
        configuration: ConfigurationState,
        backends: Mapping[str, BackendPort],
        generation: str,
        limits: LimitsState,
        clock: Callable[[], int],
        hooks: DeviceHooks,
    ) -> None:
        self.lifecycle, self.configuration, self.backends = (
            lifecycle,
            configuration,
            backends,
        )
        self.generation, self.limits, self.clock, self.hooks = (
            generation,
            limits,
            clock,
            hooks,
        )
        self.view = pb.StimulusPreviewState()
        self.pending = False

    async def report(self, report: pb.StimulusPreviewState) -> pb.ReportReceipt:
        async with self.lifecycle.lock:
            backend = self.backends.get("visual_stimulus")
            if (
                backend is None
                or report.backend != backend.context
                or report.source.role != "visual_stimulus_renderer"
                or not report.source.generation
                or report.session != self.lifecycle.session.context
                or report.configuration_revision != self.configuration.revision
                or len(report.failure) > 512
                or (report.visible and not report.available)
                or (
                    report.HasField("rates")
                    and not valid_rates(
                        report.rates.source_fps
                        if report.rates.HasField("source_fps")
                        else None,
                        report.rates.preview_fps
                        if report.rates.HasField("preview_fps")
                        else None,
                        report.rates.observed_monotonic_ns,
                    )
                )
            ):
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(
                        code="PREVIEW_SCOPE",
                        message="stale or invalid stimulus preview report",
                    ),
                )
            # Concurrent status RPCs may arrive out of order. Acknowledge older
            # observations without replacing the newest renderer-attested state.
            if (
                self.view.source == report.source
                and self.view.session == report.session
                and report.revision <= self.view.revision
            ):
                return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
            self.view.CopyFrom(report)
            self.hooks.publish()
            return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    async def execute(
        self, request: rpc.SetStimulusPreviewRequest
    ) -> pb.CommandAdmission:
        command_id = request.command.operator.command_id
        async with self.lifecycle.lock:
            error = self.hooks.authorized(request.command, targets_work=True)
            backend = self.backends.get("visual_stimulus")
            if (
                error
                or backend is None
                or self.pending
                or self.lifecycle.session.phase
                not in (
                    pb.SESSION_PHASE_READY,
                    pb.SESSION_PHASE_STARTING,
                    pb.SESSION_PHASE_RUNNING,
                )
                or self.lifecycle.session.shutdown_requested
                or request.expected_configuration_revision
                != self.configuration.revision
                or self.view.session != self.lifecycle.session.context
                or self.view.backend != backend.context
                or self.view.configuration_revision != self.configuration.revision
                or not self.view.available
            ):
                return self.hooks.admission(
                    command_id,
                    error=error
                    or "Visual Stimulus preview is unavailable in this session",
                )
            placement = request.placement
            if (
                placement.ByteSize() > 256
                or (placement.side and not 128 <= placement.side <= 2048)
                or (
                    any(
                        (
                            placement.gui_window_handle,
                            placement.gui_process_id,
                            placement.gui_process_creation_time_100ns,
                        )
                    )
                    and not all(
                        (
                            placement.gui_window_handle,
                            placement.gui_process_id,
                            placement.gui_process_creation_time_100ns,
                        )
                    )
                )
            ):
                return self.hooks.admission(
                    command_id, error="invalid preview placement"
                )
            forwarded = rpc.StimulusPreviewRequest(
                command=rpc.BackendCommand(
                    command_id=str(uuid4()),
                    issuer=pb.ProcessIdentity(
                        role="controller", generation=self.generation
                    ),
                    target=backend.context,
                    work=pb.WorkContext(session=self.lifecycle.session.context),
                    parent_operation=pb.OperationContext(command_id=command_id),
                ),
                configuration_revision=self.configuration.revision,
                visible=request.visible,
                placement=placement,
            )
            deadline = self.clock() + self.limits.current.recovery_ns
            self.hooks.operation(command_id, "SetStimulusPreview")
            self.pending = True
            self.hooks.spawn(self._perform(command_id, backend, forwarded, deadline))
            self.hooks.publish()
            return self.hooks.admission(command_id)

    async def _perform(
        self,
        command_id: str,
        backend: BackendPort,
        request: rpc.StimulusPreviewRequest,
        deadline: int,
    ) -> None:
        error = ""
        try:
            async with asyncio.timeout(remaining_seconds(deadline, clock=self.clock)):
                admission = await backend.set_stimulus_preview(
                    request, deadline_ns=deadline
                )
                if admission.result != pb.COMMAND_RESULT_ACCEPTED:
                    raise RuntimeError(admission.failure.message or "preview rejected")
                query = rpc.RetainedResultQuery(
                    query=rpc.BackendQuery(
                        target=backend.context, work=request.command.work
                    ),
                    command_id=request.command.command_id,
                )
                while True:
                    result = await backend.get_retained_result(
                        query, deadline_ns=deadline
                    )
                    operation = result.operation
                    if result.found and operation.complete:
                        if (
                            result.backend != backend.context
                            or operation.context.command_id
                            != request.command.command_id
                            or operation.work != request.command.work
                            or operation.command != "SetStimulusPreview"
                        ):
                            raise RuntimeError("preview completion identity differs")
                        if (
                            not operation.HasField("succeeded")
                            or not operation.succeeded
                        ):
                            raise RuntimeError(
                                operation.failure.message or "preview failed"
                            )
                        break
                    await asyncio.sleep(0.02)
        except Exception as exc:
            error = str(exc) or "preview completion timed out; visibility unconfirmed"
        async with self.lifecycle.lock:
            self.pending = False
            self.hooks.complete_operation(
                command_id,
                success=not error,
                progress="Preview visibility applied"
                if not error
                else "Preview failed",
                error=error,
            )
            self.hooks.publish()
