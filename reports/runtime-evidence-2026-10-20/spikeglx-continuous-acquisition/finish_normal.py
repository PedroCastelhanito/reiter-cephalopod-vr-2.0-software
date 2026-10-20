import asyncio
import json
from pathlib import Path
from google.protobuf.json_format import ParseDict
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root
from paired_check import save, command, update, native_state, OUT
async def main():
 root=default_runtime_root(); store=CredentialStore(root,_existing_endpoint(root).controller_generation); principal=store.provision_client("cli")
 try:
  async with loopback_channel(50051,16_777_216) as channel:
   client=HeadlessClient(channel,principal)
   async with client.control(takeover=True):
    assert "SAVEVERIFY-" in client.snapshot.session.directory and "continuous_normal" in client.snapshot.session.directory
    await asyncio.wait_for(client._wait(lambda s:s.session.phase==pb.SESSION_PHASE_ENDED and s.session.cleanup_confirmed),90)
    save("normal-ended.json",client.snapshot)
    ended=await native_state("normal-after")
    assert ended["running"] and not ended["saving"]
    before=json.loads((OUT/"normal-before-native.json").read_text())
    assert all(ended["sample_counts"][k]>v for k,v in before["sample_counts"].items())
    await command(client,"NewSession")
    original=ParseDict(json.loads((OUT/"operator-runtime-original.json").read_text()),pb.ExperimentConfiguration())
    await update(client,original)
 finally: store.remove_client(principal)
asyncio.run(main())
