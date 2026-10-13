import asyncio,json
from pathlib import Path
from cephvr.client.session import HeadlessClient,loopback_channel
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore,default_runtime_root
async def main():
 endpoint=None
 for _ in range(100):
  try: endpoint=_existing_endpoint(default_runtime_root()); break
  except Exception: await asyncio.sleep(.1)
 if endpoint is None: raise RuntimeError('Launcher endpoint not ready')
 store=CredentialStore(default_runtime_root(),endpoint.controller_generation)
 principal=store.provision_client('cli')
 try:
  async with loopback_channel(50051,16_777_216) as channel:
   client=HeadlessClient(channel,principal)
   state=await client.get_snapshot()
   for _ in range(40):
    holder=store.lookup(state.control.holder_client_id) if state.control.holder_client_id else None
    if holder is not None and holder.role=='gui': break
    await asyncio.sleep(.2)
    state=await client.get_snapshot()
   a=next(b.acquisition for b in state.configuration_values.current.backends if b.backend_name=='acquisition')
   result={'purpose':'read-only manual GUI readiness; no control claim or pin command','controller_generation':state.controller_generation,'phase':pb.SessionPhase.Name(state.session.phase),'port':a.pulses.port,'trial_pin':a.pulses.trial_state_pin,'trial_enabled':a.pulses.trial_state_enabled,'diagnostic_active':state.microcontroller.diagnostic.active,'has_control_holder':bool(state.control.holder_client_id),'control_holder_role':holder.role if holder else None}
   Path('reports/runtime-evidence-2026-10-13/pin-test/manual-readiness.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
   print(json.dumps(result))
 finally: store.remove_client(principal)
asyncio.run(main())
