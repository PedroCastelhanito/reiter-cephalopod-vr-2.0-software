"""Prepare a bounded trial from preserved accepted settings; GUI owns Start."""
import asyncio
import dataclasses
import json
from pathlib import Path

from google.protobuf.json_format import MessageToDict, ParseDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).parent


async def main():
    saved = json.loads((OUT / "originals/config/last_configuration.json").read_text())
    config = ParseDict(saved["configuration"], pb.ExperimentConfiguration())
    config.subject = "PREVIEW"
    config.experiment = "previewrepair"
    recording_root = Path.cwd() / ".tmp" / "previewrepair"
    recording_root.mkdir(exist_ok=True)
    config.recording_root = str(recording_root.resolve())
    del config.trials[1:]
    del config.gaps[:]
    for backend in config.backends:
        if backend.backend_name == "acquisition":
            for role in ("behavioral", "tracking", "eye_tracking"):
                getattr(backend.acquisition, role).save_video = False
        if backend.backend_name == "visual_stimulus":
            backend.visual_stimulus.save_visual_stimulus_data = False
    program = json.loads(config.trials[0].stimulus.program.program_json)
    program["sequence"] = [e for e in program["sequence"] if e.get("scene_id") == "textures"]
    program["assets"] = [a for a in program["assets"] if a["asset_id"] != "circular"]
    program["instances"] = [i for i in program["instances"] if i["family"] != "arena"]
    program["scenes"] = [s for s in program["scenes"] if s["scene_id"] == "textures"]
    assert program["sequence"] and 120 % len(program["sequence"]) == 0
    for epoch in program["sequence"]:
        epoch["duration"]["duration"]["seconds"] = str(120 // len(program["sequence"]))
    config.trials[0].stimulus.program.program_json = json.dumps(program)
    config.trials[0].stimulus.arena_boundaries.boundaries_json = json.dumps(
        {"format_version": 1, "bindings": []}
    )
    (OUT / "runtime-candidate.json").write_text(
        json.dumps(MessageToDict(config, preserving_proto_field_name=True), indent=2)
    )
    root = default_runtime_root()
    endpoint = _existing_endpoint(root)
    store = CredentialStore(root, endpoint.controller_generation)
    principal = store.provision_client("cli")
    results = []
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                assert client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION
                for name in ("UpdateConfiguration", "Setup"):
                    request = rpc.UpdateConfigurationRequest(
                        command=client.operator_command(),
                        expected_revision=client.snapshot.configuration.revision,
                        proposed=config,
                    ) if name == "UpdateConfiguration" else None
                    result = await asyncio.wait_for(
                        client.execute(name, request) if request is not None else client.execute(name), 90
                    )
                    results.append({"command": name, **dataclasses.asdict(result)})
                    print(json.dumps(results[-1]), flush=True)
                    if not result.succeeded:
                        break
    finally:
        store.remove_client(principal)
        (OUT / "runtime-setup.json").write_text(json.dumps(results, indent=2))


asyncio.run(main())
