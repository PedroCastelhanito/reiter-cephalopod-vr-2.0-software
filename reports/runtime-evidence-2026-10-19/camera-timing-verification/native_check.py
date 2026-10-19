"""Bounded native recording checks with exact configuration restoration."""

import asyncio
import dataclasses
import json
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).resolve().parent
RESULTS = []


def save(name, message):
    (OUT / name).write_text(
        json.dumps(MessageToDict(message, preserving_proto_field_name=True), indent=2)
        + "\n",
        encoding="utf-8",
    )


async def command(client, name, request=None):
    result = await asyncio.wait_for(client.execute(name, request), 90)
    record = {"command": name, **dataclasses.asdict(result)}
    RESULTS.append(record)
    (OUT / "native-commands.json").write_text(json.dumps(RESULTS, indent=2) + "\n")
    print(json.dumps(record), flush=True)
    if not result.succeeded:
        raise RuntimeError(str(record))


async def update(client, config):
    await command(client, "UpdateConfiguration", rpc.UpdateConfigurationRequest(
        command=client.operator_command(),
        expected_revision=client.snapshot.configuration.revision,
        proposed=config,
    ))


async def main():
    root = default_runtime_root()
    store = CredentialStore(root, _existing_endpoint(root).controller_generation)
    principal = store.provision_client("cli")
    saved_path = Path("config/last_configuration.json")
    saved_bytes = saved_path.read_bytes()
    (OUT / "saved-configuration-before.json").write_bytes(saved_bytes)
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.observe():
                if client.snapshot.session.phase != pb.SESSION_PHASE_CONFIGURATION:
                    raise RuntimeError("rig is no longer idle in Configuration")
                original = pb.ExperimentConfiguration()
                original.CopyFrom(client.snapshot.configuration_values.current)
                save("runtime-configuration-before.json", original)
                await client.claim_control(takeover=True)
                try:
                    for run, abort in (("normal", False), ("abort", True)):
                        config = pb.ExperimentConfiguration()
                        config.CopyFrom(original)
                        config.subject = "VERIFY"
                        config.experiment = "camera_timing_" + run
                        recording_root = Path(".tmp/ctverify").resolve()
                        recording_root.mkdir(parents=True, exist_ok=True)
                        config.recording_root = str(recording_root)
                        del config.trials[1:]
                        del config.gaps[:]
                        program = json.loads(config.trials[0].stimulus.program.program_json)
                        group = program["sequence"][0]
                        assert group["kind"] == "group" and len(group["body"]) == 2
                        group["repetitions"] = 2
                        assert sum(float(e["duration"]["duration"]["seconds"]) for e in group["body"]) == 30
                        program["sequence"] = [group]
                        config.trials[0].stimulus.program.program_json = json.dumps(program)
                        for backend in config.backends:
                            if backend.backend_name == "acquisition" and backend.enabled:
                                for role in ("behavioral", "tracking", "eye_tracking"):
                                    camera = getattr(backend.acquisition, role)
                                    if camera.enabled:
                                        camera.save_video = True
                        save(run + "-candidate.json", config)
                        await update(client, config)
                        await command(client, "Setup")
                        save(run + "-ready.json", client.snapshot)
                        await command(client, "StartSession")
                        await asyncio.wait_for(client._wait(lambda s: s.session.phase == pb.SESSION_PHASE_RUNNING), 20)
                        save(run + "-running.json", client.snapshot)
                        if abort:
                            await asyncio.sleep(12)
                            await command(client, "AbortNow")
                        await asyncio.wait_for(client._wait(lambda s: s.session.phase == pb.SESSION_PHASE_ENDED and s.session.cleanup_confirmed), 90)
                        save(run + "-ended.json", client.snapshot)
                        await command(client, "NewSession")
                finally:
                    save("native-final-state.json", client.snapshot)
                    if client.snapshot.session.phase == pb.SESSION_PHASE_READY:
                        await command(client, "CancelSetup")
                    if client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION:
                        await update(client, original)
                        save("runtime-configuration-restored.json", client.snapshot.configuration_values.current)
                        current = json.loads(saved_path.read_bytes())
                        before = json.loads(saved_bytes)
                        if current.get("configuration") == before.get("configuration"):
                            saved_path.write_bytes(saved_bytes)
                        (OUT / "restoration.json").write_text(json.dumps({
                            "runtime_configuration_equal": client.snapshot.configuration_values.current == original,
                            "saved_file_byte_equal": saved_path.read_bytes() == saved_bytes,
                        }, indent=2) + "\n")
    finally:
        store.remove_client(principal)


if __name__ == "__main__":
    asyncio.run(main())
