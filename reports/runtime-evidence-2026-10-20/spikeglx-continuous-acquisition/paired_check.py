"""Bounded native recording checks with exact configuration restoration."""

import asyncio
import dataclasses
import json
from pathlib import Path

from google.protobuf.json_format import MessageToDict, ParseDict

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


async def native_state(label):
    from cephvr.synchronization.native import read_sdk, with_sdk
    from cephvr.synchronization.settings import load_host_settings
    root = Path.cwd()
    settings = load_host_settings(root)
    def read():
        state = read_sdk(root, settings)
        counts = with_sdk(root, settings, lambda sdk,h:{str((int(stream.family)-1,stream.index)):int(sdk.c_sglx_getStreamSampleCount(h,int(stream.family)-1,stream.index)) for stream in state.streams if stream.saved_channel_indices})
        return dict(running=state.running,saving=state.saving,run_name=state.run_name,sample_counts=counts)
    result = await asyncio.to_thread(read)
    (OUT / (label+"-native.json")).write_text(json.dumps(result,indent=2)+"\n")
    return result


async def main():
    root = default_runtime_root()
    store = CredentialStore(root, _existing_endpoint(root).controller_generation)
    principal = store.provision_client("cli")
    saved_path = Path("config/last_configuration.json")
    saved_bytes = (OUT / "operator-saved-original.json").read_bytes()
    (OUT / "saved-configuration-before.json").write_bytes(saved_bytes)
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.observe():
                if client.snapshot.session.phase != pb.SESSION_PHASE_CONFIGURATION:
                    raise RuntimeError("rig is no longer idle in Configuration")
                original = pb.ExperimentConfiguration()
                original_path = OUT / "operator-runtime-original.json"
                if original_path.exists():
                    ParseDict(json.loads(original_path.read_text()), original)
                else:
                    original.CopyFrom(client.snapshot.configuration_values.current)
                    save("operator-runtime-original.json", original)
                save("runtime-configuration-before.json", original)
                await client.claim_control(takeover=True)
                try:
                    for run, abort in (("abort", True), ("cancel", False)):
                        config = pb.ExperimentConfiguration()
                        config.CopyFrom(original)
                        config.subject = "SAVEVERIFY"
                        config.experiment = "continuous_" + run
                        recording_root = Path(".tmp/continuous").resolve()
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
                        paired = next((b for b in config.backends if b.backend_name == "synchronization"), None)
                        if paired is None:
                            paired = config.backends.add(backend_name="synchronization")
                        paired.enabled = True
                        save(run + "-candidate.json", config)
                        await update(client, config)
                        before = await native_state(run + "-before")
                        await command(client, "Setup")
                        save(run + "-ready.json", client.snapshot)
                        ready = await native_state(run + "-ready")
                        assert ready["running"] and not ready["saving"] and ready["run_name"] == before["run_name"]
                        if run == "cancel":
                            await command(client, "CancelSetup")
                            cancelled = await native_state("cancel-after")
                            assert cancelled["running"] and not cancelled["saving"] and cancelled["run_name"] == before["run_name"]
                            continue
                        await command(client, "StartSession")
                        await asyncio.wait_for(client._wait(lambda s: s.session.phase == pb.SESSION_PHASE_RUNNING), 20)
                        save(run + "-running.json", client.snapshot)
                        expected = Path(client.snapshot.session.directory).name
                        # Controller's writing gate already confirmed matching name and advancing counts.
                        await asyncio.wait_for(client._wait(lambda state: state.spikeglx_recording.running and state.spikeglx_recording.saving), 10)
                        if abort:
                            await asyncio.sleep(12)
                            await command(client, "AbortNow")
                        await asyncio.wait_for(client._wait(lambda s: s.session.phase == pb.SESSION_PHASE_ENDED and s.session.cleanup_confirmed), 90)
                        save(run + "-ended.json", client.snapshot)
                        ended = await native_state(run + "-after")
                        assert ended["running"] and not ended["saving"] and ended["run_name"] == expected
                        assert all(ended["sample_counts"][key] > value for key,value in before["sample_counts"].items())
                        await command(client, "NewSession")
                finally:
                    save("native-final-state.json", client.snapshot)
                    if client.snapshot.session.phase == pb.SESSION_PHASE_FINALIZING:
                        await asyncio.wait_for(client._wait(lambda state: state.session.phase == pb.SESSION_PHASE_ENDED and state.session.cleanup_confirmed), 90)
                    if client.snapshot.session.phase == pb.SESSION_PHASE_ENDED and client.snapshot.session.cleanup_confirmed:
                        await command(client, "NewSession")
                    if client.snapshot.session.phase == pb.SESSION_PHASE_SETTING_UP:
                        await asyncio.wait_for(client._wait(lambda state: state.session.phase == pb.SESSION_PHASE_CONFIGURATION), 30)
                    save("native-final-settled.json", client.snapshot)
                    if client.snapshot.session.phase == pb.SESSION_PHASE_READY:
                        await command(client, "CancelSetup")
                    if client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION:
                        await update(client, original)
                        save("runtime-configuration-restored.json", client.snapshot.configuration_values.current)
                        current = json.loads(saved_path.read_bytes())
                        before = json.loads(saved_bytes)
                        if current.get("configuration") in [before.get("configuration")] + [json.loads((OUT / (r+"-candidate.json")).read_text()) for r in ("normal","abort","cancel") if (OUT / (r+"-candidate.json")).exists()]:
                            saved_path.write_bytes(saved_bytes)
                        (OUT / "restoration.json").write_text(json.dumps({
                            "runtime_configuration_equal": client.snapshot.configuration_values.current == original,
                            "saved_file_byte_equal": saved_path.read_bytes() == saved_bytes,
                        }, indent=2) + "\n")
    finally:
        store.remove_client(principal)


if __name__ == "__main__":
    asyncio.run(main())
