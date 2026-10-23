"""E05 Setup execution, preparation gates and operator prompts."""

from __future__ import annotations

import asyncio
import shutil
import uuid
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.operations import ControlOperations
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.incident.registry import IncidentRegistry
from cephvr.controller.lifecycle.evidence_wait import EvidenceWaiter
from cephvr.controller.lifecycle.handoffs import PreparationHandoffs
from cephvr.controller.lifecycle.preparation_context import PreparationContext
from cephvr.controller.lifecycle.setup_resolution import SetupResolution
from cephvr.controller.ports import SpikeGLXPort, SupervisorPort
from cephvr.controller.state import (
    Attempt,
    ControlState,
    IncidentState,
    LifecycleState,
    LimitsState,
    SupervisorState,
)
from cephvr.shared.deadlines import remaining_seconds
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
        control_operations: ControlOperations,
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
        late_cleanup: Callable[[Attempt], Coroutine[Any, Any, None]],
        spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]],
    ) -> None:
        self.lifecycle = lifecycle
        self.control = control
        self.supervisor_state = supervisor_state
        self.incident_state = incident_state
        self.limits = limits
        self.clock = clock
        self.control_operations = control_operations
        self.publisher = publisher
        self.reservation_started = reservation_started
        self.spikeglx = spikeglx
        self.supervisor = supervisor
        self.preparation_context = preparation_context
        self.evidence_waiter = evidence_waiter
        self.handoffs = handoffs
        self.resolution = SetupResolution(
            clock=clock,
            preparation_context=preparation_context,
            evidence_waiter=evidence_waiter,
            validators=validators,
            display_validator=display_validator,
            output_planner=output_planner,
        )
        self.max_incident_bytes = max_incident_bytes
        self.cancel_attempt = cancel_attempt
        self.late_cleanup = late_cleanup
        self.spawn = spawn

    async def run_setup(self, attempt: Attempt, command_id: str, deadline: int) -> None:
        try:
            await self._action(command_id, "Checking output folder…")
            retained_deadline = await self._reserve_output(
                attempt, command_id, deadline
            )
            if retained_deadline is None:
                return
            deadline, supervisor = await self._prepare_participants(
                attempt, command_id, retained_deadline
            )
            await self._action(command_id, "Resolving outputs…")
            await self.resolution.resolve_settings_and_outputs(attempt, deadline)
            await self._action(command_id, "Registering outputs…")
            await self._register_final_context(
                attempt, command_id, deadline, supervisor
            )
            await self._publish_ready(attempt, command_id)
        except Exception as exc:
            await self.fail_setup(attempt, command_id, str(exc))

    async def _action(self, command_id: str, action: str) -> None:
        async with self.lifecycle.lock:
            self.control_operations.update_progress(command_id, action)
            self.publisher.publish()

    async def _reserve_output(
        self, attempt: Attempt, command_id: str, deadline: int
    ) -> int | None:
        """Check space, resolve listed collisions, and register the live reservation."""
        if not attempt.reservation.persistent:
            return deadline
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
            extended = await self._prompt_extending_deadline(
                attempt, command_id, f"{reason}; Continue or Cancel Setup", deadline
            )
            if extended is None:
                return None
            deadline = extended
            attempt.overrides.append(
                {"check": "recording_space", "free_bytes": free, "reason": reason}
            )
        acquire = asyncio.create_task(asyncio.to_thread(attempt.reservation.acquire))
        attempt.reservation_acquire_task = acquire

        def acquired(task: asyncio.Task[list[Path]]) -> None:
            # A timed-out thread still owns the exact attempt; never lose its lock.
            if not task.cancelled():
                task.exception()
            if attempt.cancel_requested:
                self.spawn(self.late_cleanup(attempt))

        acquire.add_done_callback(acquired)
        conflicts = await asyncio.wait_for(
            asyncio.shield(acquire), remaining_seconds(deadline, clock=self.clock)
        )
        if attempt.cancel_requested or self.lifecycle.attempt is not attempt:
            raise RuntimeError("Setup retired during reservation acquisition")
        if conflicts:
            listed = [str(path) for path in conflicts]
            extended = await self._prompt_extending_deadline(
                attempt,
                command_id,
                "Existing output files: "
                + ", ".join(listed)
                + "; Continue deletes exactly these files or Cancel preserves them",
                deadline,
            )
            if extended is None:
                return None
            deadline = extended
            await asyncio.wait_for(
                asyncio.to_thread(attempt.reservation.resolve_collisions, conflicts),
                remaining_seconds(deadline, clock=self.clock),
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
                remaining_seconds(deadline, clock=self.clock),
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

    async def _prompt_extending_deadline(
        self, attempt: Attempt, command_id: str, explanation: str, deadline: int
    ) -> int | None:
        """Prompt; extend the Setup deadline by the wait, or cancel and return None."""
        choice, wait_ns = await self.setup_prompt(attempt, command_id, explanation)
        deadline += wait_ns
        attempt.setup_deadline_ns += wait_ns
        if choice == "cancel":
            await self.cancel_attempt(attempt)
            return None
        return deadline

    async def _prepare_participants(
        self, attempt: Attempt, command_id: str, deadline: int
    ) -> tuple[int, SupervisorPort]:
        """Confirm paired ephys, preliminary authority, backend Setup and Ready."""
        if attempt.paired:
            await self._action(command_id, "Preparing SpikeGLX…")
            await self._prepare_spikeglx(attempt, deadline)
        await self._action(command_id, "Registering backends…")
        supervisor = await self._register_preliminary_context(
            attempt, command_id, deadline
        )
        closed_loop_handoff = (
            attempt.handoff is not None and attempt.handoff.closed_loop
        )
        for name in attempt.required:
            attempt.setup_operations.setdefault(name, str(uuid.uuid4()))
        if "acquisition" in attempt.required:
            await self._action(command_id, "Preparing cameras…")
        await self._setup_acquisition(attempt, deadline)
        if any(name != "acquisition" for name in attempt.required):
            await self._action(command_id, "Preparing backends…")
        await self._setup_other_backends(attempt, deadline, closed_loop_handoff)
        if attempt.handoff is not None:
            await self.handoffs.complete_preparation_handoff(attempt, deadline)
        await self._action(command_id, "Waiting for backends…")
        if await self.evidence_waiter.wait_lifecycle_with_recovery(
            attempt, "setup_ready", frozenset(attempt.required), deadline
        ):
            deadline += self.limits.current.recovery_ns
        return deadline, supervisor

    async def _prepare_spikeglx(self, attempt: Attempt, deadline: int) -> None:
        """Prepare the paired SpikeGLX run and validate its readback identity."""
        assert self.spikeglx is not None
        expected_run = attempt.reservation.session_directory.name
        preparation = await asyncio.wait_for(
            self.spikeglx.prepare(
                attempt.prepared.configuration, attempt.context, expected_run
            ),
            remaining_seconds(deadline, clock=self.clock),
        )
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

    async def _register_preliminary_context(
        self, attempt: Attempt, command_id: str, deadline: int
    ) -> SupervisorPort:
        """Register the preliminary Setup work identity with the supervisor."""
        supervisor = self.supervisor
        if supervisor is None:
            raise RuntimeError("supervisor registration unavailable")
        initial_registration = await asyncio.wait_for(
            supervisor.register_context(
                self.preparation_context.registration(attempt, command_id)
            ),
            remaining_seconds(deadline, clock=self.clock),
        )
        if (
            initial_registration.admission.result != pb.COMMAND_RESULT_ACCEPTED
            or initial_registration.registered.work.session != attempt.context
        ):
            raise RuntimeError(
                "supervisor did not register Setup work identity: "
                + (
                    initial_registration.failure.message
                    or initial_registration.admission.failure.message
                    or "registered work context differs"
                )
            )
        attempt.registered_context = deepcopy(initial_registration.registered)
        return supervisor

    async def _setup_acquisition(self, attempt: Attempt, deadline: int) -> None:
        """Run acquisition Setup first and wait for its resolution evidence."""
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
                remaining_seconds(deadline, clock=self.clock),
            )
            if response.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(
                    f"acquisition rejected Setup: {response.failure.message}"
                )
            await self.evidence_waiter.wait_evidence(
                lambda: attempt.resolution_confirmed, deadline, attempt
            )

    async def _setup_other_backends(
        self, attempt: Attempt, deadline: int, closed_loop_handoff: bool
    ) -> None:
        """Run the remaining backends' Setup in parallel within the deadline."""
        initial = {
            name: backend
            for name, backend in attempt.required.items()
            if name != "acquisition"
            and (name != "visual_stimulus" or not closed_loop_handoff)
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
            remaining_seconds(deadline, clock=self.clock),
        )
        for name, response in zip(initial, responses, strict=True):
            if response.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(f"{name} rejected Setup: {response.failure.message}")

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
            remaining_seconds(deadline, clock=self.clock),
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
            self.control_operations.complete_operation(
                command_id, success=True, progress="Ready"
            )
            self.publisher.publish()

    async def fail_setup(self, attempt: Attempt, command_id: str, error: str) -> None:
        async with self.lifecycle.lock:
            if self.lifecycle.attempt is not attempt:
                return
            attempt.cancel_requested = True
            if attempt.handoff is not None:
                attempt.handoff.retire()
            progress = self.control.operations[command_id].progress
            self.control_operations.complete_operation(
                command_id,
                success=False,
                progress=progress,
                error=error,
                failure_code="SETUP_FAILED",
            )
            self.control.add_warning("controller", error)
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
