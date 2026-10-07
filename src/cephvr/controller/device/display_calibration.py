"""Leased, sessionless display-calibration commands and evidence deadlines (V01)."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from uuid import uuid4

from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.device.ports import DeviceHooks
from cephvr.controller.ports import BackendPort
from cephvr.controller.projections import ProjectionStore
from cephvr.controller.state import (
    ConfigurationState,
    ControlState,
    DeviceState,
    LifecycleState,
    LimitsState,
)
from cephvr.shared.identity import require_uuid4
from cephvr.visual_stimulus.v1 import runtime_pb2 as vs_runtime


def _read_reference(
    root_value: str, reference: str, expected_sha256: str, maximum: int
) -> tuple[bytes, Path]:
    relative = PurePosixPath(reference)
    if (
        not reference
        or "\\" in reference
        or relative.is_absolute()
        or any(part in ("", ".", "..") for part in relative.parts)
    ):
        raise ValueError("calibration references must be portable relative paths")
    root = Path(root_value).resolve(strict=True)
    path = root.joinpath(*relative.parts).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("calibration reference escapes the accepted asset root")
    before = path.stat()
    if before.st_size > maximum:
        raise ValueError("calibration asset exceeds its accepted byte limit")
    with path.open("rb") as source:
        data = source.read(maximum + 1)
    after = path.stat()
    if (
        len(data) > maximum
        or (before.st_size, before.st_mtime_ns, before.st_ino)
        != (after.st_size, after.st_mtime_ns, after.st_ino)
        or len(data) != after.st_size
    ):
        raise OSError("calibration asset changed while being verified")
    digest = hashlib.sha256(data).hexdigest()
    if len(expected_sha256) != 64 or digest != expected_sha256.lower():
        raise ValueError("calibration asset digest differs from the submitted identity")
    return data, path


class DisplayCalibrationController:
    """Admit untimed renderer diagnostics without creating a session or trial."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        configuration: ConfigurationState,
        control: ControlState,
        device: DeviceState,
        backends: Mapping[str, BackendPort],
        projections: ProjectionStore,
        file_policy_loader: Callable[[frozenset[str]], Mapping[str, Message]] | None,
        display_validator: Callable[[str], frozenset[str]] | None,
        display_pacing_resolver: Callable[[str, Message], str] | None,
        generation: str,
        limits: LimitsState,
        hooks: DeviceHooks,
        maximum_asset_bytes: int,
        clock: Callable[[], int],
    ) -> None:
        self.lifecycle = lifecycle
        self.configuration = configuration
        self.control = control
        self.device = device
        self.backends = backends
        self.projections = projections
        self.file_policy_loader = file_policy_loader
        self.display_validator = display_validator
        self.display_pacing_resolver = display_pacing_resolver
        self.generation = generation
        self.limits = limits
        self.hooks = hooks
        self.maximum_asset_bytes = maximum_asset_bytes
        self.clock = clock
        self._dispatch_lock = asyncio.Lock()
        self._active_backend: BackendPort | None = None
        self._active_backend_context: pb.BackendContext | None = None
        self._owner_loss_deadline_ns: int | None = None
        self._inflight_backend_calls: set[asyncio.Task[pb.CommandAdmission]] = set()

    async def open(
        self, request: svc.OpenDisplayCalibrationRequest
    ) -> pb.CommandAdmission:
        command = request.command
        command_id = command.operator.command_id
        async with self.lifecycle.lock:
            error = self.hooks.authorized(command)
            if error:
                return self.hooks.admission(command_id, error=error)
            if request.expected_configuration_revision != self.configuration.revision:
                return self.hooks.admission(
                    command_id, error="accepted configuration revision changed"
                )
            if (
                self.lifecycle.authority_lost
                or self.lifecycle.session.shutdown_requested
                or self.lifecycle.session.phase != pb.SESSION_PHASE_CONFIGURATION
                or self.lifecycle.attempt is not None
                or self.device.display_pending is not None
                or self.device.calibration_pending is not None
            ):
                return self.hooks.admission(
                    command_id,
                    error="display calibration is unavailable in the current phase",
                )
            prior = self._evidence()
            if prior is not None and (
                prior.state != vs_runtime.DISPLAY_CALIBRATION_STATE_IDLE
                or not prior.HasField("idle")
                or not prior.idle
                or not prior.HasField("resources_closed")
                or not prior.resources_closed
            ):
                return self.hooks.admission(
                    command_id,
                    error="previous display calibration is not confirmed closed",
                )
            if self.configuration.current.HasField("asset_root") is False:
                return self.hooks.admission(
                    command_id, error="accepted asset root is unavailable"
                )
            setting = next(
                (
                    item
                    for item in self.configuration.current.backends
                    if item.backend_name == "visual_stimulus"
                    and item.enabled
                    and item.WhichOneof("settings") == "visual_stimulus"
                ),
                None,
            )
            backend = self.backends.get("visual_stimulus")
            if setting is None or backend is None:
                return self.hooks.admission(
                    command_id,
                    error="enabled Visual Stimulus configuration is unavailable",
                )
            revision = self.configuration.revision
            asset_root = self.configuration.current.asset_root
            backend_context = pb.BackendContext.FromString(
                backend.context.SerializeToString()
            )
            if self.file_policy_loader is None or self.display_validator is None:
                return self.hooks.admission(
                    command_id,
                    error="Visual Stimulus file policy validation is unavailable",
                )
            limits = self.limits.current
            deadline = (
                self.clock()
                + 5 * limits.validation_ns
                + limits.setup_ns
                + limits.recovery_ns
            )
            try:
                self.hooks.operation(
                    command_id,
                    "OpenDisplayCalibration",
                    progress="calibration asset validation pending",
                )
            except RuntimeError as exc:
                return self.hooks.admission(command_id, error=str(exc))
            self.device.calibration_pending = (
                command_id,
                revision,
                deadline,
                request.diagnostic_id,
                vs_runtime.DISPLAY_CALIBRATION_STATE_ACTIVE,
                frozenset(),
            )
            self.device.calibration_blocked = True
            self._owner_loss_deadline_ns = None
            self.hooks.publish()
        try:
            loaded = await asyncio.wait_for(
                asyncio.to_thread(
                    self.file_policy_loader, frozenset({"visual_stimulus"})
                ),
                max(0, (deadline - self.clock()) / 1e9),
            )
            policies = loaded.get("visual_stimulus")
            if (
                policies is None
                or policies.DESCRIPTOR
                != vs_runtime.VisualStimulusFilePolicies.DESCRIPTOR
            ):
                raise ValueError("Visual Stimulus resource limits are unavailable")
            policies = vs_runtime.VisualStimulusFilePolicies.FromString(
                policies.SerializeToString()
            )
            if not policies.HasField("limits"):
                raise ValueError("Visual Stimulus resource limits are unavailable")
            if (
                not policies.limits.HasField("max_document_bytes")
                or not policies.limits.HasField("max_asset_cpu_bytes")
                or not policies.limits.HasField("max_asset_gpu_bytes")
                or min(
                    policies.limits.max_document_bytes,
                    policies.limits.max_asset_cpu_bytes,
                    policies.limits.max_asset_gpu_bytes,
                )
                <= 0
            ):
                raise ValueError("Visual Stimulus calibration limits must be positive")
            profile_limit = int(policies.limits.max_document_bytes)
            arena_limit = min(
                self.maximum_asset_bytes,
                int(policies.limits.max_asset_cpu_bytes),
            )
            profile_data, _ = await asyncio.wait_for(
                asyncio.to_thread(
                    _read_reference,
                    asset_root,
                    request.profile_asset_reference,
                    request.expected_profile_sha256,
                    profile_limit,
                ),
                max(0, (deadline - self.clock()) / 1e9),
            )
            arena_data, _ = await asyncio.wait_for(
                asyncio.to_thread(
                    _read_reference,
                    asset_root,
                    request.arena_asset_reference,
                    request.expected_arena_sha256,
                    arena_limit,
                ),
                max(0, (deadline - self.clock()) / 1e9),
            )
            if not arena_data:
                raise ValueError("arena asset is empty")
            from cephvr.visual_stimulus.config.models.display_profile import (
                parse_display_json,
            )

            display_json = profile_data.decode("utf-8")
            if self.display_pacing_resolver is not None:
                display_json = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.display_pacing_resolver, display_json, policies
                    ),
                    max(0, (deadline - self.clock()) / 1e9),
                )
            accepted = parse_display_json(display_json, max_bytes=profile_limit)
            canonical_profile_json = accepted.model_dump_json()
            output_ids = await asyncio.wait_for(
                asyncio.to_thread(self.display_validator, display_json),
                max(0, (deadline - self.clock()) / 1e9),
            )
            if not output_ids or len(output_ids) > 64:
                raise ValueError("display profile has no bounded active outputs")
            require_uuid4(request.diagnostic_id)
        except asyncio.CancelledError:
            await self._admission_failed(
                command_id,
                "display calibration Open cancelled before dispatch",
                rejected=True,
            )
            raise
        except Exception as exc:
            await self._admission_failed(command_id, str(exc), rejected=True)
            return self.hooks.admission(
                command_id, error=f"display calibration assets rejected: {exc}"
            )
        rejection = ""
        dispatch_cancelled = False
        dispatch: svc.VisualStimulusDisplayCalibrationOpenRequest | None = None
        async with self.lifecycle.lock:
            error = self.hooks.authorized(command)
            if (
                error
                or self.lifecycle.authority_lost
                or self.lifecycle.session.shutdown_requested
                or revision != self.configuration.revision
                or self.lifecycle.session.phase != pb.SESSION_PHASE_CONFIGURATION
                or self.lifecycle.attempt is not None
                or self.device.display_pending is not None
                or self.device.calibration_pending is None
                or self.device.calibration_pending[0] != command_id
                or self.backends.get("visual_stimulus") is not backend
                or backend.context != backend_context
                or self.clock() >= deadline
            ):
                rejection = error or (
                    "authority, configuration or deadline changed before dispatch"
                )
            else:
                try:
                    await asyncio.wait_for(
                        self._dispatch_lock.acquire(),
                        max(0, (deadline - self.clock()) / 1e9),
                    )
                except asyncio.CancelledError:
                    rejection = "display calibration Open cancelled before dispatch"
                    dispatch_cancelled = True
                except TimeoutError:
                    rejection = "calibration dispatch deadline expired"
            if not rejection:
                self._active_backend = backend
                self._active_backend_context = pb.BackendContext.FromString(
                    backend_context.SerializeToString()
                )
                dispatch = svc.VisualStimulusDisplayCalibrationOpenRequest(
                    command_id=command_id,
                    issuer=pb.ProcessIdentity(
                        role="controller", generation=self.generation
                    ),
                    target=backend_context,
                    configuration_revision=revision,
                    diagnostic_id=request.diagnostic_id,
                    deadline_monotonic_ns=deadline,
                    profile_json=canonical_profile_json,
                    profile_sha256=hashlib.sha256(
                        canonical_profile_json.encode()
                    ).hexdigest(),
                    asset_root=asset_root,
                    arena_relative_path=request.arena_asset_reference,
                    arena_size_bytes=len(arena_data),
                    arena_sha256=request.expected_arena_sha256,
                    policies=policies,
                )
                self.device.calibration_pending = (
                    command_id,
                    revision,
                    deadline,
                    request.diagnostic_id,
                    vs_runtime.DISPLAY_CALIBRATION_STATE_ACTIVE,
                    frozenset(output_ids),
                )
                self.projections.expect_display(command_id, revision)
                self.hooks.publish()
        if rejection:
            await self._admission_failed(command_id, rejection, rejected=True)
            if dispatch_cancelled:
                raise asyncio.CancelledError
            return self.hooks.admission(command_id, error=rejection)
        assert dispatch is not None
        rpc_task: asyncio.Task[pb.CommandAdmission] | None = None
        try:
            rpc_task = asyncio.create_task(
                backend.open_display_calibration(dispatch, deadline_ns=deadline)
            )
            self._track_backend_call(rpc_task)
            # Let the request enter the backend transport before a safety Close
            # may acquire the local dispatch gate.
            await asyncio.sleep(0)
        except asyncio.CancelledError:
            # Cancellation leaves the remote outcome uncertain. Keep the exact
            # pending identity, but always release the local serialization gate.
            raise
        finally:
            if self._dispatch_lock.locked():
                self._dispatch_lock.release()
        assert rpc_task is not None
        try:
            reply = await asyncio.wait_for(
                asyncio.shield(rpc_task),
                max(0, (deadline - self.clock()) / 1e9),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._admission_failed(command_id, str(exc))
            return self.hooks.admission(command_id, error=str(exc))
        if reply.result != pb.COMMAND_RESULT_ACCEPTED:
            message = reply.failure.message or "renderer rejected calibration"
            await self._admission_failed(command_id, message, rejected=True)
            return self.hooks.admission(command_id, error=message)
        self.hooks.spawn(self._timeout(command_id, deadline))
        return self.hooks.admission(command_id)

    async def close(
        self, request: svc.CloseDisplayCalibrationRequest
    ) -> pb.CommandAdmission:
        command = request.command
        command_id = command.operator.command_id
        async with self.lifecycle.lock:
            error = self.hooks.authorized(command)
            if error:
                return self.hooks.admission(command_id, error=error)
            pending = self.device.calibration_pending
            pending_open = (
                pending is not None
                and pending[3] == request.diagnostic_id
                and pending[4] == vs_runtime.DISPLAY_CALIBRATION_STATE_ACTIVE
            )
            display_view = self.projections.display
            evidence = self._evidence()
            if (
                request.expected_configuration_revision != self.configuration.revision
                or self.lifecycle.session.phase != pb.SESSION_PHASE_CONFIGURATION
                or self.lifecycle.attempt is not None
                or (pending is not None and not pending_open)
                or (
                    not pending_open
                    and (
                        evidence is None
                        or display_view is None
                        or evidence.diagnostic_id != request.diagnostic_id
                        or evidence.state
                        not in {
                            vs_runtime.DISPLAY_CALIBRATION_STATE_ACTIVE,
                            vs_runtime.DISPLAY_CALIBRATION_STATE_UNKNOWN,
                        }
                    )
                )
            ):
                return self.hooks.admission(
                    command_id,
                    error="active display calibration identity is unavailable",
                )
            backend = self._active_backend or self.backends.get("visual_stimulus")
            if backend is None:
                return self.hooks.admission(
                    command_id, error="Visual Stimulus coordinator unavailable"
                )
            revision = (
                pending[1] if pending_open and pending else self.configuration.revision
            )
            output_ids = (
                pending[5]
                if pending_open and pending is not None
                else frozenset(item.output_id for item in display_view.outputs)
                if display_view is not None
                else frozenset()
            )
            if not output_ids:
                return self.hooks.admission(
                    command_id, error="calibration output identity is unavailable"
                )
            deadline = (
                self.clock()
                + self.limits.current.setup_ns
                + self.limits.current.recovery_ns
            )
            dispatch = svc.VisualStimulusDisplayCalibrationCloseRequest(
                command_id=command_id,
                issuer=pb.ProcessIdentity(
                    role="controller", generation=self.generation
                ),
                target=backend.context,
                configuration_revision=revision,
                diagnostic_id=request.diagnostic_id,
                deadline_monotonic_ns=deadline,
            )
            try:
                await asyncio.wait_for(
                    self._dispatch_lock.acquire(),
                    max(0, (deadline - self.clock()) / 1e9),
                )
            except TimeoutError:
                return self.hooks.admission(
                    command_id, error="calibration dispatch deadline expired"
                )
            self._active_backend = backend
            self._active_backend_context = pb.BackendContext.FromString(
                backend.context.SerializeToString()
            )
            try:
                self.hooks.operation(
                    command_id,
                    "CloseDisplayCalibration",
                    progress="renderer closure pending",
                )
            except RuntimeError as exc:
                self._dispatch_lock.release()
                return self.hooks.admission(command_id, error=str(exc))
            self.device.calibration_pending = (
                command_id,
                revision,
                deadline,
                request.diagnostic_id,
                vs_runtime.DISPLAY_CALIBRATION_STATE_IDLE,
                output_ids,
            )
            self.projections.expect_display(command_id, revision)
            self.hooks.publish()
        rpc_task: asyncio.Task[pb.CommandAdmission] | None = None
        try:
            rpc_task = asyncio.create_task(
                backend.close_display_calibration(dispatch, deadline_ns=deadline)
            )
            self._track_backend_call(rpc_task)
            await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        finally:
            if self._dispatch_lock.locked():
                self._dispatch_lock.release()
        assert rpc_task is not None
        try:
            reply = await asyncio.wait_for(
                asyncio.shield(rpc_task),
                max(0, (deadline - self.clock()) / 1e9),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._admission_failed(command_id, str(exc))
            return self.hooks.admission(command_id, error=str(exc))
        if reply.result != pb.COMMAND_RESULT_ACCEPTED:
            message = reply.failure.message or "renderer rejected calibration closure"
            await self._admission_failed(command_id, message)
            return self.hooks.admission(command_id, error=message)
        self.hooks.spawn(self._timeout(command_id, deadline))
        return self.hooks.admission(command_id)

    def _evidence(self) -> vs_runtime.DisplayCalibrationEvidence | None:
        view = self.projections.display
        if view is None or not view.HasField("calibration"):
            return None
        return view.calibration

    async def owner_lost(self) -> None:
        """Close the exact sessionless diagnostic under one retained recovery bound."""
        async with self.lifecycle.lock:
            if self._owner_loss_deadline_ns is None:
                self._owner_loss_deadline_ns = (
                    self.clock() + self.limits.current.recovery_ns
                )
            deadline = self._owner_loss_deadline_ns
            pending = self.device.calibration_pending
            if pending is not None and pending[4] == (
                vs_runtime.DISPLAY_CALIBRATION_STATE_IDLE
            ):
                pending_command_id = pending[0]
                diagnostic_id = pending[3]
                revision = pending[1]
                output_ids = pending[5]
                wait_for_close = True
            else:
                evidence = self._evidence()
                display = self.projections.display
                if pending is not None and pending[4] == (
                    vs_runtime.DISPLAY_CALIBRATION_STATE_ACTIVE
                ):
                    diagnostic_id = pending[3]
                    revision = pending[1]
                    output_ids = pending[5]
                elif (
                    evidence is not None
                    and display is not None
                    and evidence.state
                    in {
                        vs_runtime.DISPLAY_CALIBRATION_STATE_ACTIVE,
                        vs_runtime.DISPLAY_CALIBRATION_STATE_UNKNOWN,
                    }
                    and evidence.controller_generation == self.generation
                    and evidence.configuration_revision == self.configuration.revision
                    and display.backend.backend_name == "visual_stimulus"
                    and display.source.role == "visual_stimulus"
                    and display.source.generation == display.backend.backend_generation
                ):
                    diagnostic_id = evidence.diagnostic_id
                    revision = evidence.configuration_revision
                    output_ids = frozenset(item.output_id for item in display.outputs)
                else:
                    return
                pending_command_id = ""
                wait_for_close = False
            backend = self._active_backend
            backend_context = self._active_backend_context
            if (
                backend is None
                or backend_context is None
                or self.backends.get("visual_stimulus") is not backend
                or backend.context != backend_context
                or revision != self.configuration.revision
                or not diagnostic_id
                or not output_ids
                or self.clock() >= deadline
            ):
                return
            if not wait_for_close:
                command_id = str(uuid4())
                try:
                    self.hooks.operation(
                        command_id,
                        "CloseDisplayCalibration",
                        progress="control-loss closure pending",
                    )
                except RuntimeError:
                    return
                self.device.calibration_blocked = True
                self.device.calibration_pending = (
                    command_id,
                    revision,
                    deadline,
                    diagnostic_id,
                    vs_runtime.DISPLAY_CALIBRATION_STATE_IDLE,
                    output_ids,
                )
                self.projections.expect_display(command_id, revision)
                self.hooks.publish()
                pending_command_id = command_id
                dispatch = svc.VisualStimulusDisplayCalibrationCloseRequest(
                    command_id=command_id,
                    issuer=pb.ProcessIdentity(
                        role="controller", generation=self.generation
                    ),
                    target=backend_context,
                    configuration_revision=revision,
                    diagnostic_id=diagnostic_id,
                    deadline_monotonic_ns=deadline,
                )
        if wait_for_close:
            await self._wait_owner_loss_close(
                pending_command_id, diagnostic_id, deadline
            )
            return
        try:
            await asyncio.wait_for(
                self._dispatch_lock.acquire(),
                max(0, (deadline - self.clock()) / 1e9),
            )
        except TimeoutError:
            return
        rpc_task: asyncio.Task[pb.CommandAdmission] | None = None
        try:
            if self.clock() < deadline:
                rpc_task = asyncio.create_task(
                    backend.close_display_calibration(dispatch, deadline_ns=deadline)
                )
                self._track_backend_call(rpc_task)
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        finally:
            if self._dispatch_lock.locked():
                self._dispatch_lock.release()
        if rpc_task is None:
            return
        try:
            reply = await asyncio.wait_for(
                asyncio.shield(rpc_task),
                max(0, (deadline - self.clock()) / 1e9),
            )
        except Exception as exc:
            self.hooks.complete_operation(
                pending_command_id,
                success=False,
                progress="control-loss closure unresolved",
                error=str(exc),
            )
            return
        if reply.result != pb.COMMAND_RESULT_ACCEPTED:
            self.hooks.complete_operation(
                pending_command_id,
                success=False,
                progress="control-loss closure rejected",
                error=reply.failure.message or "renderer rejected exact closure",
            )
            return
        await self._wait_owner_loss_close(pending_command_id, diagnostic_id, deadline)

    async def _wait_owner_loss_close(
        self, command_id: str, diagnostic_id: str, deadline_ns: int
    ) -> None:
        loop = asyncio.get_running_loop()
        wall_deadline = loop.time() + max(0, (deadline_ns - self.clock()) / 1e9)
        while self.clock() < deadline_ns and loop.time() < wall_deadline:
            async with self.lifecycle.lock:
                evidence = self._evidence()
                pending = self.device.calibration_pending
                if pending is None or pending[0] != command_id:
                    if (
                        evidence is not None
                        and evidence.diagnostic_id == diagnostic_id
                        and evidence.state == vs_runtime.DISPLAY_CALIBRATION_STATE_IDLE
                        and evidence.HasField("idle")
                        and evidence.idle
                        and evidence.HasField("resources_closed")
                        and evidence.resources_closed
                    ):
                        self._active_backend = None
                        self._active_backend_context = None
                        self._owner_loss_deadline_ns = None
                    return
            await asyncio.sleep(min(0.01, max(0, wall_deadline - loop.time())))

    def _track_backend_call(self, task: asyncio.Task[pb.CommandAdmission]) -> None:
        self._inflight_backend_calls.add(task)

        def finished(completed: asyncio.Task[pb.CommandAdmission]) -> None:
            self._inflight_backend_calls.discard(completed)
            if not completed.cancelled():
                completed.exception()

        task.add_done_callback(finished)

    async def _admission_failed(
        self, command_id: str, message: str, *, rejected: bool = False
    ) -> None:
        async with self.lifecycle.lock:
            pending = self.device.calibration_pending
            if pending is not None and pending[0] == command_id:
                self.hooks.complete_operation(
                    command_id,
                    success=False,
                    progress="calibration admission failed",
                    error=message,
                )
                if (
                    rejected
                    and pending[4] == vs_runtime.DISPLAY_CALIBRATION_STATE_ACTIVE
                ):
                    self.device.calibration_blocked = False
                    self.device.calibration_pending = None
                    self.projections.expected_display = None
                elif rejected:
                    self.device.calibration_pending = None
                    self.projections.expected_display = None
                self.hooks.publish()

    async def _timeout(self, command_id: str, deadline_ns: int) -> None:
        await asyncio.sleep(max(0, (deadline_ns - self.clock()) / 1e9))
        async with self.lifecycle.lock:
            pending = self.device.calibration_pending
            if pending is not None and pending[0] == command_id:
                self.hooks.complete_operation(
                    command_id,
                    success=False,
                    progress="calibration evidence timed out",
                    error="exact renderer state and closure evidence missing",
                )
                # Retain the exact diagnostic identity when Open or Close
                # evidence is absent; control loss must still be able to issue
                # one bounded exact Close, and Setup stays blocked.
                if pending[4] == vs_runtime.DISPLAY_CALIBRATION_STATE_IDLE:
                    self.device.calibration_pending = None
                    self.projections.expected_display = None
                self.hooks.publish()
