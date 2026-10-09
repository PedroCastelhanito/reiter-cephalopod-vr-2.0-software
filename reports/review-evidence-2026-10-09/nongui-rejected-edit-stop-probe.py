import asyncio, tempfile
from pathlib import Path
from tests.controller.test_camera_configuration import _runtime_with_validators, _open_preview, _LiveEditAcquisition, _update
from tests.controller.support_components import bind_ledger, _id
from cephvr.control.v1 import types_pb2 as pb, services_pb2 as svc
from cephvr.acquisition.v1 import runtime_pb2 as acq, camera_pb2 as camera
from cephvr.controller.state import Watch

async def run():
  with tempfile.TemporaryDirectory(prefix='cephvr-astra-rejected-edit-') as directory:
    runtime=_runtime_with_validators(Path(directory)); _open_preview(runtime)
    entry=runtime.configuration_state.current.backends.add(backend_name='acquisition',enabled=True)
    entry.acquisition.tracking.enabled=True; entry.acquisition.tracking.device.device_id='camera-1'
    run_id=_id(); runtime.projections.devices.tracking.preview_run_id=run_id
    calls=[]
    class Backend(_LiveEditAcquisition):
      async def get_retained_result(self, query, *, deadline_ns):
        calls.append('query')
        assert query.command_id==self.request.command.command_id
        return svc.RetainedResult(found=True,backend=self.context,work=pb.WorkContext(),admission=pb.CommandAdmission(result=pb.COMMAND_RESULT_REJECTED,command_id=query.command_id))
      async def execute_camera_command(self, command, *, deadline_ns):
        calls.append('Stop')
        return pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED,command_id=command.command.command_id)
    backend=Backend(runtime,reject=True)
    runtime.configuration_commands.owned_edits.backend=backend
    runtime.acquisition_resolution.backends={'acquisition':backend}
    runtime.acquisition_resolution.authorized=lambda _command:''
    policies=acq.AcquisitionFilePolicies(); policies.cameras.add(camera=camera.CAMERA_ROLE_TRACKING)
    runtime.configuration_commands.owned_edits.file_policy_loader=lambda _: {'acquisition':policies}
    runtime.camera.file_policy_loader=lambda _: {'acquisition':policies}
    runtime.camera.backends['acquisition']=backend
    edit=await runtime.update_configuration(_update(runtime,experiment='e2'))
    print('edit_rejected=',edit.result==pb.COMMAND_RESULT_REJECTED,'retained_missing_status=',[x.device_status is None for x in runtime.device_state.configuration_edit_terminals.values()])
    bind_ledger(runtime)
    client_id,watch_id,generation=_id(),_id(),_id()
    runtime.control.watches[(client_id,watch_id)]=Watch(client_id,watch_id,asyncio.Queue(maxsize=1),runtime.control.revision)
    runtime.control.owner=(client_id,watch_id,generation)
    request=svc.CameraCommandRequest(kind=svc.CAMERA_COMMAND_KIND_STOP_PREVIEW,camera=camera.CAMERA_ROLE_TRACKING,expected_configuration_revision=1,preview_run_id=run_id)
    request.command.controller_generation=runtime.generation
    request.command.operator.command_id=_id(); request.command.operator.client_id=client_id; request.command.operator.control_generation=generation
    result=await runtime.execute_camera_command(request)
    print('exact_stop_result=',result.result,'reason=',result.failure.message,'calls=',calls)
    # Counterfactual removes only rejected edit bookkeeping; same exact run/authority.
    runtime.device_state.configuration_edit_terminals.clear()
    request.command.operator.command_id=_id()
    result=await runtime.execute_camera_command(request)
    print('without_rejected_edit_terminal=',result.result,'calls=',calls)
    for task in tuple(runtime._tasks): task.cancel()
    if runtime._tasks: await asyncio.gather(*tuple(runtime._tasks),return_exceptions=True)
asyncio.run(run())
