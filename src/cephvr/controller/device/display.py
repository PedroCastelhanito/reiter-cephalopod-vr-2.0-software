"""VR Idle display initialization and confirmation."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Mapping
from copy import deepcopy

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
from cephvr.vr.v1 import runtime_pb2 as vr_pb


class DisplayInitialization:
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
        generation: str,
        limits: LimitsState,
        max_operation_records: int,
        clock: Callable[[], int],
        hooks: DeviceHooks,
    ) -> None:
        self.lifecycle = lifecycle
        self.configuration = configuration
        self.control = control
        self.device = device
        self.backends = backends
        self.projections = projections
        self.file_policy_loader = file_policy_loader
        self.display_validator = display_validator
        self.generation = generation
        self.limits = limits
        self.max_operation_records = max_operation_records
        self.clock = clock
        self.hooks = hooks

    async def initialize_display(self) -> pb.CommandAdmission:
        """One startup V19 preparation against the adopted revision, never Setup."""
        command_id = str(uuid.uuid4())
        async with self.lifecycle.lock:
            backend = self.backends.get("vr")
            setting = next(
                (
                    item
                    for item in self.configuration.current.backends
                    if item.backend_name == "vr" and item.enabled
                ),
                None,
            )
            self.hooks.prune_operations()
            if len(self.control.operations) >= self.max_operation_records - 2:
                return self._capacity_failure(command_id)
            if (
                self.lifecycle.authority_lost
                or self.lifecycle.session.shutdown_requested
                or self.lifecycle.session.phase != pb.SESSION_PHASE_CONFIGURATION
                or self.device.display_pending is not None
            ):
                return self.hooks.admission(
                    command_id,
                    error="display initialization unavailable in current phase",
                )
            if (
                backend is None
                or setting is None
                or setting.WhichOneof("settings") != "vr"
                or not setting.vr.display.profile_json
            ):
                self.control.warnings.append(
                    pb.Warning(
                        warning_id=str(uuid.uuid4()),
                        component="vr_display",
                        message="VR display settings or registered coordinator unavailable",
                    )
                )
                self.hooks.publish()
                return self.hooks.admission(
                    command_id, error="VR display settings or coordinator unavailable"
                )
            if self.display_validator is None or self.file_policy_loader is None:
                self.control.warnings.append(
                    pb.Warning(
                        warning_id=str(uuid.uuid4()),
                        component="vr_display",
                        message="display validator or file policy loader unavailable",
                    )
                )
                self.hooks.publish()
                return self.hooks.admission(
                    command_id,
                    error="display validator or file policy loader unavailable",
                )
            revision = self.configuration.revision
            display = deepcopy(setting.vr.display)
        try:
            output_ids, loaded = await asyncio.wait_for(
                asyncio.gather(
                    asyncio.to_thread(self.display_validator, display.profile_json),
                    asyncio.to_thread(self.file_policy_loader, frozenset({"vr"})),
                ),
                self.limits.current.validation_ns / 1e9,
            )
            if not output_ids or len(output_ids) > 64:
                raise ValueError(
                    "display validator returned no bounded required output identities"
                )
            policy = loaded.get("vr")
            if policy is None or policy.DESCRIPTOR != vr_pb.VRFilePolicies.DESCRIPTOR:
                raise ValueError("VR file policies unavailable")
            vr_policy = vr_pb.VRFilePolicies.FromString(policy.SerializeToString())
            if not vr_policy.HasField("limits") or not vr_policy.limits.ListFields():
                raise ValueError("VR resource limits unresolved")
        except (TimeoutError, ValueError, Exception) as exc:
            async with self.lifecycle.lock:
                self.control.warnings.append(
                    pb.Warning(
                        warning_id=str(uuid.uuid4()),
                        component="vr_display",
                        message=f"display settings unavailable: {exc}",
                    )
                )
                self.hooks.publish()
            return self.hooks.admission(
                command_id, error=f"display settings unavailable: {exc}"
            )
        async with self.lifecycle.lock:
            if (
                self.configuration.revision != revision
                or self.lifecycle.session.phase != pb.SESSION_PHASE_CONFIGURATION
                or self.lifecycle.authority_lost
                or self.lifecycle.session.shutdown_requested
            ):
                return self.hooks.admission(
                    command_id, error="display settings changed before dispatch"
                )
            deadline_ns = (
                self.clock()
                + self.limits.current.setup_ns
                + self.limits.current.recovery_ns
            )
            request = svc.VRDisplayInitializationRequest(
                command_id=command_id,
                issuer=pb.ProcessIdentity(
                    role="controller", generation=self.generation
                ),
                target=backend.context,
                configuration_revision=revision,
                display=display,
                limits=vr_policy.limits,
                policies=self.configuration.policies,
                deadline_monotonic_ns=deadline_ns,
            )
            try:
                # Reserve the record first: a capacity failure must leave no display state.
                self.hooks.operation(
                    command_id,
                    "InitializeDisplay",
                    progress="renderer preparation pending",
                )
            except RuntimeError:
                return self._capacity_failure(command_id)
            self.device.display_pending = (
                command_id,
                revision,
                deadline_ns,
                output_ids,
            )
            self.projections.expect_display(command_id, revision)
            self.hooks.publish()
        try:
            reply = await asyncio.wait_for(
                backend.initialize_display(request, deadline_ns=deadline_ns),
                max(0, (deadline_ns - self.clock()) / 1e9),
            )
            if reply.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(
                    reply.failure.message or "renderer rejected display initialization"
                )
        except Exception as exc:
            async with self.lifecycle.lock:
                if (
                    self.device.display_pending is not None
                    and self.device.display_pending[0] == command_id
                ):
                    self.hooks.complete_operation(
                        command_id,
                        success=False,
                        progress="display initialization admission failed",
                        error=str(exc),
                    )
                    self.device.display_pending = None
                    self.projections.expected_display = None
                    self.hooks.publish()
            return self.hooks.admission(command_id, error=str(exc))
        self.hooks.spawn(self._display_timeout(command_id, deadline_ns))
        return self.hooks.admission(command_id)

    def _capacity_failure(self, command_id: str) -> pb.CommandAdmission:
        self.control.warnings.append(
            pb.Warning(
                warning_id=str(uuid.uuid4()),
                component="vr_display",
                message="display initialization not started: retained operation capacity exhausted",
            )
        )
        self.hooks.publish()
        return self.hooks.admission(
            command_id, error="retained operation capacity exhausted"
        )

    async def _display_timeout(self, command_id: str, deadline_ns: int) -> None:
        await asyncio.sleep(max(0, (deadline_ns - self.clock()) / 1e9))
        async with self.lifecycle.lock:
            if (
                self.device.display_pending is not None
                and self.device.display_pending[0] == command_id
            ):
                self.hooks.complete_operation(
                    command_id,
                    success=False,
                    progress="display initialization evidence timed out",
                    error="exact renderer completion missing",
                )
                self.device.display_pending = None
                self.projections.expected_display = None
                self.hooks.publish()
