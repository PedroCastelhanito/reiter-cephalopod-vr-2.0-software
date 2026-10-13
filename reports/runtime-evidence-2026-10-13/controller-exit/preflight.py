import asyncio,json
from pathlib import Path
from cephvr.client.session import HeadlessClient,loopback_channel
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore,default_runtime_root
async def main():
 endpoint=_existing_endpoint(default_runtime_root())
 store=CredentialStore(default_runtime_root(),endpoint.controller_generation)
 principal=store.provision_client('cli')
 try:
  async with loopback_channel(50051,16_777_216) as channel:
   state=await HeadlessClient(channel,principal).get_snapshot()
   data={'controller_generation':state.controller_generation,'phase':pb.SessionPhase.Name(state.session.phase),'visual_stimulus_display':str(state.visual_stimulus_display),'acquisition_devices':str(state.acquisition_devices),'tracking_diagnostic_active':state.tracking_diagnostic.active}
   print(json.dumps(data,indent=2))
   Path('reports/runtime-evidence-2026-10-13/controller-exit/preflight.json').write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
 finally: store.remove_client(principal)
asyncio.run(main())
