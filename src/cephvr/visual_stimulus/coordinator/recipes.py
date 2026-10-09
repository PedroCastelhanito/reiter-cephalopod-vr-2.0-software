"""Coordinator-owned recipe publication and exact cancellation ownership (V03/V13)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.commands import CommandLedger
from cephvr.shared.deadlines import remaining_seconds
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus

from .ports import PeerPort
from .state import CommandLink, Identity, State


class RecipeOwner:
    def __init__(
        self,
        identity: Identity,
        state: State,
        worker: PeerPort,
        supervisor: PeerPort,
        cancelled: asyncio.Event,
        clock: Callable[[], int],
        ledger: CommandLedger,
    ) -> None:
        self.identity, self.state, self.worker, self.supervisor = (
            identity,
            state,
            worker,
            supervisor,
        )
        self.cancelled, self.clock = cancelled, clock
        self.ledger = ledger
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.plans: dict[str, pb.OutputPlan] = {}
        self.cancelled_trials: set[str] = set()
        self.release_confirmations: dict[str, asyncio.Event] = {}
        self.wake = asyncio.Event()
        self.start_times: dict[str, int] = {}

    def cancel_trial(self, trial_id: str) -> None:
        start = self.start_times.get(trial_id)
        if start is None or self.clock() < start:
            self.cancelled_trials.add(trial_id)
            self.release_confirmations.setdefault(trial_id, asyncio.Event()).set()
        self.wake.set()

    def interrupt(self) -> None:
        for trial_id in self.plans:
            self.cancel_trial(trial_id)

    def confirm_release(self, trial_id: str) -> None:
        self.release_confirmations.setdefault(trial_id, asyncio.Event()).set()

    def release_result(self, trial_id: str, succeeded: bool) -> None:
        if not succeeded:
            self.cancelled_trials.add(trial_id)
            self.wake.set()
        self.confirm_release(trial_id)

    async def prepare(self, setup: wire.SetupSessionRequest, deadline_ns: int) -> None:
        from .obligations import output_plans

        if any(not task.done() for task in self.tasks.values()):
            raise RuntimeError("prior recipe writes remain owned")
        if self.state.resources:
            raise RuntimeError("prior session resources remain owned")
        await self.supervisor.receipt(
            "ReportHeartbeat",
            pb.HeartbeatReport(
                source=self.identity.process,
                work=setup.command.work,
                sent_monotonic_ns=self.clock(),
                session_phase=pb.SESSION_PHASE_SETTING_UP,
                cleanup_resources_revision=0,
            ),
            deadline_ns=deadline_ns,
        )
        self.state.catalogue_revision = 0
        self.tasks.clear()
        self.start_times.clear()
        self.cancelled_trials.clear()
        self.release_confirmations.clear()
        self.wake.clear()
        self.plans = {
            item.trial.trial_id: item
            for item in output_plans(
                self.identity.backend,
                list(setup.plan.trials),
                setup.settings.visual_stimulus.save_visual_stimulus_data,
            )
            if item.output_tag == "stimulus_LOG"
        }
        obligations = [
            pb.ResourceObligation(
                owner=self.identity.process, resource="recipe:" + trial_id
            )
            for trial_id in self.plans
        ]
        resources = [*self.state.resources, *obligations]
        revision = self.state.catalogue_revision + 1
        await self.supervisor.receipt(
            "ReportHeartbeat",
            pb.HeartbeatReport(
                source=self.identity.process,
                work=setup.command.work,
                sent_monotonic_ns=self.clock(),
                session_phase=pb.SESSION_PHASE_SETTING_UP,
                cleanup_resources=resources,
                cleanup_resources_revision=revision,
            ),
            deadline_ns=deadline_ns,
        )
        self.state.resources = resources
        self.state.catalogue_revision = revision

    def scheduled(self, schedule: wire.ScheduleTrialRequest) -> None:
        tid = schedule.command.work.trial.trial_id
        outputs = [
            item for item in schedule.outputs if item.output_tag == "stimulus_LOG"
        ]
        if len(outputs) != 1 or tid not in self.plans:
            raise ValueError("schedule lacks its exact required stimulus log")
        output = outputs[0]
        planned = self.plans[tid]
        if (
            output.output_key != planned.output_key
            or output.trial != planned.trial
            or output.backend != planned.backend
            or output.extension != "json"
            or not output.HasField("path")
        ):
            raise ValueError("stimulus log reservation changed at Schedule")
        self.plans[tid] = pb.OutputPlan.FromString(output.SerializeToString())

    def not_started(self, tid: str) -> None:
        output = self.plans[tid]
        result = pb.OutputResult(
            output_key=output.output_key,
            closure=pb.OUTPUT_CLOSURE_NOT_STARTED,
            artifact_present=False,
        )
        if output.HasField("path"):
            result.path = output.path
        self.state.recipe_results[tid] = result

    def cleanup_results(self) -> tuple[pb.OutputResult, ...]:
        if any(not task.done() for task in self.tasks.values()):
            raise RuntimeError("recipe publication still owns file resources")
        for tid in self.plans:
            if tid not in self.state.recipe_results:
                self.not_started(tid)
        return tuple(self.state.recipe_results[tid] for tid in self.plans)

    def start(
        self,
        release: wire.ReleaseTrialRequest,
        deadline_ns: int,
        release_deadline_ns: int,
    ) -> None:
        tid = release.command.work.trial.trial_id
        self.start_times[tid] = release.start_monotonic_ns
        if tid in self.tasks:
            raise ValueError("recipe release already retained")
        self.tasks[tid] = asyncio.create_task(
            self.publish_after_confirmation(release, deadline_ns, release_deadline_ns)
        )

    async def publish_after_confirmation(
        self,
        release: wire.ReleaseTrialRequest,
        deadline_ns: int,
        release_deadline_ns: int,
    ) -> None:
        tid = release.command.work.trial.trial_id
        confirmed = self.release_confirmations.setdefault(tid, asyncio.Event())
        try:
            async with asyncio.timeout(
                remaining_seconds(release_deadline_ns, clock=self.clock)
            ):
                await confirmed.wait()
        except TimeoutError:
            failure = pb.Failure(
                code="RELEASE_UNCONFIRMED",
                message="renderer Release execution was not confirmed by its original deadline",
            )
            output = self.plans[tid]
            self.state.recipe_results[tid] = pb.OutputResult(
                output_key=output.output_key,
                path=output.path,
                closure=pb.OUTPUT_CLOSURE_UNCONFIRMED,
                failure=failure,
            )
            self.state.interrupted = True
            await self.supervisor.receipt(
                "ReportError",
                pb.ErrorReport(
                    error_id=str(uuid4()),
                    source=self.identity.process,
                    work=release.command.work,
                    operation=pb.OperationContext(
                        command_id=release.command.command_id
                    ),
                    occurred_monotonic_ns=self.clock(),
                    failure=failure,
                ),
                deadline_ns=deadline_ns,
            )
            return
        await self.publish(release, deadline_ns)

    async def drain(self, deadline_ns: int) -> None:
        if self.tasks:
            async with asyncio.timeout(
                remaining_seconds(deadline_ns, clock=self.clock)
            ):
                await asyncio.gather(
                    *(asyncio.shield(task) for task in self.tasks.values())
                )

    async def publish(
        self, release: wire.ReleaseTrialRequest, deadline_ns: int
    ) -> None:
        from cephvr.visual_stimulus.recording.recipe import publish_recipe

        tid = release.command.work.trial.trial_id
        prepared = self.state.prepared[tid]
        output = self.plans[tid]
        while self.clock() < release.start_monotonic_ns:
            if self.cancelled.is_set() or tid in self.cancelled_trials:
                self.not_started(tid)
                return
            try:
                await asyncio.wait_for(
                    self.wake.wait(),
                    remaining_seconds(release.start_monotonic_ns, clock=self.clock),
                )
                self.wake.clear()
            except TimeoutError:
                pass
        if tid in self.cancelled_trials:
            self.not_started(tid)
            return
        publication = visual_stimulus.WorkerRecipePublication(
            command=visual_stimulus.WorkerCommand(
                command_id=str(uuid4()),
                issuer=self.identity.process,
                target=visual_stimulus.WorkerContext(
                    worker=self.identity.worker,
                    owner=self.identity.process,
                    work=release.command.work,
                    configuration_revision=prepared.handle.configuration_revision,
                ),
                parent_operation=pb.OperationContext(
                    command_id=release.command.command_id
                ),
                deadline_monotonic_ns=deadline_ns,
            ),
            prepared=prepared.handle,
            path=output.path,
        )
        parent = wire.BackendCommand(
            command_id=publication.command.command_id,
            issuer=self.identity.process,
            target=self.identity.backend,
            work=release.command.work,
            parent_operation=publication.command.parent_operation,
        )
        result = pb.OutputResult(
            output_key=output.output_key,
            path=output.path,
            closure=pb.OUTPUT_CLOSURE_UNCONFIRMED,
        )
        try:
            # Immutable artifact bytes came from Setup. File work never occupies RPC threads.
            recipe = prepared.recipe
            await asyncio.to_thread(
                publish_recipe,
                Path(output.path),
                Path(output.path).name,
                recipe,
                expected_sha256=prepared.handle.plan_sha256,
                expected_byte_length=prepared.handle.plan_bytes,
                trial_start_host_ns=release.start_monotonic_ns,
                now_host_ns=self.clock(),
            )
            result.closure = pb.OUTPUT_CLOSURE_CLOSED
            result.artifact_present = True
            publication.published = True
        except Exception as exc:
            result.failure.CopyFrom(
                pb.Failure(code="STIMULUS_LOG", message=str(exc)[:2048])
            )
            publication.failure.CopyFrom(result.failure)
        self.state.recipe_results[tid] = result
        try:
            self.ledger.admit(
                parent.command_id,
                publication.SerializeToString(),
                self.clock(),
                work_key=tid,
                deadline_ns=deadline_ns,
            )
            self.state.links[parent.command_id] = CommandLink(
                "ConfirmRecipePublication", parent, publication.command, deadline_ns
            )
            admission = await self.worker.command(
                "ConfirmRecipePublication", publication, deadline_ns=deadline_ns
            )
            self.ledger.complete(
                parent.command_id, admission.SerializeToString(), self.clock()
            )
            if admission.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(admission.failure.message)
            if not publication.published:
                raise RuntimeError(publication.failure.message)
        except Exception as exc:
            await self.supervisor.receipt(
                "ReportError",
                pb.ErrorReport(
                    error_id=str(uuid4()),
                    source=self.identity.process,
                    work=release.command.work,
                    operation=pb.OperationContext(
                        command_id=release.command.command_id
                    ),
                    occurred_monotonic_ns=self.clock(),
                    failure=pb.Failure(
                        code="RECIPE_PUBLICATION", message=str(exc)[:2048]
                    ),
                ),
                deadline_ns=deadline_ns,
            )
