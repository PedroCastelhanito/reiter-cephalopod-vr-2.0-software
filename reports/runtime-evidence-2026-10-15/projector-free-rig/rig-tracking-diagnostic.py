import asyncio,dataclasses,hashlib,json
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from cephvr.shared.credentials import default_runtime_root,CredentialStore
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.client.session import HeadlessClient,loopback_channel
from cephvr.control.v1 import services_pb2 as rpc,types_pb2 as pb
from cephvr.acquisition.v1 import camera_pb2
from cephvr.tracking.v1 import services_pb2 as tw
from cephvr.gui.managed_device_commands import dispatch_device_action
from cephvr.gui.tracking_frame_transport import fetch_tracking_diagnostic_frame
out=Path.cwd()/'reports/runtime-evidence-2026-10-15/projector-free-rig';record={'events':[]}
def keep(label,value):
 record['events'].append({'label':label,'value':value});(out/'managed-tracking-diagnostic.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8');print(label,json.dumps(value),flush=True)
def view(x):return MessageToDict(x,preserving_proto_field_name=True)
async def main():
 endpoint=_existing_endpoint(default_runtime_root());record['generation']=endpoint.controller_generation;store=CredentialStore(default_runtime_root(),endpoint.controller_generation);principal=store.provision_client('gui')
 try:
  async with loopback_channel(50051,16_777_216) as channel:
   client=HeadlessClient(channel,principal)
   async with client.control(takeover=True):
    s=client.snapshot
    if s.session.phase!=pb.SESSION_PHASE_CONFIGURATION or s.prompts:raise RuntimeError('Idle configuration without prompts required')
    original=s.configuration_values.current.SerializeToString();settings=pb.TrackingSettings.FromString(next(b.tracking for b in s.configuration_values.current.backends if b.backend_name=='tracking').SerializeToString());settings.input_camera_role=camera_pb2.CAMERA_ROLE_TRACKING
    try:
     keep('preview_start',await asyncio.wait_for(dispatch_device_action(client,'camera',{'role':2,'kind':rpc.CAMERA_COMMAND_KIND_START_PREVIEW,'show_preview':False},principal),40))
     cases=[('image_only',[]),('flow_only',[pb.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW]),('missing_dependencies',[pb.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW,pb.TRACKING_DIAGNOSTIC_STAGE_FLOW_QUALITY,pb.TRACKING_DIAGNOSTIC_STAGE_LOCOMOTION])]
     for label,stages in cases:
      before=client.snapshot;request=rpc.BeginTrackingDiagnosticRequest(command=client.operator_command(),expected_configuration_revision=before.configuration.revision,preview_run_id=before.acquisition_devices.tracking.preview_run_id,selected_stages=stages,diagnostic_settings=settings)
      try:
       outcome=await asyncio.wait_for(client.execute('BeginTrackingDiagnostic',request),50);keep(label+'-begin',dataclasses.asdict(outcome))
       if not outcome.succeeded:raise RuntimeError(outcome.failure)
       for sample in range(3):
        await asyncio.sleep(2);s=client.snapshot;d=s.tracking_diagnostic;keep(label+f'-status-{sample}',view(d));options={'expected_revision':d.configuration_revision,'diagnostic_id':d.diagnostic_id,'preview_run_id':d.preview_run_id,'tracking_endpoint':d.tracking_endpoint,'tracking_generation':d.tracking_process.generation};_,_,data=await fetch_tracking_diagnostic_frame(client,principal,options,connection_epoch=1,max_message_bytes=16_777_216);frame=tw.TrackingDiagnosticFrame.FromString(data);keep(label+f'-frame-{sample}',{'available':frame.available,'reason':frame.unavailable_reason,'source_frame_id':frame.source_frame_id,'receipt_ns':frame.source_host_receipt_ns,'image':view(frame.image),'image_bytes':len(frame.image_bytes),'image_sha256':hashlib.sha256(frame.image_bytes).hexdigest(),'vectors':len(frame.vectors),'labels':[view(x) for x in frame.labels]})
      finally:
       d=client.snapshot.tracking_diagnostic
       if d.diagnostic_id and not d.closed:
        close=rpc.CloseTrackingDiagnosticRequest(command=client.operator_command(),expected_configuration_revision=d.configuration_revision,diagnostic_id=d.diagnostic_id,preview_run_id=d.preview_run_id);keep(label+'-close',dataclasses.asdict(await asyncio.wait_for(client.execute('CloseTrackingDiagnostic',close),50)));keep(label+'-closed_state',view(client.snapshot.tracking_diagnostic))
    finally:
     d=client.snapshot.acquisition_devices.tracking
     if d.device_open or d.preview_run_id or d.cleanup_pending:keep('preview_stop',await asyncio.wait_for(dispatch_device_action(client,'camera',{'role':2,'kind':rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW},principal),40))
     keep('tracking_camera_released',view(client.snapshot.acquisition_devices.tracking));keep('configuration_unchanged',client.snapshot.configuration_values.current.SerializeToString()==original);(out/'managed-tracking-final.pb').write_bytes(client.snapshot.SerializeToString())
 except BaseException as exc:keep('error',str(exc));raise
 finally:store.remove_client(principal)
asyncio.run(main())

