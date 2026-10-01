"""CPU Setup work and immutable handoff to the graphics owner."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass

from cephvr.control.v1 import types_pb2 as pb
from cephvr.visual_stimulus.compiler import serialize_prepared_trial
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


def begin(
    request: visual_stimulus.WorkerSetup,
    preparation: PreparationPort,
    recording: RecordingPort,
    reports: ReportPort,
    announce: Callable[[str, str | None], None],
    deadline_ns: int,
    clock: Callable[[], int],
) -> PreparationJob:
    job = PreparationJob(request, deadline_ns, Future(), Future())

    def run() -> None:
        try:
            artifacts = preparation.prepare_trials(request, announce, deadline_ns)
            if {item.identity.trial_id for item in artifacts} != {
                item.context.trial_id for item in request.session.trials
            }:
                raise ValueError("preparer omitted a required trial")
            future = recording.prepare_artifacts(artifacts, deadline_ns)
            if future is not None:
                future.result(max(0, (deadline_ns - clock()) / 1e9))
            result = []
            for artifact in artifacts:
                if clock() >= deadline_ns:
                    raise TimeoutError("CPU preparation missed its original deadline")
                data = serialize_prepared_trial(artifact)
                handle = vp.PreparedHandle(
                    prepared_generation=artifact.identity.prepared_generation,
                    configuration_revision=artifact.identity.configuration_revision,
                    model_compatibility=artifact.model_compatibility,
                    compiler_compatibility=artifact.compiler_compatibility,
                    resource_generation=artifact.identity.resource_generation,
                    plan_sha256=hashlib.sha256(data).hexdigest(),
                    plan_bytes=len(data),
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
                result.append(TrialArtifact(artifact, data, handle))
            job.result.set_result(tuple(result))
        except BaseException as exc:
            job.result.set_exception(exc)

    announce(job.resource_key, None)
    job.thread = threading.Thread(
        target=run, name="cephvr-visual-stimulus-preparation", daemon=True
    )
    job.thread.start()
    return job
