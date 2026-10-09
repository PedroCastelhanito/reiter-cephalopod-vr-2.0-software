from cephvr.supervisor.registry import LaunchRegistry
from cephvr.control.v1 import services_pb2 as wire
from tests.supervisor.support import Native, _identity, _launch, WORKER_ROLE
native=Native(); registry=LaunchRegistry(native,15_000_000_000,max_launches=1)
owner=_identity('acquisition')
first=_launch(registry,native,owner,_identity(WORKER_ROLE),1,python=True)
native.jobs[first.containment_job_name]=[]
registry.release(first.plan.command_id,obligations_met=True)
second=_launch(registry,native,owner,_identity(WORKER_ROLE),2,python=True)
native.jobs[second.containment_job_name]=[]
registry.release(second.plan.command_id,obligations_met=True)
replay=registry.plan(first.plan)
print('Replayed immediately after capacity pruning:',wire.LaunchPhase.Name(replay.phase))
print('New native job exists:', replay.containment_job_name in native.jobs)
assert replay.phase==wire.LAUNCH_PHASE_PLANNED
