import asyncio
from types import SimpleNamespace
from uuid import uuid4
from cephvr.acquisition.coordinator.configuration_resolution import ConfigurationResolution
from cephvr.acquisition.coordinator.manual_device_recovery import ManualDeviceRecovery
from cephvr.acquisition.coordinator.manual_preview_pulse import ManualPreviewPulseLifecycle
from cephvr.acquisition.coordinator.manual_preview_transfer import ManualPreviewTransferOwner
from cephvr.acquisition.state import ConfigurationRecord, CoordinatorIdentity, LaunchRecord, PulseRecord, WorkerRecord, WorkerPreview
from cephvr.acquisition.v1 import messages_pb2 as acq, camera_pb2 as camera, runtime_pb2 as runtime
from cephvr.control.v1 import types_pb2 as pb, services_pb2 as wire
from cephvr.shared.commands import CommandLedger

async def run():
    backend=pb.BackendContext(backend_name='acquisition',backend_generation=str(uuid4()))
    process=pb.ProcessIdentity(role='acquisition',generation=backend.backend_generation)
    controller=pb.ProcessIdentity(role='controller',generation=str(uuid4()))
    identity=CoordinatorIdentity(backend,process,controller,pb.ProcessIdentity(role='supervisor',generation=str(uuid4())),pb.ProcessIdentity(role='tracking',generation=str(uuid4())))
    role=camera.CAMERA_ROLE_BEHAVIORAL
    configuration=ConfigurationRecord(pb.AcquisitionSettings(),runtime.AcquisitionFilePolicies(),revision=1)
    lock=asyncio.Lock()
    resolution=ConfigurationResolution(identity=identity,configuration=configuration,controller=SimpleNamespace(),lock=lock,clock=lambda:10)
    operation=await resolution.begin(wire.BackendCommand(command_id='old-edit',issuer=controller,target=backend,parent_operation=pb.OperationContext(command_id='old-edit')),expected_cameras={role},request_revision=1,deadline_ns=1_000_010)
    preview=WorkerPreview(run_id='old-run',configuration_revision=1,allocation_id='owned-ring',resolved_camera=camera.CameraResolvedState(),viewer=pb.ProcessIdentity(role='preview_viewer',generation=str(uuid4())),viewer_transfer_id='owned-transfer',started=True)
    context=acq.WorkerContext(worker=pb.ProcessIdentity(role='acquisition_behavioral_worker',generation=str(uuid4())),owner=process,camera=role)
    ledger=CommandLedger(backend.backend_generation,10000,max_records=32,max_bytes=1000000,result_reservation_bytes=4096)
    class Port:
        async def stop_preview(self, request, *, deadline_ns):
            child=record.child_operations[request.command.command_id]
            child.report=pb.OperationState(context=pb.OperationContext(command_id=child.command_id),command='StopPreview',complete=True,succeeded=True)
            child.report_ingress_ns=10
            preview.started=False
            preview.stopped_event.set(); preview.cleanup_event.set()
            return pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED,command_id=child.command_id)
    record=WorkerRecord(context,Port(),LaunchRecord('launch',context.worker,context.owner,context.work,role,operation,1),preview=preview,commands=ledger)
    workers={role:record}; resources={'owned-ring':SimpleNamespace(ring=None,ledger_key='exact-ledger-key')}
    native=SimpleNamespace(retire=lambda *a,**k:None,may_close_owner=lambda key:False)
    transfers=ManualPreviewTransferOwner(identity=identity,resources=resources,resource_ledger=native,resource_port=SimpleNamespace(),controller=SimpleNamespace(),commands=ledger,find_preview=lambda run:record.preview if record.preview and record.preview.run_id==run else None,clock=lambda:10)
    pulse=PulseRecord()
    recovery=ManualDeviceRecovery(workers=SimpleNamespace(workers=workers),resolution=resolution,pulse=pulse,serial=SimpleNamespace(),clock=lambda:10)
    resolution._pending.device_work_quiescent=lambda:recovery.device_work_quiescent(parent_command_id='old-edit',required_preview_runs={role:'old-run'})
    lifecycle=ManualPreviewPulseLifecycle(identity=identity,configuration=configuration,workers=workers,pulse=pulse,serial=SimpleNamespace(),resources=resources,resource_ledger=native,resource_port=SimpleNamespace(),transfers=transfers,device_status=SimpleNamespace(resolve_camera=lambda *a,**k:None),lock=lock,clock=lambda:10)
    try:
        await lifecycle.pause_for_pulse_change((role,),deadline_ns=1_000_010,parent_operation=operation)
    except TimeoutError:
        print('pause timed out waiting for exact viewer release')
    quiet=recovery.device_work_quiescent(parent_command_id='old-edit',required_preview_runs={role:'old-run'})
    prior=recovery.prior_device_work_quiescent()
    await resolution.cancel(operation)
    await resolution.retire_failed_if_quiescent()
    print('worker_preview_retained=',record.preview is preview,'old_transfer_retained=',transfers._retired.get('old-run') is preview,'resource_owned=',bool(resources),'device_quiescent=',quiet,'prior_quiescent=',prior,'failed_resolution_retained=',resolution._pending is not None)
    if quiet:
        await resolution.begin(wire.BackendCommand(command_id='fresh',issuer=controller,target=backend,parent_operation=pb.OperationContext(command_id='fresh')),expected_cameras=set(),request_revision=1,deadline_ns=900,allow_empty=True,accepted_base_revision=1,accepted_base_settings=configuration.settings,preexisting_work_quiescent=recovery.prior_device_work_quiescent)
        print('fresh real resolution admitted despite unreleased old viewer/ring')

asyncio.run(run())
