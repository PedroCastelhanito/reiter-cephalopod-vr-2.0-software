"""CPU Setup work and immutable handoff to the graphics owner."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field

from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.deadlines import remaining_seconds
from cephvr.visual_stimulus.compiler import serialize_prepared_trial
from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus
from cephvr.visual_stimulus.v1 import plan_pb2
from cephvr.visual_stimulus.v1 import runtime_pb2 as vp

from .ports import PreparationPort, RecordingPort, ReportPort
from .state import TrialArtifact


@dataclass
class PreparationJob:
    request: visual_stimulus.WorkerSetup
    deadline_ns: int
    result: Future[tuple[TrialArtifact, ...]]
    completion: Future[None]
    thread: threading.Thread | None = None
    resource_key: str = "preparation:cpu"
    graphics_input: Future[tuple[PreparedTrial, ...]] = field(default_factory=Future)
    graphics_result: Future[tuple[PreparedTrial, ...]] = field(default_factory=Future)

    def service_graphics(
        self, preparation: PreparationPort, *, cancelled: bool, now_ns: int
    ) -> None:
        """Complete the CPU handoff on the graphics owner, under the original bound."""
        if (
            not self.graphics_input.done()
            or self.graphics_result.done()
            or self.result.done()
        ):
            return
        try:
            if cancelled:
                raise InterruptedError("Setup cancelled before graphics preparation")
            if now_ns >= self.deadline_ns:
                raise TimeoutError("graphics preparation missed its original deadline")
            artifacts = preparation.prepare_graphics(self.graphics_input.result())
            self.graphics_result.set_result(artifacts)
        except BaseException as exc:
            self.graphics_result.set_exception(exc)


def begin(
    request: visual_stimulus.WorkerSetup,
    preparation: PreparationPort,
    recording: RecordingPort,
    reports: ReportPort,
    announce: Callable[[str, str | None], None],
    deadline_ns: int,
    clock: Callable[[], int],
    announce_batch: Callable[[tuple[tuple[str, str | None], ...]], None] | None = None,
) -> PreparationJob:
    job = PreparationJob(request, deadline_ns, Future(), Future())

    def run() -> None:
        try:
            artifacts = preparation.prepare_trials(
                request, announce, deadline_ns, announce_batch=announce_batch
            )
            if {item.identity.trial_id for item in artifacts} != {
                item.context.trial_id for item in request.session.trials
            }:
                raise ValueError("preparer omitted a required trial")
            job.graphics_input.set_result(artifacts)
            artifacts = job.graphics_result.result(
                remaining_seconds(deadline_ns, clock=clock)
            )
            result = []
            for artifact in artifacts:
                if clock() >= deadline_ns:
                    raise TimeoutError("CPU preparation missed its original deadline")
                data = serialize_prepared_trial(artifact)
                if (
                    request.policies.limits.HasField("max_prepared_plan_bytes")
                    and len(data) > request.policies.limits.max_prepared_plan_bytes
                ):
                    raise MemoryError("final prepared artifact exceeds its byte limit")
                handle = vp.PreparedHandle(
                    prepared_generation=artifact.identity.prepared_generation,
                    configuration_revision=artifact.identity.configuration_revision,
                    model_compatibility=artifact.model_compatibility,
                    compiler_compatibility=artifact.compiler_compatibility,
                    resource_generation=artifact.identity.resource_generation,
                    plan_sha256=hashlib.sha256(data).hexdigest(),
                    plan_bytes=len(data),
                )
                result.append(TrialArtifact(artifact, data, handle))
            future = recording.prepare_artifacts(artifacts, deadline_ns)
            if future is not None:
                future.result(remaining_seconds(deadline_ns, clock=clock))
            for record in result:
                artifact, data, handle = record.artifact, record.data, record.handle
                if clock() >= deadline_ns:
                    raise TimeoutError(
                        "recipe publication missed its original deadline"
                    )
                source = next(
                    item.context
                    for item in request.session.trials
                    if item.context.trial_id == artifact.identity.trial_id
                )
                reports.confirm(
                    "ReportWorkerOperation",
                    visual_stimulus.WorkerOperation(
                        source=request.command.target,
                        operation=pb.OperationState(
                            context=pb.OperationContext(
                                command_id=request.command.command_id
                            ),
                            command="SetupSession",
                            work=request.command.target.work,
                            complete=False,
                        ),
                        prepared_trial=source,
                        prepared_artifact=plan_pb2.PreparedArtifact(
                            prepared_trial_json=data.decode("utf-8"),
                            sha256=handle.plan_sha256,
                        ),
                    ),
                    deadline_ns,
                )
            job.result.set_result(tuple(result))
        except BaseException as exc:
            job.result.set_exception(exc)

    announce(job.resource_key, None)
    job.thread = threading.Thread(
        target=run, name="cephvr-visual-stimulus-preparation", daemon=True
    )
    job.thread.start()
    return job
