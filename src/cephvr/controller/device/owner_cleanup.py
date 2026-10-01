"""Bounded release of controller-owned manual camera state after lease loss."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Mapping
from copy import deepcopy

from google.protobuf.message import Message

from cephvr.acquisition.v1 import camera_pb2 as camera_pb
from cephvr.acquisition.v1 import runtime_pb2 as acquisition_pb
from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.device.ports import DeviceHooks
from cephvr.controller.device.release_evidence import (
    camera_policy,
    camera_view,
    finish_editing_confirmed,
    load_file_policies,
    manual_state_open,
    stop_preview_confirmed,
)
from cephvr.controller.device.status_retention import CameraStatusRetention
from cephvr.controller.ports import BackendPort
from cephvr.controller.projections import ProjectionStore
from cephvr.controller.state import (
    RETAINED_LIMIT,
    CameraOperation,
    ConfigurationState,
    ControlState,
    DeviceState,
    LifecycleState,
    LimitsState,
)

MANUAL_CLEANUP_TASK_NAME = "manual-camera-cleanup"
_RETRY_MAX_S = 10.0


def record_manual_cleanup_warning(
    control: ControlState, publish: Callable[[], None], error: BaseException | None
) -> None:
    """Replace the retained cleanup warning by the current failure, or clear it."""
    kept = [
        item for item in control.warnings if item.component != "manual_camera_cleanup"
    ]
    changed = error is not None or len(kept) != len(control.warnings)
    if error is not None:
        kept.append(
            pb.Warning(
                warning_id=str(uuid.uuid4()),
                component="manual_camera_cleanup",
                message=f"manual camera cleanup pending, retrying: {error}",
            )
        )
    control.warnings = kept[-RETAINED_LIMIT:]
    if changed:
        publish()


class ManualControlCleanup:
    """Finish in-flight edits, then stop previews without changing saved settings."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        configuration: ConfigurationState,
        device: DeviceState,
        backends: Mapping[str, BackendPort],
        projections: ProjectionStore,
        file_policy_loader: Callable[[frozenset[str]], Mapping[str, Message]] | None,
        generation: str,
        limits: LimitsState,
        clock: Callable[[], int],
        hooks: DeviceHooks,
        status_retention: CameraStatusRetention,
        retry_delay_s: float = 1.0,
    ) -> None:
        self.lifecycle = lifecycle
        self.configuration = configuration
        self.device = device
        self.backends = backends
        self.projections = projections
        self.file_policy_loader = file_policy_loader
        self.generation = generation
        self.limits = limits
        self.clock = clock
        self.hooks = hooks
        self.status_retention = status_retention
        self.retry_delay_s = retry_delay_s
        self._failures = 0

    async def run(self) -> None:
        """Release manual state promptly after loss; active experiments are untouched."""
        async with self.lifecycle.lock:
            if self.lifecycle.session.phase != pb.SESSION_PHASE_CONFIGURATION:
                return
            deadline_ns = self.clock() + self.limits.current.setup_ns
        owner_operation_id = str(uuid.uuid4())
        self.hooks.operation(
            owner_operation_id,
            "ReleaseManualCameraState",
            progress="manual camera cleanup pending",
        )
        try:
            if not await self._finish_existing_operation(deadline_ns):
                raise TimeoutError("existing camera operation did not reconcile")
            views = self.projections.devices
            settings = self._settings()
            backend = self.backends.get("acquisition")
            if views is None:
                if not self.device.manual_effects_admitted:
                    await self._complete_cleanup(owner_operation_id)
                    return
                raise RuntimeError("manual camera effects have no retained device view")
            view_by_role = (
                (camera_pb.CAMERA_ROLE_BEHAVIORAL, views.behavioral),
                (camera_pb.CAMERA_ROLE_TRACKING, views.tracking),
            )
            known_views = all(
                view.HasField("device_open")
                and view.HasField("preview_running")
                and view.HasField("cleanup_pending")
                for _, view in view_by_role
            )
            any_effect = any(
                (view.HasField("device_open") and view.device_open)
                or (view.HasField("preview_running") and view.preview_running)
                or view.preview_prepared
                or (view.HasField("cleanup_pending") and view.cleanup_pending)
                for _, view in view_by_role
            )
            if not self.device.manual_effects_admitted and not any_effect:
                await self._complete_cleanup(owner_operation_id)
                return
            if not known_views and self.device.manual_effects_admitted:
                raise RuntimeError("manual camera device state is incomplete")
            if known_views and not any(
                manual_state_open(view) or view.cleanup_pending
                for _, view in view_by_role
            ):
                self.device.manual_effects_admitted = False
                await self._complete_cleanup(owner_operation_id)
                return
            if settings is None or backend is None:
                raise RuntimeError("open manual camera has no cleanup backend settings")
            policies = await load_file_policies(
                self.file_policy_loader, (deadline_ns - self.clock()) / 1e9
            )
            for role, view in view_by_role:
                if self.clock() >= deadline_ns:
                    break
                if not manual_state_open(view) and not view.cleanup_pending:
                    continue
                if (
                    view.preview_running
                    or view.preview_prepared
                    or view.cleanup_pending
                    and view.preview_run_id
                ):
                    final_view = await self._release_camera(
                        backend,
                        settings,
                        policies,
                        role,
                        view,
                        svc.CAMERA_COMMAND_KIND_STOP_PREVIEW,
                        deadline_ns,
                        owner_operation_id,
                    )
                else:
                    final_view = view
                if final_view.device_open or final_view.cleanup_pending:
                    await self._release_camera(
                        backend,
                        settings,
                        policies,
                        role,
                        final_view,
                        svc.CAMERA_COMMAND_KIND_FINISH_EDITING,
                        deadline_ns,
                        owner_operation_id,
                    )
            if self.clock() >= deadline_ns:
                raise TimeoutError("manual camera cleanup deadline expired")
            await self._complete_cleanup(owner_operation_id)
        except Exception as exc:
            self.hooks.complete_operation(
                owner_operation_id,
                success=False,
                progress="manual camera cleanup incomplete",
                error=str(exc),
            )
            raise

    async def _task(self, delay_s: float = 0.0) -> None:
        """One cleanup attempt; a failure schedules the next until confirmed.

        The pending barrier stays set and the runtime shows the failure as a
        device-cleanup warning instead of interrupting an experiment.
        """
        current = asyncio.current_task()
        if current is not None:
            current.set_name(MANUAL_CLEANUP_TASK_NAME)
        if delay_s > 0:
            await asyncio.sleep(delay_s)
        try:
            await self.run()
        except Exception:
            async with self.lifecycle.lock:
                if (
                    self.lifecycle.manual_control_cleanup_pending
                    and not self.lifecycle.manual_control_cleanup_stopping
                    and self.lifecycle.session.phase == pb.SESSION_PHASE_CONFIGURATION
                    and not self.lifecycle.session.shutdown_requested
                ):
                    delay = min(self.retry_delay_s * 2**self._failures, _RETRY_MAX_S)
                    self._failures += 1
                    self.lifecycle.manual_control_cleanup_task = self.hooks.spawn(
                        self._task(delay)
                    )
            raise
        self._failures = 0

    async def request(self) -> None:
        """Start one retained cleanup task that survives caller cancellation."""
        async with self.lifecycle.lock:
            if self.lifecycle.session.phase != pb.SESSION_PHASE_CONFIGURATION:
                return
            self.lifecycle.manual_control_cleanup_pending = True
            task = self.lifecycle.manual_control_cleanup_task
            if task is None or task.done():
                task = self.hooks.spawn(self._task())
                self.lifecycle.manual_control_cleanup_task = task
        try:
            await asyncio.shield(task)
        except Exception:
            # Runtime task supervision records a warning; the admission barrier
            # remains until exact cleanup evidence is available.
            return

    async def _complete_cleanup(self, operation_id: str) -> None:
        async with self.lifecycle.lock:
            if self.lifecycle.session.phase != pb.SESSION_PHASE_CONFIGURATION:
                return
            self.lifecycle.manual_control_cleanup_pending = False
            self.lifecycle.manual_control_cleanup_task = None
            self.device.manual_effects_admitted = False
            self.hooks.complete_operation(
                operation_id,
                success=True,
                progress="manual camera state released",
            )
            self.hooks.publish()

    async def _finish_existing_operation(self, deadline_ns: int) -> bool:
        async with self.lifecycle.lock:
            if self.lifecycle.session.phase != pb.SESSION_PHASE_CONFIGURATION:
                return False
            operation = self.device.camera_operation
            if operation is None:
                return True
            self.device.camera_operation_changed.clear()
        while True:
            remaining = max(0, deadline_ns - self.clock()) / 1e9
            if remaining <= 0:
                return False
            try:
                await asyncio.wait_for(
                    self.device.camera_operation_changed.wait(), remaining
                )
            except TimeoutError:
                return False
            async with self.lifecycle.lock:
                if self.lifecycle.session.phase != pb.SESSION_PHASE_CONFIGURATION:
                    return False
                if self.device.camera_operation is operation:
                    self.device.camera_operation_changed.clear()
                    continue
                return bool(
                    operation.admission_rejected or operation.final_status is not None
                )

    def _settings(self) -> pb.AcquisitionSettings | None:
        return next(
            (
                item.acquisition
                for item in self.configuration.current.backends
                if item.backend_name == "acquisition"
                and item.WhichOneof("settings") == "acquisition"
            ),
            None,
        )

    async def _release_camera(
        self,
        backend: BackendPort,
        settings: pb.AcquisitionSettings,
        policies: acquisition_pb.AcquisitionFilePolicies,
        role: camera_pb.CameraRole,
        view: pb.CameraDeviceView,
        kind: svc.CameraCommandKind,
        deadline_ns: int,
        owner_operation_id: str,
    ) -> pb.CameraDeviceView:
        role_name = (
            "behavioral" if role == camera_pb.CAMERA_ROLE_BEHAVIORAL else "tracking"
        )
        camera_settings = getattr(settings, role_name)
        if not camera_settings.HasField("device"):
            raise RuntimeError(f"{role_name} camera has no retained device assignment")
        policy = camera_policy(policies, role)
        command_id = str(uuid.uuid4())
        command = svc.AcquisitionCameraCommand(
            camera=role,
            kind=kind,
            configuration_revision=self.configuration.revision,
        )
        command.command.command_id = command_id
        command.command.issuer.CopyFrom(
            pb.ProcessIdentity(role="controller", generation=self.generation)
        )
        command.command.target.CopyFrom(backend.context)
        command.command.work.CopyFrom(self.projections.work)
        command.command.parent_operation.command_id = owner_operation_id
        command.file_policies.CopyFrom(policies)
        command.requested.CopyFrom(camera_settings.device)
        command.transport.CopyFrom(policy.transport)
        if kind == svc.CAMERA_COMMAND_KIND_STOP_PREVIEW:
            command.preview_run_id = view.preview_run_id
        async with self.lifecycle.lock:
            if self.lifecycle.session.phase != pb.SESSION_PHASE_CONFIGURATION:
                raise RuntimeError("Configuration ended during manual camera cleanup")
            operation = CameraOperation(
                command_id,
                command_id,
                self.configuration.revision,
                role,
                kind,
                deepcopy(command.command.work),
                deadline_ns,
                False,
                preview_run_id=view.preview_run_id
                if kind == svc.CAMERA_COMMAND_KIND_STOP_PREVIEW
                else "",
            )
            if self.device.camera_operation is not None:
                raise RuntimeError("camera operation began during owner cleanup")
            self.status_retention.prune()
            self.status_retention.reserve(operation)
            self.device.camera_operation = operation
            self.device.camera_operation_changed.clear()
            self.device.manual_effects_admitted = True
            self.hooks.operation(
                command_id,
                "ReleaseManualCameraState",
                progress="safe camera release pending",
            )
            self.hooks.publish()
        try:
            reply = await asyncio.wait_for(
                backend.execute_camera_command(command, deadline_ns=deadline_ns),
                max(0, (deadline_ns - self.clock()) / 1e9),
            )
            if reply.result != pb.COMMAND_RESULT_ACCEPTED:
                async with self.lifecycle.lock:
                    if self.device.camera_operation is operation:
                        operation.admission_rejected = True
                        self.status_retention.release_unstarted(operation)
                        self.device.camera_operation = None
                        self.device.camera_operation_changed.set()
                        self.hooks.complete_operation(
                            command_id,
                            success=False,
                            progress="safe camera release rejected",
                            error=reply.failure.message,
                        )
                        self.hooks.publish()
                raise RuntimeError(reply.failure.message or "camera release rejected")
            while True:
                remaining = max(0, deadline_ns - self.clock()) / 1e9
                if remaining <= 0:
                    raise TimeoutError("camera release completion was not confirmed")
                async with self.lifecycle.lock:
                    if self.device.camera_operation is not operation:
                        if operation.final_status is None:
                            raise RuntimeError(
                                "manual camera release has no retained final status"
                            )
                        view = camera_view(
                            operation.camera, operation.final_status.views
                        )
                        if not _release_was_confirmed(operation):
                            raise RuntimeError(
                                "manual camera release result lacks successful evidence"
                            )
                        return pb.CameraDeviceView.FromString(
                            view.SerializeToString(deterministic=True)
                        )
                    self.device.camera_operation_changed.clear()
                try:
                    await asyncio.wait_for(
                        self.device.camera_operation_changed.wait(), remaining
                    )
                except TimeoutError as exc:
                    raise TimeoutError(
                        "camera release completion was not confirmed"
                    ) from exc
        except Exception as exc:
            async with self.lifecycle.lock:
                if (
                    self.device.camera_operation is operation
                    and operation.final_status is None
                ):
                    operation.timed_out = True
                    self.hooks.complete_operation(
                        command_id,
                        success=False,
                        progress="safe camera release unconfirmed",
                        error=str(exc),
                    )
                    self.hooks.publish()
            raise


def _release_was_confirmed(operation: CameraOperation) -> bool:
    """Exact terminal success confirms release, even when it arrived late."""
    status = operation.final_status
    if (
        status is None
        or not status.result.HasField("succeeded")
        or not status.result.succeeded
    ):
        return False
    view = camera_view(operation.camera, status.views)
    if operation.kind == svc.CAMERA_COMMAND_KIND_STOP_PREVIEW:
        return stop_preview_confirmed(view, operation.preview_run_id)
    return finish_editing_confirmed(view, require_closed=True)
