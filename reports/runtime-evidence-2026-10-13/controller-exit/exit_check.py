import asyncio,json,time
from pathlib import Path
from cephvr.client.session import HeadlessClient,loopback_channel
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.platform.windows.jobs import WindowsJobs
from cephvr.shared.credentials import CredentialStore,default_runtime_root
from cephvr.shared.recovery import RecoveryStore
OUT=Path('reports/runtime-evidence-2026-10-13/controller-exit')
async def preflight():
 endpoint=_existing_endpoint(default_runtime_root())
 store=CredentialStore(default_runtime_root(),endpoint.controller_generation)
 principal=store.provision_client('cli')
 try:
  async with loopback_channel(50051,16_777_216) as channel:
   state=await HeadlessClient(channel,principal).get_snapshot()
   if state.session.phase != pb.SESSION_PHASE_CONFIGURATION or state.tracking_diagnostic.active or str(state.acquisition_devices):
    raise RuntimeError('Refusing process-exit check while device/session work is active')
   return endpoint.controller_generation
 finally: store.remove_client(principal)
generation=asyncio.run(preflight())
processes=json.loads((OUT/'processes-before.json').read_text(encoding='utf-8-sig'))
controllers=[p for p in processes if ' cephvr.controller.main ' in p['CommandLine']]
if len(controllers)!=1: raise RuntimeError('Require one exact managed controller')
controller=controllers[0]
supervisor_pid=controller['ParentProcessId']
owned=[p for p in processes if p['ProcessId']==supervisor_pid or p['ParentProcessId']==supervisor_pid]
owned_ids={p['ProcessId'] for p in owned}
owned += [p for p in processes if p['ParentProcessId'] in owned_ids and p not in owned]
native=WindowsJobs(); retained=[]
for p in owned:
 handle=native.api.OpenProcess(0x00100000|0x1000,False,p['ProcessId'])
 native._check(handle,'OpenProcess(identity)')
 try: member=native._member(handle,p['ProcessId'])
 finally: native.api.CloseHandle(handle)
 if member is None or member[2].casefold()!=p['ExecutablePath'].casefold(): raise RuntimeError('Managed process identity changed')
 native.retain_exact(*member)
 retained.append(member)
selected=next(p for p in retained if p[0]==controller['ProcessId'])
result={'controller_generation':generation,'method':'terminate exact controller PID+creation-time; observe retained handles and generation-bound application exit receipt','owned_before':retained,'terminated_controller':selected,'observations':[]}
(OUT/'exit-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
start=time.monotonic(); native.terminate_exact(selected[0],selected[1])
last=None
while time.monotonic()-start<100:
 alive=[p[0] for p in retained if native.process_running(p[0],p[1])]
 if alive!=last:
  result['observations'].append({'elapsed_s':round(time.monotonic()-start,3),'alive_pids':alive}); last=alive
  print('owned remaining',alive,flush=True)
 receipt=RecoveryStore(default_runtime_root()).read_exit_receipt(generation)
 if not alive and receipt is not None and receipt.all_owned_processes_absent:
  result['all_retained_owned_absent']=True
  result['application_exit_receipt']=str(receipt)
  result['elapsed_s']=round(time.monotonic()-start,3)
  break
 time.sleep(.1)
else:
 result['all_retained_owned_absent']=False
 result['remaining']=[p for p in retained if native.process_running(p[0],p[1])]
(OUT/'exit-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
for pid,created,_ in retained: native.release_process(pid,created)
print('result',result['all_retained_owned_absent'],result.get('elapsed_s'),flush=True)
