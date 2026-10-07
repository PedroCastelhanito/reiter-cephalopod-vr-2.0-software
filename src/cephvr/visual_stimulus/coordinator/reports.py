"""Validate exact worker evidence before promoting aggregate Visual Stimulus facts (V01/E08)."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from uuid import uuid4

from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.commands import CommandLedger
from cephvr.visual_stimulus.recording.recipe import PreparedRecipe
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus
from cephvr.visual_stimulus.v1 import runtime_pb2 as vp

from .ports import PeerPort
from .ready import validate_ready
from .state import Identity, Prepared, State


class Reports:
    def __init__(
        self,
        identity: Identity,
        state: State,
        ledger: CommandLedger,
        controller: PeerPort,
        supervisor: PeerPort,
        clock: Callable[[], int],
    ) -> None:
        self.identity, self.state, self.ledger = identity, state, ledger
        self.controller, self.supervisor, self.clock = controller, supervisor, clock
        self.release_result: Callable[[str, bool], None] | None = None
        self.catalogue_lock = asyncio.Lock()

    async def heartbeat(self, report: pb.HeartbeatReport, ingress_ns: int) -> None:
        async with self.catalogue_lock:
            await self._heartbeat(report, ingress_ns)

    async def _heartbeat(self, report: pb.HeartbeatReport, ingress_ns: int) -> None:
        state = self.state
        if report.source != self.identity.worker or not report.HasField(
            "cleanup_resources_revision"
        ):
            raise ValueError("worker heartbeat source/catalogue missing")
        if state.setup is not None:
            kind = report.work.WhichOneof("work")
            session = (
                report.work.trial.session if kind == "trial" else report.work.session
            )
            if session != state.setup.plan.context:
                previous_report = state.worker_heartbeat
                initial = (
                    previous_report is None
                    and kind is None
                    and not report.cleanup_resources
                )
                unchanged_previous = previous_report is not None and (
                    report.work == previous_report.work
                    and report.cleanup_resources == previous_report.cleanup_resources
                    and report.cleanup_resources_revision
                    == previous_report.cleanup_resources_revision
                )
                if initial or unchanged_previous:
                    # Setup can race an already-sent preceding-scope heartbeat.
                    # It proves only this exact process remains responsive.
                    state.worker_ingress_ns = ingress_ns
                    return
                raise ValueError("worker heartbeat has wrong session")
        previous = {
            x.resource: x for x in state.resources if x.owner == self.identity.worker
        }
        incoming = {x.resource: x for x in report.cleanup_resources}
        if len(incoming) != len(report.cleanup_resources) or any(
            x.owner != self.identity.worker for x in incoming.values()
        ):
            raise ValueError("worker catalogue contains duplicate/foreign resources")
        if not previous.keys() <= incoming.keys() or any(
            incoming[k] != v for k, v in previous.items()
        ):
            raise ValueError("worker catalogue regressed or mutated")
        if state.sealed and incoming != previous:
            raise ValueError("Ready sealed the cleanup catalogue")
        changed = incoming != previous
        prior_heartbeat = state.worker_heartbeat
        if prior_heartbeat is not None and (
            report.cleanup_resources_revision
            < prior_heartbeat.cleanup_resources_revision
            or (
                changed
                and report.cleanup_resources_revision
                <= prior_heartbeat.cleanup_resources_revision
            )
        ):
            raise ValueError("worker catalogue revision regressed or failed to advance")
        resources = [
            x for x in state.resources if x.owner != self.identity.worker
        ] + list(incoming.values())
        revision = state.catalogue_revision + int(changed)
        aggregate = pb.HeartbeatReport(
            source=self.identity.process,
            work=report.work,
            sent_monotonic_ns=self.clock(),
            workers=report.workers,
            continuing_functions=report.continuing_functions,
            cleanup_resources=resources,
        )
        if state.setup is not None:
            aggregate.cleanup_resources_revision = revision
        elif resources:
            raise ValueError("renderer resources precede registered session catalogue")
        lifecycle = report.WhichOneof("lifecycle")
        if lifecycle == "session_phase":
            aggregate.session_phase = report.session_phase
        elif lifecycle == "trial_phase":
            aggregate.trial_phase = report.trial_phase
        else:
            raise ValueError("worker heartbeat lifecycle is missing")
        if report.HasField("active_error"):
            aggregate.active_error.CopyFrom(report.active_error)
        deadline = self.clock() + (
            state.setup.plan.policies.supervisor_registration.initial_ns
            if state.setup
            else 5_000_000_000
        )
        await self.supervisor.receipt(
            "ReportHeartbeat", aggregate, deadline_ns=deadline
        )
        state.resources, state.catalogue_revision = resources, revision
        state.worker_heartbeat = pb.HeartbeatReport.FromString(
            report.SerializeToString()
        )
        state.worker_ingress_ns = ingress_ns

    async def operation(self, report: visual_stimulus.WorkerOperation) -> None:
        link = self.state.links.get(report.operation.context.command_id)
        if link is None or report.source != link.child.target:
            raise ValueError("worker operation does not match a retained command")
        if report.HasField("prepared_artifact"):
            setup = self.state.setup
            if setup is None or link.method != "SetupSession" or self.state.interrupted:
                raise ValueError("artifact outside live Setup")
            data = report.prepared_artifact.prepared_trial_json.encode("utf-8")
            maximum = setup.visual_stimulus_policies.limits.max_prepared_plan_bytes
            if (
                not 0 < len(data) <= maximum
                or hashlib.sha256(data).hexdigest() != report.prepared_artifact.sha256
            ):
                raise ValueError("prepared artifact size/hash mismatch")
            from cephvr.visual_stimulus.config.models.artifact_models import (
                parse_prepared_json,
            )

            parsed = parse_prepared_json(data.decode(), max_bytes=maximum)
            trial = next(
                (
                    t.context
                    for t in setup.plan.trials
                    if t.context == report.prepared_trial
                ),
                None,
            )
            if (
                trial is None
                or parsed.identity.trial_id != trial.trial_id
                or parsed.identity.session_id != trial.session.session_id
                or parsed.identity.renderer_generation
                != self.identity.worker.generation
                or parsed.identity.configuration_revision
                != setup.plan.configuration_revision
            ):
                raise ValueError("prepared artifact identity mismatch")
            handle = vp.PreparedHandle(
                prepared_generation=parsed.identity.prepared_generation,
                configuration_revision=parsed.identity.configuration_revision,
                model_compatibility=parsed.model_compatibility,
                compiler_compatibility=parsed.compiler_compatibility,
                resource_generation=parsed.identity.resource_generation,
                plan_sha256=report.prepared_artifact.sha256,
                plan_bytes=len(data),
            )
            old = self.state.prepared.get(trial.trial_id)
            if old is not None and (old.data != data or old.handle != handle):
                raise ValueError("immutable prepared artifact changed")
            self.ledger.reserve_payload(
                "recipe:" + trial.trial_id,
                len(data),
                work_key=setup.plan.context.session_id,
            )
            self.state.prepared[trial.trial_id] = Prepared(
                trial, data, handle, PreparedRecipe(data, handle.plan_sha256), parsed
            )
        if report.operation.complete:
            result = pb.OperationState.FromString(report.operation.SerializeToString())
            result.context.command_id = link.parent.command_id
            result.work.CopyFrom(link.parent.work)
            self.ledger.complete_executor(
                link.parent.command_id, result.SerializeToString(), self.clock()
            )
            if link.method == "ReleaseTrial" and self.release_result is not None:
                self.release_result(link.parent.work.trial.trial_id, result.succeeded)
            if link.method == "ConfirmRecipePublication":
                if not result.succeeded:
                    self.state.interrupted = True
                    await self.supervisor.receipt(
                        "ReportError",
                        pb.ErrorReport(
                            error_id=str(uuid4()),
                            source=self.identity.process,
                            work=result.work,
                            operation=result.context,
                            occurred_monotonic_ns=self.clock(),
                            failure=result.failure,
                        ),
                        deadline_ns=link.deadline_ns,
                    )
                return
            import asyncio

            deliveries = [
                self.controller.receipt(
                    "ReportLifecycle",
                    pb.LifecycleReport(
                        operation=pb.BackendOperationReport(
                            source=self.identity.backend, operation=result
                        )
                    ),
                    deadline_ns=link.deadline_ns,
                )
            ]
            if not result.succeeded:
                self.state.interrupted = True
                deliveries.append(
                    self.supervisor.receipt(
                        "ReportError",
                        pb.ErrorReport(
                            error_id=str(uuid4()),
                            source=self.identity.process,
                            work=result.work,
                            operation=result.context,
                            occurred_monotonic_ns=self.clock(),
                            failure=result.failure,
                        ),
                        deadline_ns=link.deadline_ns,
                    )
                )
            outcomes = await asyncio.gather(*deliveries, return_exceptions=True)
            for outcome in outcomes:
                if isinstance(outcome, BaseException):
                    raise outcome

    async def lifecycle(self, evidence: visual_stimulus.WorkerLifecycle) -> None:
        if evidence.source != self.identity.worker:
            raise ValueError("wrong worker lifecycle source")
        report = pb.LifecycleReport.FromString(evidence.report.SerializeToString())
        kind = report.WhichOneof("report")
        if kind not in {"ready", "started", "stopped", "finished", "cleanup"}:
            raise ValueError("unsupported worker lifecycle evidence")
        payload = getattr(report, kind)
        operation = (
            payload.operation if kind == "cleanup" else payload.context.operation
        )
        link = self.state.links.get(operation.command_id)
        if link is None:
            raise ValueError("worker lifecycle operation unknown")
        work = payload.work if kind == "cleanup" else payload.context.work
        if work != link.child.target.work:
            raise ValueError("worker lifecycle work mismatch")
        if kind == "cleanup":
            if (
                payload.source != self.identity.worker
                or not payload.trial_activity_stopped
            ):
                raise ValueError("cleanup has no stopped worker proof")
            released = {x.resource: x for x in payload.resources}
            required = {
                x.resource: x
                for x in self.state.resources
                if x.owner == self.identity.worker
            }
            if set(released) != set(required) or any(
                x.HasField("path") != required[k].HasField("path")
                or x.path != required[k].path
                for k, x in released.items()
            ):
                raise ValueError(
                    "worker cleanup does not describe exact native catalogue"
                )
            payload.outputs.extend(self.state.recipe_results.values())
            for resource in self.state.resources:
                if resource.owner == self.identity.process:
                    resolved = all(
                        result.closure
                        in {
                            pb.OUTPUT_CLOSURE_CLOSED,
                            pb.OUTPUT_CLOSURE_FAILED,
                            pb.OUTPUT_CLOSURE_NOT_STARTED,
                        }
                        and result.HasField("artifact_present")
                        for result in self.state.recipe_results.values()
                    )
                    payload.resources.add(resource=resource.resource, released=resolved)
            payload.source.CopyFrom(self.identity.process)
            payload.operation.command_id = link.parent.command_id
            payload.cleanup_resources_revision = self.state.catalogue_revision
        else:
            if payload.context.backend != self.identity.backend:
                raise ValueError("worker evidence backend mismatch")
            payload.context.operation.command_id = link.parent.command_id
        if kind == "ready":
            if self.state.interrupted or not payload.required_checks_passed:
                raise ValueError("worker not Ready")
            setup = self.state.setup
            if (
                setup is None
                or payload.configuration_revision != setup.plan.configuration_revision
            ):
                raise ValueError("Ready revision mismatch")
            validate_ready(payload, work, setup, self.state.prepared)
            payload.cleanup_resources.clear()
            payload.cleanup_resources.extend(self.state.resources)
            self.state.sealed = True
        if kind == "finished":
            recipe = self.state.recipe_results.get(work.trial.trial_id)
            if recipe is None:
                raise ValueError("stimulus log closure not yet established")
            payload.outputs.add().CopyFrom(recipe)
        key = (kind, link.parent.command_id)
        old = self.state.reports.get(key)
        if old is not None and old != report:
            raise ValueError("retained lifecycle evidence changed")
        self.ledger.reserve_payload(
            "report:" + kind + ":" + link.parent.command_id,
            report.ByteSize(),
            work_key=(
                work.trial.trial_id
                if work.WhichOneof("work") == "trial"
                else work.session.session_id
            ),
            priority=kind == "cleanup",
        )
        self.state.reports[key] = report
        if kind == "cleanup":
            self.state.cleanup = pb.CleanupReport.FromString(
                payload.SerializeToString()
            )
            if all(item.released for item in payload.resources) and all(
                item.closure
                in {
                    pb.OUTPUT_CLOSURE_CLOSED,
                    pb.OUTPUT_CLOSURE_FAILED,
                    pb.OUTPUT_CLOSURE_NOT_STARTED,
                }
                and item.HasField("artifact_present")
                for item in payload.outputs
            ):
                scopes = {
                    record.work_key
                    for item in self.state.links.values()
                    if (record := self.ledger.get(item.parent.command_id)) is not None
                }
                for scope in scopes:
                    self.ledger.finalize_work(scope, self.clock())
            # Delivery copies are independent: supervisor failure cannot suppress controller delivery.
            import asyncio

            results = await asyncio.gather(
                self.controller.receipt(
                    "ReportLifecycle", report, deadline_ns=link.deadline_ns
                ),
                self.supervisor.receipt(
                    "ReportLifecycle", report, deadline_ns=link.deadline_ns
                ),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, BaseException):
                    raise result
        else:
            await self.controller.receipt(
                "ReportLifecycle",
                report,
                deadline_ns=self.lifecycle_deadline(kind, payload, link.deadline_ns),
            )

    async def display(self, report: pb.VisualStimulusDisplayView) -> None:
        link = self.state.links.get(report.command_id)
        if (
            link is None
            or link.method
            not in {
                "InitializeDisplay",
                "OpenDisplayCalibration",
                "CloseDisplayCalibration",
                "Cleanup",
                "Shutdown",
                "InterruptSession",
                "CancelSetup",
            }
            or report.source != self.identity.worker
            or report.backend != self.identity.backend
            or report.controller != self.identity.controller
            or report.requested_revision != link.child.target.configuration_revision
        ):
            raise ValueError("display evidence identity/revision mismatch")
        if link.method in {"OpenDisplayCalibration", "CloseDisplayCalibration"}:
            evidence = report.calibration
            outputs = {item.output_id for item in report.outputs}
            active_evidence = self.state.display
            expected_diagnostic = link.diagnostic_id
            if (
                not expected_diagnostic
                and active_evidence is not None
                and active_evidence.HasField("calibration")
            ):
                expected_diagnostic = active_evidence.calibration.diagnostic_id
            if (
                not report.HasField("calibration")
                or evidence.diagnostic_id != expected_diagnostic
                or evidence.controller_generation != self.identity.controller.generation
                or evidence.renderer_generation != self.identity.worker.generation
                or evidence.configuration_revision
                != link.child.target.configuration_revision
                or outputs != link.output_ids
                or len(report.outputs) != len(outputs)
            ):
                raise ValueError(
                    "calibration evidence identity differs from its command"
                )
            if link.method == "OpenDisplayCalibration" and (
                evidence.state == vp.DISPLAY_CALIBRATION_STATE_ACTIVE
                and (not evidence.HasField("presented") or not evidence.presented)
            ):
                raise ValueError("Active calibration lacks presentation evidence")
            if link.method == "CloseDisplayCalibration" and (
                evidence.state == vp.DISPLAY_CALIBRATION_STATE_IDLE
                and (
                    not evidence.HasField("idle")
                    or not evidence.idle
                    or not evidence.HasField("resources_closed")
                    or not evidence.resources_closed
                )
            ):
                raise ValueError("Idle calibration lacks resource-closure evidence")
            if evidence.state not in {
                vp.DISPLAY_CALIBRATION_STATE_ACTIVE,
                vp.DISPLAY_CALIBRATION_STATE_IDLE,
                vp.DISPLAY_CALIBRATION_STATE_UNKNOWN,
            }:
                raise ValueError(
                    "calibration evidence is not a terminal diagnostic state"
                )
        elif link.method in {
            "Cleanup",
            "Shutdown",
            "InterruptSession",
            "CancelSetup",
        } and report.HasField("calibration"):
            evidence = report.calibration
            outputs = {item.output_id for item in report.outputs}
            prior = self.state.display
            if (
                prior is None
                or not prior.HasField("calibration")
                or evidence.diagnostic_id != prior.calibration.diagnostic_id
                or evidence.controller_generation != self.identity.controller.generation
                or evidence.renderer_generation != self.identity.worker.generation
                or evidence.configuration_revision
                != link.child.target.configuration_revision
                or outputs != link.output_ids
                or len(report.outputs) != len(outputs)
                or evidence.state
                not in {
                    vp.DISPLAY_CALIBRATION_STATE_IDLE,
                    vp.DISPLAY_CALIBRATION_STATE_UNKNOWN,
                }
            ):
                raise ValueError("safety-close calibration evidence is not exact")
            if evidence.state == vp.DISPLAY_CALIBRATION_STATE_IDLE and (
                not evidence.HasField("idle")
                or not evidence.idle
                or not evidence.HasField("resources_closed")
                or not evidence.resources_closed
            ):
                raise ValueError("safety-close Idle lacks resource-closure evidence")
        forwarded = pb.VisualStimulusDisplayView.FromString(report.SerializeToString())
        forwarded.command_id = link.parent.command_id
        forwarded.source.CopyFrom(self.identity.process)
        self.state.display = forwarded
        await self.controller.receipt(
            "ReportVisualStimulusDisplay", forwarded, deadline_ns=link.deadline_ns
        )

    def lifecycle_deadline(
        self, kind: str, payload: object, command_deadline: int
    ) -> int:
        setup, release = self.state.setup, self.state.release
        if (
            setup is None
            or release is None
            or kind not in {"started", "stopped", "finished"}
        ):
            return command_deadline
        policies = setup.plan.policies
        if kind == "started":
            return release.start_monotonic_ns + policies.start_evidence_allowance_ns
        cutoff = release.normal_end_monotonic_ns
        for (saved_kind, _), report in self.state.reports.items():
            if (
                saved_kind == "stopped"
                and report.stopped.context.work == release.command.work
            ):
                cutoff = report.stopped.actual_stop_monotonic_ns
        if isinstance(payload, pb.StoppedReport):
            cutoff = payload.actual_stop_monotonic_ns
        return cutoff + (
            policies.stop_evidence_allowance_ns
            if kind == "stopped"
            else policies.trial_finished.initial_ns
        )
