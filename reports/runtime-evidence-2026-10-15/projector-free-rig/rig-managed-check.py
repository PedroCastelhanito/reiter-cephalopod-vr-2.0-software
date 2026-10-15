import asyncio,dataclasses,json,sys
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from cephvr.shared.credentials import default_runtime_root,CredentialStore
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.client.session import HeadlessClient,loopback_channel
from cephvr.control.v1 import services_pb2 as rpc,types_pb2 as pb
from cephvr.gui.managed_device_commands import dispatch_device_action
out=Path.cwd()/'reports/runtime-evidence-2026-10-15/projector-free-rig'
record={'mode':sys.argv[1],'events':[]}
def keep(label,value):
 record['events'].append({'label':label,'value':value});(out/('managed-'+sys.argv[1]+'.json')).write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8');print(label,json.dumps(value),flush=True)
def view(message):return MessageToDict(message,preserving_proto_field_name=True)
async def main():
 endpoint=_existing_endpoint(default_runtime_root());record['controller_generation']=endpoint.controller_generation;store=CredentialStore(default_runtime_root(),endpoint.controller_generation);principal=store.provision_client('cli')
 try:
  async with loopback_channel(50051,16_777_216) as channel:
   client=HeadlessClient(channel,principal)
   async with client.control(takeover=True):
    state=client.snapshot;keep('initial_session',view(state.session))
    if state.session.phase!=pb.SESSION_PHASE_CONFIGURATION or state.prompts:raise RuntimeError('Idle Configuration without prompts required')
    original=state.configuration_values.current.SerializeToString();(out/('managed-'+sys.argv[1]+'-before.pb')).write_bytes(state.SerializeToString())
    if sys.argv[1]=='shutdown':
     keep('shutdown',dataclasses.asdict(await asyncio.wait_for(client.execute('ShutdownApplication'),90)));return
    if sys.argv[1]=='mcu':
     keep('connect',await asyncio.wait_for(dispatch_device_action(client,'mcu',{'kind':rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT},principal),20));keep('mcu',view(client.snapshot.microcontroller))
    elif sys.argv[1]=='idle_controller_loss':
     for name in ['behavioral','tracking','eye_tracking']:
      d=getattr(client.snapshot.acquisition_devices,name)
      if d.device_open or d.preview_run_id or d.cleanup_pending:raise RuntimeError('Idle fault check requires every camera released')
     identity=json.loads(Path('.tmp/rig-controller-process.json').read_text(encoding='utf-8-sig'))
     if identity['generation']!=endpoint.controller_generation:raise RuntimeError('Generation changed')
     keep('verified_idle_before_loss',{'session':view(state.session),'devices':view(state.acquisition_devices),'mcu':view(state.microcontroller)})
     from cephvr.platform.windows.jobs import WindowsJobs
     native=WindowsJobs();native.retain_exact(identity['pid'],identity['creation_time_100ns'],identity['executable']);native.terminate_exact(identity['pid'],identity['creation_time_100ns']);exited=native.wait_process_exit(identity['pid'],identity['creation_time_100ns'],timeout_ms=2000);native.release_process(identity['pid'],identity['creation_time_100ns']);keep('exact_idle_controller_terminated',dict(identity,exited=exited));await asyncio.sleep(10);return
    elif sys.argv[1]=='controller_loss':
     try:
      keep('start',await asyncio.wait_for(dispatch_device_action(client,'camera',{'role':1,'kind':rpc.CAMERA_COMMAND_KIND_START_PREVIEW,'show_preview':False},principal),40));await asyncio.sleep(2)
      keep('loss_ready',{'generation':endpoint.controller_generation,'session':view(client.snapshot.session),'behavioral':view(client.snapshot.acquisition_devices.behavioral)})
      identity=json.loads(Path('.tmp/rig-controller-process.json').read_text(encoding='utf-8-sig'))
      if identity['generation']!=endpoint.controller_generation:raise RuntimeError('Generation changed')
      from cephvr.platform.windows.jobs import WindowsJobs
      native=WindowsJobs();native.retain_exact(identity['pid'],identity['creation_time_100ns'],identity['executable'])
      native.terminate_exact(identity['pid'],identity['creation_time_100ns'])
      exited=native.wait_process_exit(identity['pid'],identity['creation_time_100ns'],timeout_ms=2000)
      native.release_process(identity['pid'],identity['creation_time_100ns'])
      keep('injected_exact_controller_loss',dict(identity,exited=exited))
      await asyncio.sleep(10)
     finally:
      try:
       latest=await client.get_snapshot()
       if latest.acquisition_devices.behavioral.device_open or latest.acquisition_devices.behavioral.preview_run_id or latest.acquisition_devices.behavioral.cleanup_pending:
        keep('cleanup_with_live_controller',await asyncio.wait_for(dispatch_device_action(client,'camera',{'role':1,'kind':rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW},principal),40))
      except Exception as exc:keep('controller_departed',str(exc))
     return
    elif sys.argv[1]=='previews':
     acq=next(b.acquisition for b in state.configuration_values.current.backends if b.backend_name=='acquisition');roles=[(1,'behavioral'),(2,'tracking')]
     for cycle in range(4):
      for role,name in roles:
       config=getattr(acq,name)
       if not config.enabled:keep(f'{cycle}-{name}-skipped','disabled');continue
       initial=getattr(client.snapshot.acquisition_devices,name)
       if initial.device_open or initial.preview_run_id or initial.cleanup_pending:raise RuntimeError('Camera already in use before owned test')
       try:
        keep(f'{cycle}-{name}-start',await asyncio.wait_for(dispatch_device_action(client,'camera',{'role':role,'kind':rpc.CAMERA_COMMAND_KIND_START_PREVIEW,'show_preview':cycle==0},principal),40));await asyncio.sleep(3);keep(f'{cycle}-{name}-active',view(getattr(client.snapshot.acquisition_devices,name)))
       finally:
        device=getattr(client.snapshot.acquisition_devices,name)
        if device.device_open or device.preview_run_id or device.cleanup_pending:
         keep(f'{cycle}-{name}-stop',await asyncio.wait_for(dispatch_device_action(client,'camera',{'role':role,'kind':rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW},principal),40))
       await asyncio.sleep(.4);device=getattr(client.snapshot.acquisition_devices,name);keep(f'{cycle}-{name}-released',view(device))
       if device.device_open or device.preview_run_id or device.cleanup_pending:raise RuntimeError('Release unconfirmed')
    keep('configuration_unchanged',client.snapshot.configuration_values.current.SerializeToString()==original);(out/('managed-'+sys.argv[1]+'-after.pb')).write_bytes(client.snapshot.SerializeToString())
 except BaseException as exc:
  keep('error',str(exc));raise
 finally:store.remove_client(principal)
asyncio.run(main())
