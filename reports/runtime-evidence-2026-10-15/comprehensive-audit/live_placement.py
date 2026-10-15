"""Hash-bound existing diagnostic bundles; temporary live output edits only."""

import asyncio
import dataclasses
import hashlib
import json
from pathlib import Path
import time

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import ClientError, HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.gui.managed_display_operations import capture_display_calibration_intent, open_display_calibration_request, close_display_calibration_request
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.calibration_assets import calibration_asset_root, calibration_runtime_root
from cephvr.shared.credentials import CredentialStore, default_runtime_root
from cephvr.visual_stimulus.v1 import runtime_pb2 as vp

out = Path(__file__).parent / "live-placement-propagation"
out.mkdir(exist_ok=False)
record = {"scope":"Actual native projector diagnostic Open/Update/reject/Close through authenticated controller; no saved drafts/assets edited, no optical measurement", "events":[]}


def keep(name,value):
    record["events"].append({"name":name,"monotonic_ns":time.perf_counter_ns(),"value":value})
    (out / "results.json").write_text(json.dumps(record,indent=2)+"\n",encoding="utf-8")
    print(name,json.dumps(value),flush=True)


def view(value):
    return MessageToDict(value,preserving_proto_field_name=True)


async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    assert endpoint is not None
    record["generation"] = endpoint.controller_generation
    store = CredentialStore(default_runtime_root(),endpoint.controller_generation)
    principal = store.provision_client("cli")
    hashes = {}
    try:
        async with loopback_channel(50051,16_777_216) as channel:
            client = HeadlessClient(channel,principal)
            async with client.control(takeover=True):
                assert client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION and not client.snapshot.prompts
                for name in ("photodiode_placement","blackout_placement"):
                    arena = calibration_asset_root()/"calibration"/(name+".glb")
                    profile_path = calibration_runtime_root(name)/"calibration/diagnostic_display_profile.json"
                    profile = json.loads(profile_path.read_text())
                    for path in (arena,profile_path):
                        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
                    intent = capture_display_calibration_intent(client.snapshot,arena_path=str(arena))
                    request = open_display_calibration_request(client,**intent)
                    result = await asyncio.wait_for(client.execute("OpenDisplayCalibration",request),90)
                    keep(name+"-open",dataclasses.asdict(result))
                    assert result.succeeded
                    evidence = client.snapshot.visual_stimulus_display.calibration
                    assert evidence.state == vp.DISPLAY_CALIBRATION_STATE_ACTIVE and evidence.presented
                    keep(name+"-active",view(evidence))
                    outputs = [o["output_id"] for o in profile["outputs"]]
                    selected = outputs[0]
                    value = {"outputs":[{"output_id":o,"blackout_zones":[]} for o in outputs]}
                    if name == "photodiode_placement":
                        value.update(photodiode_output_id=selected,photodiode_patch={"rect":{"x":12,"y":12,"width":16,"height":16},"high_linear_rgb":[1,1,1],"low_linear_rgb":[0,0,0]})
                    else:
                        value["outputs"][0]["blackout_zones"] = [{"x":12,"y":12,"width":16,"height":16}]

                    def update(sequence,placement):
                        return rpc.UpdateDisplayCalibrationRequest(command=client.operator_command(),expected_configuration_revision=client.snapshot.configuration.revision,diagnostic_id=request.diagnostic_id,adjustment_sequence=sequence,placement_json=json.dumps(placement))

                    invalid = json.loads(json.dumps(value))
                    if name == "photodiode_placement":
                        invalid["photodiode_patch"]["rect"]["x"] = 100_000
                    else:
                        invalid["outputs"][0]["blackout_zones"][0]["x"] = 100_000
                    try:
                        rejected = await asyncio.wait_for(client.execute("UpdateDisplayCalibration",update(1,invalid)),30)
                    except ClientError as error:
                        assert not error.admission_uncertain
                        keep(name+"-rejection",str(error))
                    else:
                        keep(name+"-admitted-terminal-rejection",dataclasses.asdict(rejected))
                        assert rejected.complete and rejected.succeeded is False, "Out-of-bounds placement unexpectedly succeeded"
                    assert client.snapshot.visual_stimulus_display.calibration.state == vp.DISPLAY_CALIBRATION_STATE_ACTIVE
                    result = await asyncio.wait_for(client.execute("UpdateDisplayCalibration",update(2,value)),60)
                    keep(name+"-valid-after-rejection",dataclasses.asdict(result))
                    assert result.succeeded
                    keep(name+"-updated",view(client.snapshot.visual_stimulus_display.calibration))
                    assert client.snapshot.visual_stimulus_display.calibration.adjustment_sequence == 2
                    if name == "photodiode_placement":
                        value["photodiode_patch"]["rect"].update(x=30,width=20)
                    else:
                        value["outputs"][0]["blackout_zones"] = []
                    result = await asyncio.wait_for(client.execute("UpdateDisplayCalibration",update(3,value)),60)
                    keep(name+"-move-or-remove",dataclasses.asdict(result))
                    assert result.succeeded
                    close = close_display_calibration_request(client,expected_revision=client.snapshot.configuration.revision,diagnostic_id=request.diagnostic_id)
                    result = await asyncio.wait_for(client.execute("CloseDisplayCalibration",close),90)
                    keep(name+"-close",dataclasses.asdict(result))
                    assert result.succeeded
                    evidence = client.snapshot.visual_stimulus_display.calibration
                    keep(name+"-closed",view(evidence))
                    assert evidence.state == vp.DISPLAY_CALIBRATION_STATE_IDLE and evidence.idle and evidence.resources_closed
                for path,digest in hashes.items():
                    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
                keep("asset_hashes_unchanged",hashes)
    except BaseException as error:
        keep("error",f"{type(error).__name__}: {error}")
        raise
    finally:
        store.remove_client(principal)


asyncio.run(main())
