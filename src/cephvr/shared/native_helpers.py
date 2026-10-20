"""Exact one-shot controller helper identities and native release receipt."""

from uuid import uuid4

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.encoder_process import WindowsEncoderProcess
from cephvr.shared.deadlines import remaining_seconds
from cephvr.shared.supervised_encoder import SupervisedEncoderLauncher
from cephvr.shared.transport_deadlines import deadline_metadata


def release_native_helper(
    launcher: SupervisedEncoderLauncher,
    plan: wire.PlanLaunchRequest,
    process: WindowsEncoderProcess | None,
    release_commands: dict[str, str],
    *,
    deadline_ns: int,
) -> None:
    """Require the original exact plan/process and supervisor-confirmed empty job."""
    launch_id = plan.command_id
    metadata = (*launcher.owner.metadata(), deadline_metadata(deadline_ns))
    timeout = remaining_seconds(deadline_ns, clock=launcher.clock_ns)
    if timeout <= 0:
        raise TimeoutError("Native helper cleanup missed its original deadline.")
    state = launcher.supervisor.GetLaunchState(
        wire.LaunchQuery(
            requester=launcher.owner_identity, launch_command_id=launch_id
        ),
        metadata=metadata,
        timeout=timeout,
    )
    if state.plan != plan:
        raise RuntimeError("Native helper cleanup resolves to a different launch.")
    if (
        process is not None
        and launch_id == process.launch_id
        and (
            state.pid != process.child.pid
            or state.creation_time_100ns != process.child.creation_time_100ns
        )
    ):
        raise RuntimeError(
            "Native helper cleanup resolves to a different native process."
        )
    if state.phase == wire.LAUNCH_PHASE_RELEASED:
        return
    request = wire.ConfirmLaunchRequest(
        command_id=release_commands.setdefault(launch_id, str(uuid4())),
        launch_command_id=launch_id,
        owner=launcher.owner_identity,
        child=state.plan.child,
        native_cleanup_complete=True,
    )
    if state.HasField("pid"):
        request.pid = state.pid
        request.creation_time_100ns = state.creation_time_100ns
    receipt = launcher.supervisor.ConfirmLaunch(
        request,
        metadata=metadata,
        timeout=remaining_seconds(deadline_ns, clock=launcher.clock_ns),
    )
    if (
        receipt.admission.result != control.COMMAND_RESULT_ACCEPTED
        or receipt.state.phase != wire.LAUNCH_PHASE_RELEASED
    ):
        raise RuntimeError("Native helper cleanup was not confirmed by the supervisor.")
