"""Exact acquisition-worker safety, cleanup, shutdown and helper reconciliation (E08)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar
from uuid import uuid4

from cephvr.acquisition.identity import (
    FFMPEG_PROBE_ROLE,
    FFMPEG_ROLES,
    camera_for_process_role,
)
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.cleanup_outputs import cleanup_output_discharged
from cephvr.shared.clock import host_time_ns
from cephvr.supervisor.ports import SupervisorOutbound
from cephvr.supervisor.receipts import require_accepted
from cephvr.supervisor.registration import RegistrationCoordinator
from cephvr.supervisor.registry import LIVE_PHASES, LaunchError, LaunchRegistry
from cephvr.supervisor.worker_context import launch_work_matches

_T = TypeVar("_T")
QUERY_TIMEOUT_NS = 2_000_000_000  # per worker query in one reconcile pass


def _is_acquisition_worker_role(role: str) -> bool:
    try:
        camera_for_process_role(role)
    except ValueError:
        return False
    return True


def lifecycle_payload_matches(
    observed: acq.WorkerLifecycleEvidence,
    retained: acq.WorkerLifecycleEvidence,
) -> bool:
    """Require exact immutable evidence, including outputs and revision."""
    return observed.SerializeToString(deterministic=True) == retained.SerializeToString(
        deterministic=True
    )


class AcquisitionWorkerControl:
    """Worker discovery, direct safety commands and exact native-child shutdown proofs."""

    def __init__(
        self,
        *,
        registration: RegistrationCoordinator,
        registry: LaunchRegistry,
        outbound: SupervisorOutbound,
        issuer: types.ProcessIdentity,
        interrupt_commands: dict[tuple[str, str], str],
        cleanup_commands: dict[tuple[str, str], str],
    ) -> None:
        self.registration = registration
        self.registry = registry
        self.outbound = outbound
        self.issuer = types.ProcessIdentity.FromString(
            issuer.SerializeToString(deterministic=True)
        )
        self.interrupt_commands = interrupt_commands
        self.cleanup_commands = cleanup_commands
        self._reconcile_lock = asyncio.Lock()
        # Last failure per helper launch command ID; cleared on release.
        self.helper_errors: dict[str, str] = {}

    def registered_workers(
        self, work: types.WorkContext
    ) -> list[tuple[wire.LaunchState, acq.WorkerContext]]:
        """Resolve only exact registered acquisition descendants for this work."""
        participant = next(
            (
                item
                for item in (
                    self.registration.state.context.required_participants
                    if self.registration.state.context
                    else ()
                )
                if item.backend_name == "acquisition"
            ),
            None,
        )
        if participant is None:
            return []
        results: list[tuple[wire.LaunchState, acq.WorkerContext]] = []
        for launch in self.registry.states(tolerant=True):
            plan = launch.plan
            try:
                camera_role = camera_for_process_role(plan.child.role)
            except ValueError:
                camera_role = None
            if (
                plan.owner.role != participant.backend_name
                or plan.owner.generation != participant.backend_generation
                or camera_role is None
                or launch.phase not in LIVE_PHASES
            ):
                continue
            if not launch_work_matches(plan, work):
                continue
            target = acq.WorkerContext(
                worker=plan.child,
                owner=plan.owner,
                work=work,
                camera=camera_role,
            )
            results.append((launch, target))
        return results

    @staticmethod
    def _worker_command(
        *,
        worker: acq.WorkerContext,
        issuer: types.ProcessIdentity,
        command_id: str | None = None,
    ) -> acq.WorkerCommand:
        resolved_id = command_id or str(uuid4())
        return acq.WorkerCommand(
            command_id=resolved_id,
            issuer=issuer,
            target=worker,
            parent_operation=types.OperationContext(command_id=resolved_id),
        )

    async def interrupt_worker(
        self,
        launch: wire.LaunchState,
        worker: acq.WorkerContext,
        report: wire.InterruptionReport,
        deadline_ns: int,
    ) -> None:
        command = self._worker_command(worker=worker, issuer=self.issuer)
        self.interrupt_commands[(worker.worker.role, worker.worker.generation)] = (
            command.command_id
        )
        request = acq.WorkerInterrupt(
            command=command,
            issued_monotonic_ns=report.issued_monotonic_ns,
            reason=report.reason,
        )
        admission = await self.outbound.interrupt_worker(
            launch, request, deadline_ns=deadline_ns
        )
        require_accepted(admission, "worker interrupt")

    async def cleanup_worker(
        self,
        launch: wire.LaunchState,
        worker: acq.WorkerContext,
        deadline_ns: int,
    ) -> None:
        """Retry exact cleanup, then require exact retained success evidence.

        Returns only when the worker retained a succeeded Cleanup; any other
        outcome raises so the caller cannot mistake it for completion.
        """
        key = (worker.worker.role, worker.worker.generation)
        command_id = self.cleanup_commands.get(key)
        if command_id is None:
            command_id = str(uuid4())
            self.cleanup_commands[key] = command_id
        command = self._worker_command(
            worker=worker, issuer=self.issuer, command_id=command_id
        )
        admission = await self.outbound.cleanup_worker(
            launch, command, deadline_ns=deadline_ns
        )
        require_accepted(admission, "worker cleanup")
        retained = await self.outbound.get_worker_retained_result(
            launch,
            acq.WorkerRetainedResultQuery(
                query=acq.WorkerQuery(target=worker), command_id=command_id
            ),
            deadline_ns=deadline_ns,
        )
        if (
            not retained.found
            or retained.source.worker != worker.worker
            or retained.source.owner != worker.owner
            or retained.source.camera != worker.camera
            or retained.source.work != worker.work
            or not retained.HasField("operation")
            or retained.operation.operation.context.command_id != command_id
            or not retained.operation.operation.complete
            or not retained.operation.operation.HasField("succeeded")
            or not retained.operation.operation.succeeded
        ):
            raise RuntimeError("worker cleanup result is not retained as succeeded")

    async def reconcile_native_helper_exits(self, deadline_ns: int) -> list[str]:
        """Release EOF helpers whose exact camera worker proved closure.

        A helper whose owner worker is absent or CLEANUP_REQUIRED without such
        evidence is released once its job is empty; the returned messages name
        those helpers so the caller can surface unconfirmed cleanup. Runs are
        serialized, one GetState per owner worker and work, queried concurrently.
        """
        async with self._reconcile_lock:
            return await self._reconcile(deadline_ns)

    async def _bounded(self, deadline_ns: int, call: Awaitable[_T]) -> _T:
        limit = min(deadline_ns, host_time_ns() + QUERY_TIMEOUT_NS)
        async with asyncio.timeout(max(0.001, (limit - host_time_ns()) / 1e9)):
            return await call

    async def _reconcile(self, deadline_ns: int) -> list[str]:
        states = self.registry.states(tolerant=True)
        workers = {
            (item.plan.child.role, item.plan.child.generation): item
            for item in states
            if _is_acquisition_worker_role(item.plan.child.role)
            and item.phase in LIVE_PHASES
        }
        helpers = [
            helper
            for helper in states
            if helper.plan.stop_method == "owner_stdin_eof"
            and helper.plan.child.role in FFMPEG_ROLES
            and _is_acquisition_worker_role(helper.plan.owner.role)
            and helper.plan.HasField("work")
            and helper.phase == wire.LAUNCH_PHASE_OPERATIONAL
        ]
        queries: dict[tuple[str, str, bytes], asyncio.Task[acq.WorkerState]] = {}
        for helper in helpers:
            plan = helper.plan
            owner = workers.get((plan.owner.role, plan.owner.generation))
            if owner is None or not owner.HasField("endpoint"):
                continue
            key = (
                plan.owner.role,
                plan.owner.generation,
                plan.work.SerializeToString(deterministic=True),
            )
            if key not in queries:
                target = self._target(owner, plan)
                queries[key] = asyncio.create_task(
                    self._bounded(
                        deadline_ns,
                        self.outbound.get_worker_state(
                            owner,
                            acq.WorkerQuery(target=target),
                            deadline_ns=min(
                                deadline_ns, host_time_ns() + QUERY_TIMEOUT_NS
                            ),
                        ),
                    )
                )
        try:
            await asyncio.gather(*queries.values(), return_exceptions=True)
        except BaseException:
            for task in queries.values():
                task.cancel()
            raise
        unconfirmed: list[str] = []
        for helper in helpers:
            plan = helper.plan
            name = f"ffmpeg:{plan.command_id}"
            owner = workers.get((plan.owner.role, plan.owner.generation))
            owner_live = (
                owner is not None
                and owner.phase == wire.LAUNCH_PHASE_OPERATIONAL
                and owner.HasField("endpoint")
            )
            confirmed = False
            if owner is not None and owner.HasField("endpoint"):
                task = queries[
                    (
                        plan.owner.role,
                        plan.owner.generation,
                        plan.work.SerializeToString(deterministic=True),
                    )
                ]
                failure = task.exception()
                if failure is not None:
                    self.helper_errors[plan.command_id] = (
                        f"GetState failed: {failure!r}"
                    )
                else:
                    try:
                        confirmed = await self._helper_closure_proven(
                            helper, owner, task.result(), deadline_ns
                        )
                    except Exception as exc:
                        self.helper_errors[plan.command_id] = (
                            f"retained result failed: {exc!r}"
                        )
            if confirmed:
                self._release(helper)
            elif not owner_live and self._release(helper, quiet_running=True):
                unconfirmed.append(
                    f"{name} released without worker closure evidence; outputs unconfirmed"
                )
        return unconfirmed

    @staticmethod
    def _target(
        owner: wire.LaunchState, plan: wire.PlanLaunchRequest
    ) -> acq.WorkerContext:
        return acq.WorkerContext(
            worker=owner.plan.child,
            owner=owner.plan.owner,
            work=plan.work,
            camera=camera_for_process_role(plan.owner.role),
        )

    def _release(self, helper: wire.LaunchState, quiet_running: bool = False) -> bool:
        """Release one helper if it is still OPERATIONAL; record why not."""
        command_id = helper.plan.command_id
        try:
            # Re-read: a concurrent path may already have released or blocked it.
            if self.registry.refresh(command_id).phase != wire.LAUNCH_PHASE_OPERATIONAL:
                return False
            self.registry.release(command_id, obligations_met=True)
        except LaunchError as exc:
            if not (quiet_running and exc.code == "PROCESS_STILL_RUNNING"):
                self.helper_errors[command_id] = f"release failed: {exc.code}"
            return False
        self.helper_errors.pop(command_id, None)
        return True

    async def _helper_closure_proven(
        self,
        helper: wire.LaunchState,
        owner: wire.LaunchState,
        state: acq.WorkerState,
        deadline_ns: int,
    ) -> bool:
        """Exact Finished and Cleanup evidence, both confirmed as retained results."""
        plan = helper.plan
        target = self._target(owner, plan)
        is_probe = plan.child.role == FFMPEG_PROBE_ROLE
        finished_evidence: acq.WorkerLifecycleEvidence | None = None
        for evidence in state.lifecycle:
            if (
                evidence.source.worker != target.worker
                or evidence.source.owner != target.owner
                or evidence.source.camera != target.camera
                or evidence.source.work != target.work
                or evidence.WhichOneof("evidence") != "finished"
                or not evidence.finished.activity_stopped
                or (not is_probe and not evidence.finished.outputs)
                or not all(
                    cleanup_output_discharged(output)
                    for output in evidence.finished.outputs
                )
            ):
                continue
            if await self._retained_matches(owner, target, evidence, deadline_ns):
                finished_evidence = evidence
                break
        if finished_evidence is None and not is_probe:
            return False
        finished_outputs = (
            {output.output_key: output for output in finished_evidence.finished.outputs}
            if finished_evidence is not None
            else {}
        )
        if (
            finished_evidence is not None
            and len(finished_outputs) != len(finished_evidence.finished.outputs)
            or not is_probe
            and not finished_outputs
        ):
            return False
        helper_resource = f"ffmpeg:{plan.command_id}"
        for evidence in state.lifecycle:
            if (
                evidence.source.worker != target.worker
                or evidence.source.owner != target.owner
                or evidence.source.camera != target.camera
                or evidence.source.work != target.work
                or evidence.WhichOneof("evidence") != "cleanup"
                or not any(
                    item.resource == helper_resource
                    and item.released
                    and not item.failure.ByteSize()
                    for item in evidence.cleanup.resources
                )
            ):
                continue
            cleanup_outputs = {
                output.output_key: output for output in evidence.cleanup.outputs
            }
            if (
                len(cleanup_outputs) != len(evidence.cleanup.outputs)
                or cleanup_outputs.keys() != finished_outputs.keys()
                or any(
                    cleanup_outputs[key].SerializeToString(deterministic=True)
                    != finished_outputs[key].SerializeToString(deterministic=True)
                    for key in finished_outputs
                )
            ):
                continue
            if await self._retained_matches(owner, target, evidence, deadline_ns):
                return True
        return False

    async def _retained_matches(
        self,
        owner: wire.LaunchState,
        target: acq.WorkerContext,
        evidence: acq.WorkerLifecycleEvidence,
        deadline_ns: int,
    ) -> bool:
        kind = evidence.WhichOneof("evidence")
        retained = await self._bounded(
            deadline_ns,
            self.outbound.get_worker_retained_result(
                owner,
                acq.WorkerRetainedResultQuery(
                    query=acq.WorkerQuery(target=target),
                    command_id=evidence.operation.command_id,
                ),
                deadline_ns=min(deadline_ns, host_time_ns() + QUERY_TIMEOUT_NS),
            ),
        )
        return bool(
            retained.found
            and retained.source.worker == target.worker
            and retained.source.work == target.work
            and any(
                item.WhichOneof("evidence") == kind
                and item.source.worker == target.worker
                and item.source.owner == target.owner
                and item.source.camera == target.camera
                and item.source.work == target.work
                and item.operation == evidence.operation
                and lifecycle_payload_matches(evidence, item)
                for item in retained.lifecycle
            )
        )

    async def shutdown_worker(
        self,
        launch: wire.LaunchState,
        worker: acq.WorkerContext,
        deadline_ns: int,
    ) -> None:
        admission = await self.outbound.shutdown_worker(
            launch,
            self._worker_command(worker=worker, issuer=self.issuer),
            deadline_ns=deadline_ns,
        )
        require_accepted(admission, "worker shutdown")
