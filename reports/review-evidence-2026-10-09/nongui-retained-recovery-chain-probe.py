import asyncio
from types import SimpleNamespace
from uuid import uuid4
from cephvr.acquisition.coordinator.configuration_resolution import ConfigurationResolution
from cephvr.acquisition.coordinator.manual_device_recovery import ManualDeviceRecovery
from cephvr.acquisition.coordinator.evidence import WorkerEvidenceCoordinator
from cephvr.acquisition.state import ChildOperation, ConfigurationRecord, CoordinatorIdentity, LaunchRecord, PulseRecord, WorkerRecord
from cephvr.acquisition.v1 import messages_pb2 as acq,camera_pb2 as camera,runtime_pb2 as runtime
from cephvr.control.v1 import types_pb2 as pb,services_pb2 as wire
from cephvr.shared.commands import CommandLedger
async def run():
 backend=pb.BackendContext(backend_name='acquisition',backend_generation=str(uuid4()))
 process=pb.ProcessIdentity(role='acquisition',generation=backend.backend_generation)
 controller=pb.ProcessIdentity(role='controller',generation=str(uuid4()))
 identity=CoordinatorIdentity(backend,process,controller,pb.ProcessIdentity(role='supervisor',generation=str(uuid4())),pb.ProcessIdentity(role='tracking',generation=str(uuid4())))
 configuration=ConfigurationRecord(pb.AcquisitionSettings(),runtime.AcquisitionFilePolicies(),revision=1)
 lock=asyncio.Lock(); resolution=ConfigurationResolution(identity=identity,configuration=configuration,controller=SimpleNamespace(),lock=lock,clock=lambda:10)
 operation=await resolution.begin(wire.BackendCommand(command_id='old-edit',issuer=controller,target=backend,parent_operation=pb.OperationContext(command_id='old-edit')),expected_cameras={camera.CAMERA_ROLE_BEHAVIORAL},request_revision=1,deadline_ns=100)
 child=ChildOperation('sdk-child',camera.CAMERA_ROLE_BEHAVIORAL,pb.WorkContext(),operation,'apply_camera',configuration_revision=1,deadline_ns=100)
 context=acq.WorkerContext(worker=pb.ProcessIdentity(role='acquisition_behavioral_worker',generation=str(uuid4())),owner=process,camera=camera.CAMERA_ROLE_BEHAVIORAL)
 result=acq.WorkerRetainedResult(found=True,source=context,admission=pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED,command_id=child.command_id),operation=acq.WorkerOperationReport(source=context,state_revision=1,operation=pb.OperationState(context=pb.OperationContext(command_id=child.command_id),command='ApplyCameraSettings',complete=True,succeeded=False)))
 observed=[]
 class Port:
  async def get_retained_result(self,request,*,deadline_ns):
   assert request.command_id==child.command_id and request.query.target==context
   assert deadline_ns==900 and child.deadline_ns==100
   observed.append((request.command_id,deadline_ns))
   return result
 record=WorkerRecord(context,Port(),LaunchRecord('launch',context.worker,context.owner,context.work,context.camera,operation,1),child_operations={child.command_id:child})
 workers=SimpleNamespace(workers={camera.CAMERA_ROLE_BEHAVIORAL:record})
 ledger=CommandLedger(backend.backend_generation,10000,max_records=8,max_bytes=1000000,result_reservation_bytes=4096)
 evidence=WorkerEvidenceCoordinator(backend=backend,owner=process,settings=configuration.settings,workers=workers.workers,resources={},resource_ledger=SimpleNamespace(),commands=ledger,current_session=lambda:None,controller=SimpleNamespace(),lock=lock,configuration_resolution=resolution)
 recovery=ManualDeviceRecovery(workers=workers,resolution=resolution,pulse=PulseRecord(),clock=lambda:500)
 resolution._pending.device_work_quiescent=lambda:recovery.device_work_quiescent(parent_command_id='old-edit')
 recovery.bind_retained_operation_reconciler(lambda record,child,retained,deadline,ingress:evidence.reconcile_retained_operation(record,child,retained,deadline_ns=deadline,ingress_ns=ingress))
 await resolution.cancel(operation)
 await recovery.recover_failed_device_work(900)
 await resolution.retire_failed_if_quiescent()
 print('actual query observed:',observed,'original execution cutoff:',child.deadline_ns,'terminal retained:',child.report is not None,'pending resolution:',resolution._pending is not None)
 if child.report is None:
  try: await evidence.reconcile_retained_operation(record,child,result,deadline_ns=900,ingress_ns=500)
  except (ValueError,AttributeError) as exc:print('actual reconciler diagnostic:',type(exc).__name__,str(exc))
 else:
  assert resolution._pending is None
  await resolution.begin(wire.BackendCommand(command_id='fresh',issuer=controller,target=backend,parent_operation=pb.OperationContext(command_id='fresh')),expected_cameras=set(),request_revision=1,deadline_ns=900,allow_empty=True,accepted_base_revision=1,accepted_base_settings=configuration.settings,preexisting_work_quiescent=recovery.prior_device_work_quiescent)
  print('fresh real resolution admission succeeded without replaying SDK')
asyncio.run(run())
