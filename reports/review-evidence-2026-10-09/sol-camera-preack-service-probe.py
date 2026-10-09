import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from tests.supervisor.support import make_runtime, launch, _launch, _identity, WORKER_ROLE, Context
from cephvr.acquisition.v1 import messages_pb2 as acq, camera_pb2 as camera
from cephvr.control.v1 import services_pb2 as wire, types_pb2 as pb
from cephvr.shared.clock import host_time_ns

async def main():
    for scoped in (False, True):
        with TemporaryDirectory(prefix='cephvr-sol-camera-service-', dir='/tmp') as scratch:
            runtime, native, _, _ = make_runtime(Path(scratch))
            owner, child = _identity('acquisition'), _identity(WORKER_ROLE)
            runtime.credentials[(owner.role, owner.generation)] = 'owner-secret'
            context = Context(owner.role, owner.generation, 'owner-secret')
            if scoped:
                state = _launch(runtime.registry, native, owner, child, 71, python=True)
            else:
                launch(runtime, native, owner, child, 71)
                state = runtime.registry.states()[0]
            source = acq.WorkerContext(worker=child, owner=owner, camera=camera.CAMERA_ROLE_BEHAVIORAL)
            if scoped:
                source.work.CopyFrom(state.plan.work)
            operation_id = str(uuid4())
            evidence = acq.WorkerLifecycleEvidence(source=source, operation=pb.OperationContext(command_id=operation_id), state_revision=1)
            evidence.cleanup.resources.add(resource=f'camera-device:{child.generation}', released=True)
            proof = wire.AcquisitionWorkerCleanupProof(operation=acq.WorkerOperationReport(source=source, operation=pb.OperationState(context=pb.OperationContext(command_id=operation_id), work=source.work, command='Cleanup', complete=True, succeeded=True), state_revision=1), cleanup=evidence)
            request = wire.ConfirmLaunchRequest(command_id=str(uuid4()), launch_command_id=state.plan.command_id, owner=owner, child=child, pid=71, creation_time_100ns=171, acquisition_worker_cleanup=proof)
            first = await runtime.service.ConfirmLaunch(request, context)
            replay = await runtime.service.ConfirmLaunch(request, context)
            assert first.admission.result == replay.admission.result == pb.COMMAND_RESULT_ACCEPTED
            assert first.state.phase == replay.state.phase == wire.LAUNCH_PHASE_OPERATIONAL
            native.jobs[state.containment_job_name] = []
            runtime.health._check_launch_states(runtime.registry.states(), host_time_ns())
            assert runtime.shutdown_state.interruption is None
            query = await runtime.service.GetLaunchState(wire.LaunchQuery(requester=owner, launch_command_id=state.plan.command_id), context)
            assert query.phase == wire.LAUNCH_PHASE_CLEANUP_REQUIRED
            final = await runtime.service.ConfirmLaunch(request, context)
            assert final.admission.result == pb.COMMAND_RESULT_ACCEPTED
            assert final.state.phase == wire.LAUNCH_PHASE_RELEASED
            print({'session_scoped': scoped, 'same_command_id': request.command_id, 'phases': [first.state.phase, replay.state.phase, query.phase, final.state.phase], 'safety_fault': runtime.shutdown_state.interruption is not None})
asyncio.run(main())
