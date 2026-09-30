"""Stop, reallocate and restart external-trigger previews around MCU edits."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from uuid import uuid4

from cephvr.acquisition.coordinator.commands import (
    retain_worker_command,
    wait_child_operation,
)
from cephvr.acquisition.coordinator.manual_device_status import (
    ManualDeviceStatusReporter,
)
from cephvr.acquisition.coordinator.manual_preview_resources import (
    allocate_manual_preview_slot,
)
from cephvr.acquisition.coordinator.manual_preview_setup import (
    build_preview_payload,
    new_worker_preview,
)
from cephvr.acquisition.coordinator.manual_preview_transfer import (
    ManualPreviewTransferOwner,
)
from cephvr.acquisition.coordinator.manual_pulse_observation import (
    retain_applied_pulse_state,
)
from cephvr.acquisition.coordinator.session_payloads import camera_policy, role_name
from cephvr.acquisition.ports import ResourcePort, SerialOwnerPort
from cephvr.acquisition.state import (
    ConfigurationRecord,
    CoordinatorIdentity,
    PausedPreview,
    PulseRecord,
    ResourceRecord,
    WorkerPreview,
    WorkerRecord,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.resource_ledger import NativeResourceLedger
from cephvr.shared.clock import host_time_ns


class ManualPreviewPulseLifecycle:
    """Own exact old/new preview runs for one sessionless pulse operation."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        configuration: ConfigurationRecord,
        workers: dict[int, WorkerRecord],
        pulse: PulseRecord,
        serial: SerialOwnerPort,
        resources: dict[str, ResourceRecord],
        resource_ledger: NativeResourceLedger,
        resource_port: ResourcePort,
        transfers: ManualPreviewTransferOwner,
        device_status: ManualDeviceStatusReporter,
        lock: asyncio.Lock,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.configuration = configuration
        self.workers = workers
        self.pulse = pulse
        self.serial = serial
        self.resources = resources
        self.resource_ledger = resource_ledger
        self.resource_port = resource_port
        self.transfers = transfers
        self.device_status = device_status
        self.lock = lock
        self.clock = clock

    async def pause_for_pulse_change(
        self, roles: tuple[int, ...], *, deadline_ns: int
    ) -> tuple[PausedPreview, ...]:
        paused: list[PausedPreview] = []
        for role in roles:
            worker = self.workers.get(role)
            preview = worker.preview if worker is not None else None
            if preview is None or not preview.started:
                continue
            if worker is None:
                raise RuntimeError("preview worker disappeared before pulse pause")
            command_id = str(uuid4())
            command, child, port = retain_worker_command(
                worker,
                work=None,
                parent_operation=control.OperationContext(command_id=command_id),
                kind="stop_preview",
                deadline_ns=deadline_ns,
                configuration_revision=preview.configuration_revision,
            )
            preview.stopping = True
            preview.stop_operation = control.OperationContext(
                command_id=child.command_id
            )
            receipt = await port.stop_preview(
                acq.WorkerStopPreview(
                    command=command,
                    preview_run_id=preview.run_id,
                    release_device=False,
                ),
                deadline_ns=deadline_ns,
            )
            if receipt.result != control.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError("preview pause was not admitted")
            state = await wait_child_operation(
                child, deadline_ns, self.lock, self.clock
            )
            if not state.succeeded:
                raise RuntimeError("preview pause failed")
            await _wait_event(preview.stopped_event, deadline_ns, self.clock)
            await _wait_event(preview.cleanup_event, deadline_ns, self.clock)
            if preview.resolved_camera is None:
                raise RuntimeError("preview pause lacks retained resolved camera")
            self.device_status.resolve_camera(
                role,
                preview.resolved_camera,
                device_open=True,
                preview_prepared=False,
                preview_running=False,
                configuration_revision=preview.configuration_revision,
            )
            paused.append(
                PausedPreview(
                    role,
                    camera.CameraResolvedState.FromString(
                        preview.resolved_camera.SerializeToString(deterministic=True)
                    ),
                    preview.preview_output_bit_depth,
                )
            )
            viewer_was_attached = preview.viewer is not None
            preview.stopping = False
            self.transfers.retire(preview)
            worker.preview = None
            self.transfers.close_retired_resource(preview)
            if viewer_was_attached:
                await _wait_event(
                    preview.viewer_released_event, deadline_ns, self.clock
                )
                if preview.viewer is not None:
                    raise RuntimeError(
                        "preview viewer release did not retire exact transfer"
                    )
            self.transfers.close_retired_resource(preview)
            if preview.allocation_id in self.resources:
                raise RuntimeError("paused preview ring ownership remains unresolved")
        return tuple(paused)

    async def resume_after_pulse_change(
        self, token: tuple[PausedPreview, ...], *, deadline_ns: int
    ) -> None:
        restarted: list[tuple[WorkerRecord, WorkerPreview]] = []
        for item in token:
            worker = self.workers.get(item.role)
            if worker is None or worker.preview is not None:
                raise RuntimeError("paused preview ownership changed before resume")
            restarted.append(
                (worker, await self._prepare_restart(worker, item, deadline_ns))
            )
        external_roles = tuple(
            item.role for item in token if _is_external(self.configuration, item.role)
        )
        if external_roles:
            evidence = await self.serial.on(
                external_roles,
                scheduled_boundary_ns=None,
                deadline_ns=deadline_ns,
            )
            retain_applied_pulse_state(self.pulse, evidence, deadline_ns=deadline_ns)
        for worker, preview in restarted:
            await _wait_event(preview.started_event, deadline_ns, self.clock)
            if not preview.started:
                raise RuntimeError("preview restart lacks first usable frame evidence")
            if preview.resolved_camera is None:
                raise RuntimeError("preview restart lacks resolved camera state")
            role = worker.context.camera
            self.device_status.resolve_camera(
                role,
                preview.resolved_camera,
                device_open=True,
                preview_prepared=True,
                preview_running=True,
                preview_run_id=preview.run_id,
                configuration_revision=preview.configuration_revision,
            )

    async def _prepare_restart(
        self,
        worker: WorkerRecord,
        paused: PausedPreview,
        deadline_ns: int,
    ) -> WorkerPreview:
        setting = getattr(self.configuration.settings, role_name(paused.role))
        policy = camera_policy(self.configuration.file_policies, paused.role)
        run_id = str(uuid4())
        attachment, _resource = await allocate_manual_preview_slot(
            worker=worker,
            resolved=paused.resolved,
            controller=self.identity.controller,
            run_id=run_id,
            configuration_revision=self.configuration.revision,
            resources=self.resources,
            ledger=self.resource_ledger,
            resource_port=self.resource_port,
        )
        preview = new_worker_preview(
            run_id,
            self.configuration.revision,
            attachment,
            paused.resolved,
            paused.output_bits,
        )
        worker.preview = preview
        command_id = str(uuid4())
        prepare_command, prepare_child, port = retain_worker_command(
            worker,
            work=None,
            parent_operation=control.OperationContext(command_id=command_id),
            kind="prepare_preview",
            deadline_ns=deadline_ns,
            configuration_revision=self.configuration.revision,
            requested_device_id=setting.device.device_id,
        )
        preview.preparation = control.OperationContext(
            command_id=prepare_child.command_id
        )
        payload = build_preview_payload(setting, policy, paused.resolved, attachment)
        prepare = acq.WorkerPreparePreview(
            command=prepare_command,
            configuration_revision=self.configuration.revision,
            preview_run_id=run_id,
            camera=payload,
        )
        receipt = await port.prepare_preview(prepare, deadline_ns=deadline_ns)
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError("preview re-preparation was not admitted")
        prepared = await wait_child_operation(
            prepare_child, deadline_ns, self.lock, self.clock
        )
        if not prepared.succeeded:
            raise RuntimeError("preview re-preparation failed")
        start_command, start_child, port = retain_worker_command(
            worker,
            work=None,
            parent_operation=control.OperationContext(command_id=command_id),
            kind="start_preview",
            deadline_ns=deadline_ns,
            configuration_revision=self.configuration.revision,
        )
        preview.start_operation = control.OperationContext(
            command_id=start_child.command_id
        )
        receipt = await port.start_preview(
            acq.WorkerStartPreview(
                command=start_command,
                preparation=preview.preparation,
                configuration_revision=self.configuration.revision,
                preview_run_id=run_id,
            ),
            deadline_ns=deadline_ns,
        )
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError("preview restart was not admitted")
        started = await wait_child_operation(
            start_child, deadline_ns, self.lock, self.clock
        )
        if not started.succeeded:
            raise RuntimeError("preview restart failed")
        return preview


def _is_external(configuration: ConfigurationRecord, role: int) -> bool:
    setting = getattr(configuration.settings, role_name(role))
    return bool(
        setting.HasField("device")
        and setting.device.HasField("frame_timing")
        and setting.device.frame_timing == camera.FRAME_TIMING_EXTERNAL_TRIGGER
    )


async def _wait_event(
    event: asyncio.Event, deadline_ns: int, clock: Callable[[], int]
) -> None:
    remaining = max(0, deadline_ns - clock()) / 1_000_000_000
    if remaining <= 0:
        raise TimeoutError("preview lifecycle evidence missed its deadline")
    await asyncio.wait_for(event.wait(), remaining)
