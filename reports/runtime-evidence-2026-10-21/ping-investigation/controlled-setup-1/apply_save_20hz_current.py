"""Owner-approved20Hz edit and saved latest baseline through normal APIs."""
import asyncio,json,hashlib
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
   prior=pb.Snapshot();Parse((OUT/"latest-owner-snapshot.json").read_text(),prior)
   async with client.control(takeover=True):
    assert client.snapshot.controller_generation==prior.controller_generation
    assert client.snapshot.session.phase==pb.SESSION_PHASE_CONFIGURATION and not client.snapshot.session.HasField("context")
    assert client.snapshot.configuration_values.current==prior.configuration_values.current
    history=Path("config/last_configuration.json")
    assert history.read_bytes()==(OUT/"latest-owner-history.json").read_bytes()
    candidate=pb.ExperimentConfiguration();candidate.CopyFrom(client.snapshot.configuration_values.current)
    assert candidate.recording_root=="C:/Users/ReiterU_PC/Desktop/tmp"
    a=next(b.acquisition for b in candidate.backends if b.backend_name=="acquisition")
    assert a.session_preview_max_hz==10
    a.session_preview_max_hz=20
    result=await client.execute("UpdateConfiguration",rpc.UpdateConfigurationRequest(command=client.operator_command(),expected_revision=client.snapshot.configuration.revision,proposed=candidate));print("Update20Hz",result,flush=True);assert result.succeeded
    result=await client.execute("SaveConfigurationHistory");print("SaveHistory",result,flush=True);assert result.succeeded
    snapshot=await client.get_snapshot();assert snapshot.configuration_values.current==candidate
    saved=history.read_bytes();assert json.loads(saved)["configuration"]==MessageToDict(candidate,preserving_proto_field_name=True)
    (OUT/"latest-baseline-snapshot.json").write_text(json.dumps(MessageToDict(snapshot,preserving_proto_field_name=True),indent=2))
    (OUT/"latest-baseline-history.json").write_bytes(saved)
    print("LatestBaseline",hashlib.sha256(saved).hexdigest(),flush=True)
 finally:store.remove_client(principal)
asyncio.run(main())
