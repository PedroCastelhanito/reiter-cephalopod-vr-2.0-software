"""Join registered native release obligations without promoting unknown outcomes."""

from collections.abc import Callable

from cephvr.control.v1 import types_pb2 as pb
from cephvr.visual_stimulus.rendering.types import ResourceReleaseReport
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus

from .ports import EnginePort, FeedbackPort, PreparationPort, RecordingPort
from .state import DriverState


def cleanup_resources(
    state: DriverState,
    command: visual_stimulus.WorkerCommand,
    *,
    worker: pb.ProcessIdentity,
    deadline_ns: int,
    clock: Callable[[], int],
    recording: RecordingPort,
    preparation: PreparationPort,
    engine: EnginePort,
    feedback: FeedbackPort | None,
    emit: Callable[[pb.LifecycleReport, int], None] | None,
) -> None:
    keys: set[str] = set(state.released_threads)
    failures: list[str] = []
    recording_released = False
    try:
        recorded = recording.cleanup(deadline_ns)
        keys.update(recorded.released)
        failures.extend(recorded.outstanding)
        recording_released = not recorded.outstanding
    except Exception as exc:
        failures.append(str(exc))
    operations: tuple[Callable[[], ResourceReleaseReport], ...] = (
        lambda: (
            feedback.close(deadline_ns)
            if feedback is not None
            else ResourceReleaseReport((), ())
        ),
        lambda: preparation.cleanup(deadline_ns),
    )
    for operation in operations:
        try:
            result = operation()
            keys.update(result.released)
            failures.extend(result.outstanding)
        except Exception as exc:
            failures.append(str(exc))
    # Pending capture tokens still need their GL objects/context to establish a
    # confirmed cancellation. Destroying them here would erase that ownership.
    if recording_released:
        try:
            graphics = engine.cleanup()
            keys.update(graphics.released)
            failures.extend(graphics.outstanding)
            if not graphics.outstanding:
                keys.update(
                    key for key in state.resources if key.startswith("display:")
                )
        except Exception as exc:
            failures.append(str(exc))
    if not keys <= state.resources.keys():
        raise RuntimeError("cleanup returned an unregistered resource")
    cleanup = pb.CleanupReport(
        source=worker,
        work=command.target.work,
        operation=pb.OperationContext(command_id=command.command_id),
        verified_monotonic_ns=clock(),
        trial_activity_stopped=True,
        cleanup_resources_revision=state.catalogue_revision,
    )
    for key, resource in state.resources.items():
        item = cleanup.resources.add(resource=key, released=key in keys)
        if key not in keys:
            item.failure.CopyFrom(
                pb.Failure(
                    code="RESOURCE_UNCONFIRMED",
                    message="native owner did not confirm release",
                )
            )
        if resource.HasField("path"):
            item.path = resource.path
    cleanup.outputs.extend(state.outputs.values())
    if emit is not None:
        emit(pb.LifecycleReport(cleanup=cleanup), deadline_ns)
    elif state.setup is not None:
        raise RuntimeError("registered renderer cleanup requires lifecycle evidence")
    if keys == set(state.resources) and not failures:
        state.setup = None
        state.ready = False
        state.cleaned = True
    else:
        missing = sorted(set(state.resources).difference(keys))
        details = "; ".join(
            [*failures, *(f"release unconfirmed: {key}" for key in missing)]
        )
        raise RuntimeError(f"renderer native cleanup remains unconfirmed: {details}")
