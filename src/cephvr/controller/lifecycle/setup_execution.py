"""E05 Setup execution, preparation gates and operator prompts."""

from __future__ import annotations

import asyncio
import shutil
import uuid
from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from datetime import datetime

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.incident.registry import IncidentRegistry
from cephvr.controller.lifecycle.activity import activity_requirements
from cephvr.controller.lifecycle.evidence_wait import EvidenceWaiter
from cephvr.controller.lifecycle.handoffs import PreparationHandoffs
from cephvr.controller.lifecycle.preparation_context import PreparationContext
from cephvr.controller.metadata.files import safe_component as _safe_component
from cephvr.controller.ports import SpikeGLXPort, SupervisorPort
from cephvr.controller.state import (
    Attempt,
    ControlState,
    IncidentState,
    LifecycleState,
    LimitsState,
    SupervisorState,
)
from cephvr.shared.incidents import (
    IncidentEvidenceError,
    IncidentTopology,
    validate_registered_cleanup,
)


class SetupExecution:
    """Prepare one accepted attempt through Ready under its retained deadline."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        control: ControlState,
        supervisor_state: SupervisorState,
        incident_state: IncidentState,
        limits: LimitsState,
        clock: Callable[[], int],
        publisher: SnapshotPublisher,
        reservation_started: Callable[[Attempt], Awaitable[None]] | None,
        spikeglx: SpikeGLXPort | None,
        supervisor: SupervisorPort | None,
        preparation_context: PreparationContext,
        evidence_waiter: EvidenceWaiter,
        handoffs: PreparationHandoffs,
        validators: Mapping[
            str, Callable[[pb.ExperimentConfiguration], pb.ValidationResult]
        ],
        display_validator: Callable[[str], frozenset[str]] | None,
        output_planner: Callable[
            [pb.PreparedSession, Mapping[str, pb.ReadyReport]], list[pb.OutputPlan]
        ]
        | None,
        max_incident_bytes: int,
        cancel_attempt: Callable[[Attempt], Awaitable[None]],
    ) -> None:
        self.lifecycle = lifecycle
        self.control = control
        self.supervisor_state = supervisor_state
        self.incident_state = incident_state
        self.limits = limits
        self.clock = clock
        self.publisher = publisher
        self.reservation_started = reservation_started
        self.spikeglx = spikeglx
        self.supervisor = supervisor
        self.preparation_context = preparation_context
        self.evidence_waiter = evidence_waiter
        self.handoffs = handoffs
        self.validators = validators
        self.display_validator = display_validator
        self.output_planner = output_planner
        self.max_incident_bytes = max_incident_bytes
        self.cancel_attempt = cancel_attempt

    async def run_setup(self, attempt: Attempt, command_id: str, deadline: int) -> None:
        try:
            retained_deadline = await self._reserve_output(
                attempt, command_id, deadline
            )
            if retained_deadline is None:
                return
            deadline, supervisor = await self._prepare_participants(
                attempt, command_id, retained_deadline
            )
            await self._resolve_settings_and_outputs(attempt, deadline)
            await self._register_final_context(
                attempt, command_id, deadline, supervisor
            )
            await self._publish_ready(attempt, command_id)
        except Exception as exc:
            await self.fail_setup(attempt, command_id, str(exc))

    async def _reserve_output(
        self, attempt: Attempt, command_id: str, deadline: int
    ) -> int | None:
        """Check space, resolve listed collisions, and register the live reservation."""
        try:
            free = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: shutil.disk_usage(attempt.reservation.root).free
                ),
                self.limits.current.space_query_ns / 1e9,
            )
            reason = f"recording destination has {free} free bytes"
        except (TimeoutError, OSError) as exc:
            free = None
            reason = f"recording space unknown: {exc}"
        if free is None or free < self.limits.current.low_space_bytes:
            choice, wait_ns = await self.setup_prompt(
                attempt, command_id, f"{reason}; Continue or Cancel Setup"
            )
            deadline += wait_ns
            attempt.setup_deadline_ns += wait_ns
            if choice == "cancel":
                await self.cancel_attempt(attempt)
                return None
            attempt.overrides.append(
                {"check": "recording_space", "free_bytes": free, "reason": reason}
            )
        conflicts = await asyncio.wait_for(
            asyncio.to_thread(attempt.reservation.acquire),
            max(0, (deadline - self.clock()) / 1e9),
        )
        if conflicts:
            listed = [str(path) for path in conflicts]
            choice, wait_ns = await self.setup_prompt(
                attempt,
                command_id,
                "Existing output files: "
                + ", ".join(listed)
                + "; Continue deletes exactly these files or Cancel preserves them",
            )
            deadline += wait_ns
            attempt.setup_deadline_ns += wait_ns
            if choice == "cancel":
                await self.cancel_attempt(attempt)
                return None
            await asyncio.wait_for(
                asyncio.to_thread(attempt.reservation.resolve_collisions, conflicts),
                max(0, (deadline - self.clock()) / 1e9),
            )
            attempt.overrides.append({"check": "output_conflict", "paths": listed})
        if self.reservation_started is not None:
            async with self.lifecycle.lock:
                if (
                    self.lifecycle.attempt is not attempt
                    or attempt.cancel_requested
                    or self.lifecycle.authority_lost
                ):
                    raise RuntimeError("reservation registration lost Setup authority")
                attempt.reservation_registration_started = True
                attempt.reservation_registered = False
            await asyncio.wait_for(
                self.reservation_started(attempt),
                max(0, (deadline - self.clock()) / 1e9),
            )
            async with self.lifecycle.lock:
                attempt.reservation_registered = True
                if (
                    self.lifecycle.attempt is not attempt
                    or attempt.cancel_requested
                    or self.lifecycle.authority_lost
                ):
                    raise RuntimeError("Setup retired after reservation registration")
        return deadline

    async def _prepare_participants(
        self, attempt: Attempt, command_id: str, deadline: int
    ) -> tuple[int, SupervisorPort]:
        """Confirm paired ephys, preliminary authority, backend Setup and Ready."""
        if attempt.paired:
            assert self.spikeglx is not None
            preparation = await asyncio.wait_for(
                self.spikeglx.prepare(attempt.prepared.configuration, attempt.context),
                max(0, (deadline - self.clock()) / 1e9),
            )
            anchor = datetime.fromisoformat(attempt.prepared.anchor_wall_time)
            expected_run = f"{_safe_component(attempt.prepared.configuration.experiment)}_{_safe_component(attempt.prepared.configuration.subject)}_{anchor.strftime('%Y%m%d')}_{anchor.strftime('%H%M%S')}"
            if (
                not preparation.address.strip()
                or not 1 <= preparation.port <= 65535
                or preparation.run_name != expected_run
                or not preparation.spikeglx_version
                or not preparation.sdk_version
                or not preparation.mapping_id
                or not preparation.data_directory
                or not preparation.streams
            ):
                raise RuntimeError(
                    "SpikeGLX preparation endpoint, run identity or required readback missing"
                )
            attempt.prepared.spikeglx.CopyFrom(preparation)
        supervisor = self.supervisor
        if supervisor is None:
            raise RuntimeError("supervisor registration unavailable")
        initial_registration = await asyncio.wait_for(
            supervisor.register_context(
                self.preparation_context.registration(attempt, command_id)
            ),
            max(0, (deadline - self.clock()) / 1e9),
        )
        if (
            initial_registration.admission.result != pb.COMMAND_RESULT_ACCEPTED
            or initial_registration.registered.work.session != attempt.context
        ):
            raise RuntimeError("supervisor did not register Setup work identity")
        attempt.registered_context = deepcopy(initial_registration.registered)
        closed_loop_handoff = (
            attempt.handoff is not None and attempt.handoff.closed_loop
        )
        for name in attempt.required:
            attempt.setup_operations.setdefault(name, str(uuid.uuid4()))
        acquisition = attempt.required.get("acquisition")
        if acquisition is not None:
            response = await asyncio.wait_for(
                acquisition.setup_session(
                    self.preparation_context.setup_request(
                        attempt,
                        acquisition,
                        attempt.setup_operations["acquisition"],
                    ),
                    deadline_ns=deadline,
                ),
                max(0, (deadline - self.clock()) / 1e9),
            )
            if response.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(
                    f"acquisition rejected Setup: {response.failure.message}"
                )
            await self.evidence_waiter.wait_evidence(
                lambda: attempt.resolution_confirmed, deadline, attempt
            )
        initial = {
            name: backend
            for name, backend in attempt.required.items()
            if name != "acquisition" and (name != "vr" or not closed_loop_handoff)
        }
        responses = await asyncio.wait_for(
            asyncio.gather(
                *(
                    backend.setup_session(
                        self.preparation_context.setup_request(
                            attempt, backend, attempt.setup_operations[name]
                        ),
                        deadline_ns=deadline,
                    )
                    for name, backend in initial.items()
                )
            ),
            max(0, (deadline - self.clock()) / 1e9),
        )
        for name, response in zip(initial, responses, strict=True):
            if response.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(f"{name} rejected Setup: {response.failure.message}")
        if attempt.handoff is not None:
            await self.handoffs.complete_preparation_handoff(attempt, deadline)
        if await self.evidence_waiter.wait_lifecycle_with_recovery(
            attempt, "setup_ready", frozenset(attempt.required), deadline
        ):
            deadline += self.limits.current.recovery_ns
        return deadline, supervisor

    async def _resolve_settings_and_outputs(
        self, attempt: Attempt, deadline: int
    ) -> None:
        """Validate exact resolved settings, display, trial plans and outputs."""
        effective = deepcopy(attempt.prepared.configuration)
        for name in attempt.required:
            ready = attempt.ready[name]
            current = next(
                (item for item in effective.backends if item.backend_name == name),
                None,
            )
            resolved = ready.resolved_settings
            if (
                current is None
                or not current.enabled
                or resolved.backend_name != name
                or not resolved.enabled
                or resolved.WhichOneof("settings") != current.WhichOneof("settings")
            ):
                raise RuntimeError(f"{name} Ready lacks exact resolved settings")
            current.CopyFrom(resolved)
        results = await asyncio.wait_for(
            asyncio.gather(
                *(
                    asyncio.to_thread(validator, effective)
                    for validator in self.validators.values()
                )
            ),
            max(0, (deadline - self.clock()) / 1e9),
        )
        if not results or any(
            not result.completed or not result.valid for result in results
        ):
            raise RuntimeError("resolved effective settings failed pure validation")
        attempt.prepared.configuration.CopyFrom(effective)
        vr = attempt.ready.get("vr")
        if vr is None or len(vr.resolved_trials) != len(attempt.prepared.trials):
            raise RuntimeError("VR did not provide every resolved trial")
        if self.display_validator is None:
            raise RuntimeError("display output validator unavailable")
        vr_settings = next(
            item.vr
            for item in effective.backends
            if item.backend_name == "vr" and item.enabled
        )
        attempt.vr_output_ids = await asyncio.wait_for(
            asyncio.to_thread(self.display_validator, vr_settings.display.profile_json),
            max(0, (deadline - self.clock()) / 1e9),
        )
        if not attempt.vr_output_ids:
            raise RuntimeError("VR resolved display has no required outputs")
        for index, resolved_trial in enumerate(vr.resolved_trials):
            if (
                resolved_trial.context != attempt.prepared.trials[index].context
                or resolved_trial.definition
                != attempt.prepared.trials[index].definition
                or not resolved_trial.HasField("resolved_duration_ns")
                or resolved_trial.resolved_duration_ns < 60_000_000_000
            ):
                raise RuntimeError("VR resolved duration or trial identity invalid")
            attempt.prepared.trials[index].CopyFrom(resolved_trial)
        if self.output_planner is None:
            raise RuntimeError("output reservation planner unavailable")
        outputs = self.output_planner(attempt.prepared, attempt.ready)
        if not outputs:
            raise RuntimeError("required output plan unavailable")
        for name in attempt.required:
            activity_requirements(attempt, name)
        seen: set[str] = set()
        for output in outputs:
            if (
                not output.output_key
                or output.output_key in seen
                or output.trial.session != attempt.context
            ):
                raise RuntimeError("output plan identity or key invalid")
            seen.add(output.output_key)
            attempt.prepared.outputs.add().CopyFrom(output)
        await self.evidence_waiter.wait_evidence(
            lambda: self.preparation_context.catalogues_match_ready(attempt),
            deadline,
            attempt,
        )

    async def _register_final_context(
        self,
        attempt: Attempt,
        command_id: str,
        deadline: int,
        supervisor: SupervisorPort,
    ) -> None:
        """Verify prepared closure and retain the supervisor's final context."""
        context_request = self.preparation_context.registration(attempt, command_id)
        try:
            worker_owners = self.preparation_context.worker_owners(attempt)
            registered_workers = frozenset(
                worker for workers in worker_owners.values() for worker in workers
            )
            topology = IncidentTopology.from_registered(
                context_request.context,
                registered_workers=registered_workers,
                worker_backend={
                    worker: name
                    for name, workers in worker_owners.items()
                    for worker in workers
                },
            )
            zero_resources = frozenset(
                name
                for name in attempt.required
                if not self.supervisor_state.processes[
                    name
                ].last_heartbeat.cleanup_resources
            )
            validate_registered_cleanup(
                context_request.context,
                attempt.ready,
                registered_workers=registered_workers,
                zero_resource_backends=zero_resources,
            )
        except IncidentEvidenceError as exc:
            raise RuntimeError(f"prepared incident closure invalid: {exc}") from exc
        registration = await asyncio.wait_for(
            supervisor.register_context(context_request),
            max(0, (deadline - self.clock()) / 1e9),
        )
        if (
            registration.admission.result != pb.COMMAND_RESULT_ACCEPTED
            or registration.registered.work.session != attempt.context
        ):
            raise RuntimeError("supervisor did not acknowledge exact session context")
        attempt.registered_context = deepcopy(context_request.context)
        attempt.incident_topology = topology
        attempt.incidents = IncidentRegistry(
            attempt.context,
            max_incidents=self.limits.current.max_retained_incidents,
            max_error_ids=256,
            max_bytes=self.max_incident_bytes,
        )
        attempt.cleanup_catalogue_revisions = {
            name: self.supervisor_state.processes[
                name
            ].last_heartbeat.cleanup_resources_revision
            for name in attempt.required
        }

    async def _publish_ready(self, attempt: Attempt, command_id: str) -> None:
        """Commit Ready only while this attempt still owns lifecycle state."""
        async with self.lifecycle.lock:
            if self.lifecycle.attempt is not attempt or attempt.cancel_requested:
                return
            self.lifecycle.session.phase = pb.SESSION_PHASE_READY
            operation = self.control.operations[command_id]
            operation.complete = True
            operation.succeeded = True
            operation.progress = "Ready"
            self.publisher.publish()

    async def fail_setup(self, attempt: Attempt, command_id: str, error: str) -> None:
        async with self.lifecycle.lock:
            if self.lifecycle.attempt is not attempt:
                return
            attempt.cancel_requested = True
            if attempt.handoff is not None:
                attempt.handoff.retire()
            operation = self.control.operations[command_id]
            operation.complete = True
            operation.succeeded = False
            operation.failure.CopyFrom(pb.Failure(code="SETUP_FAILED", message=error))
            self.control.warnings.append(
                pb.Warning(
                    warning_id=str(uuid.uuid4()), component="controller", message=error
                )
            )
            self.publisher.publish()
        await self.cancel_attempt(attempt)

    async def setup_prompt(
        self, attempt: Attempt, command_id: str, explanation: str
    ) -> tuple[str, int]:
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        prompt = pb.Prompt(
            prompt_id=str(uuid.uuid4()),
            setup=attempt.context,
            operation=pb.OperationContext(command_id=command_id),
            explanation=explanation,
            permitted_choices=["continue", "cancel"],
        )
        async with self.lifecycle.lock:
            if self.lifecycle.attempt is not attempt or attempt.cancel_requested:
                raise RuntimeError("Setup attempt retired")
            self.incident_state.prompts[prompt.prompt_id] = (prompt, future, attempt)
            self.publisher.publish()
        since = self.clock()
        try:
            choice = await future
        finally:
            async with self.lifecycle.lock:
                self.incident_state.prompts.pop(prompt.prompt_id, None)
                self.publisher.publish()
        return choice, self.clock() - since
