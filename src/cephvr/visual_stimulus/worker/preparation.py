"""CPU Setup work and immutable handoff to the graphics owner."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any

from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.deadlines import SetupInactivity, remaining_seconds
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
    inactivity: SetupInactivity
    result: Future[tuple[TrialArtifact, ...]]
    completion: Future[None]
    thread: threading.Thread | None = None
    resource_key: str = "preparation:cpu"
    graphics_input: Future[tuple[PreparedTrial, ...]] = field(default_factory=Future)
    graphics_result: Future[tuple[PreparedTrial, ...]] = field(default_factory=Future)

    @property
    def deadline_ns(self) -> int:
        return self.inactivity.deadline_ns

    def service_graphics(
        self, preparation: PreparationPort, *, cancelled: bool, now_ns: int
    ) -> None:
        """Complete the CPU handoff on the graphics owner, under the current inactivity allowance."""
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
                raise TimeoutError("graphics preparation stopped making progress")
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
    interval = request.session.policies.setup.initial_ns or max(
        1, deadline_ns - clock()
    )
    job = PreparationJob(
        request, SetupInactivity(interval, deadline_ns), Future(), Future()
    )
    progress_lock = threading.Lock()

    def cutoff() -> int:
        return job.deadline_ns

    def wait_graphics() -> tuple[PreparedTrial, ...]:
        while True:
            try:
                return job.graphics_result.result(
                    remaining_seconds(cutoff, clock=clock)
                )
            except TimeoutError:
                if job.graphics_result.done():
                    raise
                if clock() >= cutoff():
                    raise TimeoutError(
                        "graphics preparation stopped making progress"
                    ) from None

    def progress(message: str, stale: tuple[Any, ...] = ()) -> None:
        """`stale`: replaced Fold bundle entries for the operator's keep/delete choice."""
        with progress_lock:
            now = clock()
            if now > cutoff():
                raise TimeoutError("Setup stopped making progress")
            if message == job.inactivity.message:
                return
            sequence = job.inactivity.sequence + 1
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
                        progress=message,
                        progress_sequence=sequence,
                        stale_image_bundles=[
                            pb.StaleImageBundle(
                                bundle_id=entry.directory.name,
                                sources=sorted(entry.sources)[:16],
                            )
                            for entry in stale
                        ],
                    ),
                ),
                now + interval,
            )
            if not job.inactivity.advance(sequence, message, now):
                raise TimeoutError("Setup progress did not renew inactivity")

    def run() -> None:
        try:
            artifacts = preparation.prepare_trials(
                request,
                announce,
                cutoff,
                announce_batch=announce_batch,
                progress=progress,
            )
            if {item.identity.trial_id for item in artifacts} != {
                item.context.trial_id for item in request.session.trials
            }:
                raise ValueError("preparer omitted a required trial")
            job.graphics_input.set_result(artifacts)
            artifacts = wait_graphics()
            result = []
            for index, artifact in enumerate(artifacts, 1):
                progress(f"Serializing prepared trial {index}/{len(artifacts)}")
                if clock() >= cutoff():
                    raise TimeoutError("CPU preparation stopped making progress")
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
            progress("Prepared trials serialized; preparing recording artifacts")
            future = recording.prepare_artifacts(artifacts, cutoff())
            if future is not None:
                future.result(remaining_seconds(cutoff, clock=clock))
            for index, record in enumerate(result, 1):
                progress(f"Publishing prepared trial {index}/{len(result)}")
                artifact, data, handle = record.artifact, record.data, record.handle
                if clock() >= cutoff():
                    raise TimeoutError("recipe publication stopped making progress")
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
                    cutoff(),
                )
                progress(f"Published prepared trial {index}/{len(result)}")
            job.result.set_result(tuple(result))
        except BaseException as exc:
            job.result.set_exception(exc)

    announce(job.resource_key, None)
    job.thread = threading.Thread(
        target=run, name="cephvr-visual-stimulus-preparation", daemon=True
    )
    job.thread.start()
    return job
