import asyncio,json,time
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from cephvr.client.session import HeadlessClient,loopback_channel
from cephvr.control.v1 import services_pb2 as rpc,types_pb2 as pb
from cephvr.gui.managed_device_commands import dispatch_device_action
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore,default_runtime_root
from cephvr.shared.recovery import RecoveryStore
OUT=Path(__file__).parent
result={'scope':'owner-requested Trial state output on pin 12, manual SpikeGLX observation; no camera capture, flash, Setup, recording or SpikeGLX mutation','events':[]}
def keep(name,value):
 result['events'].append({'name':name,'value':value})
 (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
 print(name,json.dumps(value),flush=True)
async def main():
 endpoint=None
 for _ in range(100):
  try: endpoint=_existing_endpoint(default_runtime_root()); break
  except Exception: await asyncio.sleep(.1)
 if endpoint is None: raise RuntimeError('Launcher endpoint unavailable')
 generation=endpoint.controller_generation
 store=CredentialStore(default_runtime_root(),generation); principal=store.provision_client('cli')
 keep('controller_generation',generation)
 try:
  async with loopback_channel(50051,16_777_216) as channel:
   client=HeadlessClient(channel,principal,rpc_timeout_s=8)
   async with client.control(takeover=True):
    try:
     state=client.snapshot
     if state.session.phase!=pb.SESSION_PHASE_CONFIGURATION or state.tracking_diagnostic.active or str(state.acquisition_devices):
      raise RuntimeError('Configuration and no camera/Tracking work required')
     acquisition=next(b.acquisition for b in state.configuration_values.current.backends if b.backend_name=='acquisition')
     pulses=acquisition.pulses
     keep('original_trial_pin',pulses.trial_state_pin)
     await dispatch_device_action(client,'save_mcu_pins',{'port':pulses.port,'trial_pin':'12','trial_enabled':True,'flip_pin':pulses.projector_flip_pin,'flip_enabled':pulses.projector_flip_enabled,'behavioral_pin':None,'tracking_pin':None},principal)
     saved=await client.get_snapshot()
     current=next(b.acquisition for b in saved.configuration_values.current.backends if b.backend_name=='acquisition')
     if current.pulses.trial_state_pin!='D12': raise RuntimeError('Pin 12 was not confirmed')
     keep('confirmed_trial_pin','D12')
     history=await client.execute('SaveConfigurationHistory')
     if not history.succeeded: raise RuntimeError('History save not confirmed')
     keep('saved_history',True)
     await dispatch_device_action(client,'mcu',{'kind':rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT},principal)
     keep('connected_mcu',MessageToDict((await client.get_snapshot()).microcontroller,preserving_proto_field_name=True))
     keep('test_start_request','Trial state pin 12 HIGH for up to 2000 ms; observe SpikeGLX')
     await dispatch_device_action(client,'mcu',{'kind':rpc.MICROCONTROLLER_COMMAND_KIND_START,'signal':pb.MICROCONTROLLER_SIGNAL_KIND_TRIAL_STATE},principal)
     keep('started_mcu',MessageToDict((await client.get_snapshot()).microcontroller,preserving_proto_field_name=True))
     await asyncio.sleep(2.2)
     await dispatch_device_action(client,'mcu',{'kind':rpc.MICROCONTROLLER_COMMAND_KIND_STATUS,'signal':pb.MICROCONTROLLER_SIGNAL_KIND_TRIAL_STATE},principal)
     stopped=await client.get_snapshot(); diagnostic=stopped.microcontroller.diagnostic
     keep('finished_mcu',MessageToDict(stopped.microcontroller,preserving_proto_field_name=True))
     if diagnostic.active or diagnostic.pin!='D12' or diagnostic.rising_edges!=1:
      raise RuntimeError('Expected stopped pin-12 diagnostic with one generated rising edge')
     keep('firmware_test_confirmed',True)
     keep('physical_reception','await owner observation in SpikeGLX; MCU evidence is not receiver proof')
    except Exception as exc:
     keep('error',str(exc)); raise
    finally:
     try:
      outcome=await client.execute('ShutdownApplication')
      keep('shutdown_result',{'succeeded':outcome.succeeded,'failure':outcome.failure})
     except Exception as exc: keep('shutdown_rpc',str(exc))
 finally:
  store.remove_client(principal)
 for _ in range(120):
  receipt=RecoveryStore(default_runtime_root()).read_exit_receipt(generation)
  if receipt is not None and receipt.all_owned_processes_absent:
   keep('all_owned_absent',str(receipt)); return
  await asyncio.sleep(.1)
 raise RuntimeError('Application exit not yet confirmed')
asyncio.run(main())
