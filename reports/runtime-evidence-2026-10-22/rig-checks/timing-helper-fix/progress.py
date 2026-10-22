"""Read-only phase/health observation; no control claim or device operation."""
import asyncio,json,sys,time
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from cephvr.client.session import HeadlessClient,loopback_channel
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore,default_runtime_root
async def main():
 root=default_runtime_root(); endpoint=_existing_endpoint(root)
 store=CredentialStore(root,endpoint.controller_generation); principal=store.provision_client("cli")
 try:
  async with loopback_channel(50051,16777216) as channel:
   s=await HeadlessClient(channel,principal).get_snapshot()
   data=MessageToDict(s,preserving_proto_field_name=True)
   (Path(__file__).parent/"diagnostic-full"/sys.argv[1]).write_text(json.dumps(data,indent=2),encoding="utf-8")
   print(json.dumps({"generation":s.controller_generation,"session":data.get("session"),"trial":data.get("trial"),"elapsed_s":(time.perf_counter_ns()-s.trial.start_monotonic_ns)/1e9 if s.trial.start_monotonic_ns else None,"errors":data.get("errors"),"warnings":data.get("warnings")}))
 finally:store.remove_client(principal)
asyncio.run(main())
