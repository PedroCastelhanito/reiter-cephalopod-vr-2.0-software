"""Validate exact worker evidence before promoting aggregate Visual Stimulus facts (V01/E08)."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from uuid import uuid4

from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.commands import CommandLedger
from cephvr.shared.recording import recording_enabled
from cephvr.shared.software import software_version
from cephvr.visual_stimulus.recording.recipe import PreparedRecipe
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus
from cephvr.visual_stimulus.v1 import runtime_pb2 as vp

from .display import (
    accept_display_report,
    recovered_startup_rejection,
    rejected_calibration_update,
)
from .ports import PeerPort
from .ready import validate_ready
from .state import CommandLink, Identity, Prepared, State


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
        previous_report = state.worker_heartbeat
        previous_kind = (
            previous_report.work.WhichOneof("work")
            if previous_report is not None
            else None
        )
        if (
            state.setup is None
            and previous_report is not None
            and previous_kind in {"session", "trial"}
            and report.work == previous_report.work
            and report.cleanup_resources == previous_report.cleanup_resources
            and report.cleanup_resources_revision
            == previous_report.cleanup_resources_revision
        ):
            # An in-flight prior-scope heartbeat proves responsiveness only.
            state.worker_ingress_ns = ingress_ns
            return
        if state.setup is not None:
            kind = report.work.WhichOneof("work")
            session = (
                report.work.trial.session if kind == "trial" else report.work.session
            )
            if session != state.setup.plan.context:
                retired_session = (
                    previous_report.work.session
                    if previous_report is not None
                    and previous_report.work.WhichOneof("work") == "session"
                    else previous_report.work.trial.session
                    if previous_report is not None
                    and previous_report.work.WhichOneof("work") == "trial"
                    else None
                )
                retired_revision = (
                    state.retired_sessions.get(
                        retired_session.SerializeToString(deterministic=True)
                    )
                    if retired_session is not None
                    else None
                )
                if (
                    kind is None
                    and not report.cleanup_resources
                    and retired_revision == report.cleanup_resources_revision
                ):
                    state.worker_ingress_ns = ingress_ns
                    return
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
            if state.cleanup is not None:
                if previous_report is not None and (
                    report.work == previous_report.work
                    and report.cleanup_resources == previous_report.cleanup_resources
                    and report.cleanup_resources_revision
                    == previous_report.cleanup_resources_revision
                ):
                    state.worker_ingress_ns = ingress_ns
                    return
                raise ValueError(
                    "worker heartbeat changed during cleanup report delivery"
                )
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

    async def operation(
        self, report: visual_stimulus.WorkerOperation, *, ingress_ns: int | None = None
    ) -> None:
        link = self.state.links.get(report.operation.context.command_id)
        if link is None or report.source != link.child.target:
            raise ValueError("worker operation does not match a retained command")
        received = self.clock() if ingress_ns is None else ingress_ns
        if link.setup_inactivity is not None and received > link.deadline_ns:
            raise ValueError("Setup report after inactivity cutoff")
        if not report.operation.complete and report.operation.progress:
            from .setup_progress import relay_setup_progress, stale_bundle_ids

            await relay_setup_progress(
                link,
                report.operation,
                live=not self.state.interrupted and not self.state.sealed,
                ingress_ns=received,
                backend=self.identity.backend,
                controller=self.controller,
            )
            # Only IDs relayed for this Setup may later be deleted (V04).
            self.state.stale_bundles.update(stale_bundle_ids(report.operation))
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

            deliveries = []
            if link.method == "SetupSession":
                deliveries.append(
                    self.controller.receipt(
                        "ReportLifecycle",
                        pb.LifecycleReport(
                            operation=pb.BackendOperationReport(
                                source=self.identity.backend, operation=result
                            )
                        ),
                        deadline_ns=link.deadline_ns,
                    )
                )
            unavailable = recovered_startup_rejection(self.state, link, result)
            rejected_update = rejected_calibration_update(
                self.identity, self.state, link, result
            )
            setup_rejection = link.method == "SetupSession"
            if (
                not result.succeeded
                and not unavailable
                and not setup_rejection
                and not rejected_update
                and link.method != "SetStimulusPreview"
            ):
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
        if evidence.report.WhichOneof("report") == "cleanup":
            async with self.catalogue_lock:
                await self._lifecycle(evidence)
            return
        await self._lifecycle(evidence)

    async def _lifecycle(self, evidence: visual_stimulus.WorkerLifecycle) -> None:
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
        parent_id = link.parent.command_id
        if kind in {"started", "stopped", "finished"}:
            prepared_link = next(
                (
                    item
                    for item in self.state.links.values()
                    if item.method == "PrepareTrial" and item.parent.work == work
                ),
                None,
            )
            if prepared_link is None:
                raise ValueError("trial lifecycle lacks retained PrepareTrial identity")
            parent_id = prepared_link.parent.command_id
        key = (kind, parent_id)
        if kind == "cleanup":
            prior = self.state.worker_reports.get(key)
            if prior is not None:
                if prior != evidence:
                    raise ValueError("immutable worker cleanup evidence changed")
                retained = self.state.reports.get(key)
                if retained is None:
                    raise RuntimeError("retained worker cleanup report is missing")
                await self._deliver_cleanup(retained, link)
                return
            if link.cleanup_finalization_scopes is None:
                work_kind = work.WhichOneof("work")
                session = (
                    work.session
                    if work_kind == "session"
                    else work.trial.session
                    if work_kind == "trial"
                    else None
                )
                link.cleanup_finalization_scopes = self._cleanup_scopes(session)
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
            if self.state.setup is None and work.WhichOneof("work") == "session":
                if self.state.resources:
                    raise ValueError("unprepared session retains native obligations")
                # This session never adopted resources; prior revisions belong
                # to the retired session, not its new supervisor catalogue.
                payload.cleanup_resources_revision = 0
                await self.supervisor.receipt(
                    "ReportHeartbeat",
                    pb.HeartbeatReport(
                        source=self.identity.process,
                        work=work,
                        sent_monotonic_ns=self.clock(),
                        session_phase=pb.SESSION_PHASE_CONFIGURATION,
                        cleanup_resources_revision=0,
                    ),
                    deadline_ns=link.deadline_ns,
                )
        else:
            if payload.context.backend != self.identity.backend:
                raise ValueError("worker evidence backend mismatch")
            payload.context.operation.command_id = parent_id
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
            payload.software_version = software_version()
            self.state.sealed = True
        if kind == "finished" and (
            self.state.setup is None
            or recording_enabled(self.state.setup.plan.configuration.backends)
        ):
            recipe = self.state.recipe_results.get(work.trial.trial_id)
            if recipe is None:
                raise ValueError("stimulus log closure not yet established")
            payload.outputs.add().CopyFrom(recipe)
        old = self.state.reports.get(key)
        if old is not None and old != report:
            raise ValueError("retained lifecycle evidence changed")
        self.ledger.reserve_payload(
            "report:" + kind + ":" + parent_id,
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
            self.ledger.reserve_payload(
                "worker-cleanup:" + parent_id,
                evidence.ByteSize(),
                work_key=(
                    work.trial.session.session_id
                    if work.WhichOneof("work") == "trial"
                    else work.session.session_id
                ),
                priority=True,
            )
            self.state.worker_reports[key] = visual_stimulus.WorkerLifecycle.FromString(
                evidence.SerializeToString()
            )
            self.state.cleanup = pb.CleanupReport.FromString(
                payload.SerializeToString()
            )
            await self._deliver_cleanup(report, link)
        else:
            await self.controller.receipt(
                "ReportLifecycle",
                report,
                deadline_ns=self.lifecycle_deadline(kind, payload, link.deadline_ns),
            )

    async def _deliver_cleanup(
        self, report: pb.LifecycleReport, link: CommandLink
    ) -> None:
        import asyncio

        outcomes = await asyncio.gather(
            self.controller.receipt(
                "ReportLifecycle", report, deadline_ns=link.deadline_ns
            ),
            self.supervisor.receipt(
                "ReportLifecycle", report, deadline_ns=link.deadline_ns
            ),
            return_exceptions=True,
        )
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                raise outcome
            if outcome.result != pb.COMMAND_RESULT_ACCEPTED:
                raise ValueError("lifecycle cleanup report was not accepted")
        self._retire_cleanup(report, link)

    def _retire_cleanup(self, report: pb.LifecycleReport, link: CommandLink) -> None:
        cleanup = report.cleanup
        work = cleanup.work
        if work.WhichOneof("work") != "session" or not self._cleanup_complete(cleanup):
            return
        session_key = work.session.SerializeToString(deterministic=True)
        if session_key in self.state.retired_sessions:
            return
        worker_report = self.state.worker_reports.get(
            ("cleanup", link.parent.command_id)
        )
        empty_revision = cleanup.cleanup_resources_revision
        if worker_report is not None:
            raw_cleanup = worker_report.report.cleanup
            empty_revision = raw_cleanup.cleanup_resources_revision + int(
                bool(raw_cleanup.resources)
            )
        self.state.retired_sessions[session_key] = empty_revision
        for scope in link.cleanup_finalization_scopes or ():
            self.ledger.finalize_work(scope, self.clock())
        if self.state.setup is None or work.session != self.state.setup.plan.context:
            return
        self.state.setup = None
        self.state.prepared.clear()
        self.state.recipe_results.clear()
        self.state.incident_revisions.clear()
        self.state.schedule = None
        self.state.release = None
        self.state.active_trial = None
        self.state.resources.clear()
        self.state.sealed = False

    @staticmethod
    def _link_session(link: CommandLink) -> pb.SessionContext | None:
        work = link.parent.work
        kind = work.WhichOneof("work")
        if kind == "session":
            return work.session
        if kind == "trial":
            return work.trial.session
        return None

    def _cleanup_scopes(self, session: pb.SessionContext | None) -> frozenset[str]:
        display_methods = {
            "InitializeDisplay",
            "OpenDisplayCalibration",
            "UpdateDisplayCalibration",
            "CloseDisplayCalibration",
        }
        scopes: set[str] = set()
        for link in self.state.links.values():
            work_kind = link.parent.work.WhichOneof("work")
            matches_session = (
                session is not None and self._link_session(link) == session
            )
            prior_display = work_kind is None and link.method in display_methods
            record = self.ledger.get(link.parent.command_id)
            if record is not None and (matches_session or prior_display):
                scopes.add(record.work_key)
        return frozenset(scopes)

    @staticmethod
    def _cleanup_complete(payload: pb.CleanupReport) -> bool:
        return (
            payload.trial_activity_stopped
            and all(item.released for item in payload.resources)
            and all(
                item.closure
                in {
                    pb.OUTPUT_CLOSURE_CLOSED,
                    pb.OUTPUT_CLOSURE_FAILED,
                    pb.OUTPUT_CLOSURE_NOT_STARTED,
                }
                and item.HasField("artifact_present")
                for item in payload.outputs
            )
        )

    async def display(self, report: pb.VisualStimulusDisplayView) -> None:
        await accept_display_report(self.identity, self.state, self.controller, report)

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
