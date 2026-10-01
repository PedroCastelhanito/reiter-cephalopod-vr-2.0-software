"""Register the actual endpoint under the pre-existing supervisor launch record."""

from uuid import uuid4

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.clock import describe_host_clock
from cephvr.visual_stimulus.coordinator.ports import PeerPort

from .bootstrap import WorkerBootstrap


async def register(bootstrap: WorkerBootstrap, supervisor: PeerPort, port: int) -> None:
    if not 0 < port <= 65535:
        raise ValueError("worker registration requires its bound port")
    clock = describe_host_clock()
    endpoint = f"127.0.0.1:{port}"
    result = await supervisor.call(
        "ConfirmLaunch",
        wire.ConfirmLaunchRequest(
            command_id=str(uuid4()),
            launch_command_id=bootstrap.launch_command_id,
            owner=bootstrap.context.owner,
            child=bootstrap.context.worker,
            pid=bootstrap.pid,
            creation_time_100ns=bootstrap.creation_time_100ns,
            endpoint=endpoint,
            host_clock=pb.HostClockDescriptor(
                clock_id=clock.clock_id,
                implementation=clock.implementation,
                monotonic=clock.monotonic,
                adjustable=clock.adjustable,
                resolution_s=clock.resolution_s,
            ),
        ),
        deadline_ns=bootstrap.registration_deadline_ns,
    )
    if (
        not isinstance(result, wire.LaunchReceipt)
        or result.admission.result != pb.COMMAND_RESULT_ACCEPTED
        or result.state.phase != wire.LAUNCH_PHASE_OPERATIONAL
        or result.state.endpoint != endpoint
        or result.state.plan.child != bootstrap.context.worker
    ):
        raise RuntimeError("supervisor did not confirm the exact renderer endpoint")
