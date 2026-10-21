"""Restore approved latestbaseline after WPRpreflight failed before Setup dispatch."""
import asyncio,json
from pathlib import Path
from google.protobuf.json_format import MessageToDict,Parse
from cephvr.client.session import HeadlessClient,loopback_channel
from cephvr.control.v1 import types_pb2 as pb,services_pb2 as rpc
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore,default_runtime_root
OUT=Path(__file__).parent
async def main():
 root=default_runtime_root();endpoint=_existing_endpoint(root);store=CredentialStore(root,endpoint.controller_generation);principal=store.provision_client("cli")
 try:
  async with loopback_channel(50051,16777216) as channel:
   client=HeadlessClient(channel,principal)
   baseline=pb.Snapshot();Parse((OUT/"latest-baseline-snapshot.json").read_text(),baseline)
   candidate=pb.ExperimentConfiguration();Parse((OUT/"test-configuration-attached.json").read_text(),candidate)
   async with client.control(takeover=True):
    s=client.snapshot;assert s.controller_generation==baseline.controller_generation
    assert s.session.phase==pb.SESSION_PHASE_CONFIGURATION and not s.session.HasField("context")
    assert all(o.command not in ("Setup","StartSession") for o in s.operations)
    assert s.configuration_values.current==candidate
    history=Path("config/last_configuration.json");assert history.read_bytes()==(OUT/"latest-baseline-history.json").read_bytes()
    result=await client.execute("UpdateConfiguration",rpc.UpdateConfigurationRequest(command=client.operator_command(),expected_revision=s.configuration.revision,proposed=baseline.configuration_values.current));print(result,flush=True);assert result.succeeded
    final=await client.get_snapshot();assert final.configuration_values.current==baseline.configuration_values.current
    assert history.read_bytes()==(OUT/"latest-baseline-history.json").read_bytes()
    (OUT/"preflight-restored-snapshot.json").write_text(json.dumps(MessageToDict(final,preserving_proto_field_name=True),indent=2))
    print("Runtime/history exactlatest20HzDesktopbaseline restored; noSetup dispatched",flush=True)
 finally:store.remove_client(principal)
asyncio.run(main())
