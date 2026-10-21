"""Bounded open-loop Setup/cancel/Abort/reuse rig evidence through the real API."""

import asyncio
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).resolve().parent / "idle-followup"
OUT.mkdir(exist_ok=True)
ROOT = Path.cwd()


def record(kind, value):
    entry = {"host_ns": time.perf_counter_ns(), "kind": kind, "value": value}
    with (OUT / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry) + "\n")
    print(kind, json.dumps(value), flush=True)


def save(name, value):
    (OUT / name).write_text(
        json.dumps(MessageToDict(value, preserving_proto_field_name=True), indent=2),
        encoding="utf-8",
    )


async def main():
    runtime = default_runtime_root()
    endpoint = _existing_endpoint(runtime)
    store = CredentialStore(runtime, endpoint.controller_generation)
    principal = store.provision_client("cli")
    history = ROOT / "config/last_configuration.json"
    saved = history.read_bytes()
    (OUT / "saved-history-before.json").write_bytes(saved)
    last = None

    def observe(state):
        nonlocal last
        key = (state.session.phase, state.trial.phase, state.session.cleanup_confirmed,
               tuple((o.context.command_id, o.progress, o.complete) for o in state.operations))
        if key != last:
            last = key
            record("state", {"phase": pb.SessionPhase.Name(state.session.phase),
                             "trial": pb.TrialPhase.Name(state.trial.phase),
                             "cleanup": state.session.cleanup_confirmed,
                             "operations": [MessageToDict(o, preserving_proto_field_name=True)
                                            for o in state.operations]})

    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal, on_snapshot=observe)
            async with client.control(takeover=True):
                assert client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION
                original = pb.ExperimentConfiguration()
                original.CopyFrom(client.snapshot.configuration_values.current)
                save("runtime-before.json", client.snapshot)

                async def command(name, request=None, *, expect_success=True):
                    started = time.perf_counter_ns()
                    result = await asyncio.wait_for(client.execute(name, request), 120)
                    record(name, {**asdict(result), "elapsed_ms": (time.perf_counter_ns()-started)/1e6})
                    save("latest-snapshot.json", client.snapshot)
                    if expect_success:
                        assert result.succeeded, result
                    return result

                async def update(candidate):
                    await command("UpdateConfiguration", rpc.UpdateConfigurationRequest(
                        command=client.operator_command(),
                        expected_revision=client.snapshot.configuration.revision,
                        proposed=candidate))

                candidate = pb.ExperimentConfiguration()
                candidate.CopyFrom(original)
                candidate.subject = "RIGCHECK"
                candidate.experiment = "bounded_rig_validation_oct21"
                candidate.recording_root = str(OUT / "recordings")
                (OUT / "recordings").mkdir(exist_ok=True)
                del candidate.trials[1:]
                del candidate.gaps[:]
                program = json.loads(candidate.trials[0].stimulus.program.program_json)
                group = program["sequence"][0]
                assert group["kind"] == "group"
                group["repetitions"] = 1
                group["body"] = [group["body"][0]]
                group["body"][0]["repetition_settings"] = group["body"][0]["repetition_settings"][:1]
                group["body"][0]["duration"] = {"kind": "fixed", "duration": {"seconds": "60"}}
                program["sequence"] = [group]
                candidate.trials[0].stimulus.program.program_json = json.dumps(program)
                for backend in candidate.backends:
                    if backend.backend_name in ("tracking", "synchronization"):
                        backend.enabled = False
                    elif backend.backend_name == "acquisition":
                        for role in ("behavioral", "tracking", "eye_tracking"):
                            camera = getattr(backend.acquisition, role)
                            if camera.enabled:
                                camera.save_video = True
                    elif backend.backend_name == "visual_stimulus":
                        backend.visual_stimulus.save_visual_stimulus_data = True
                save("test-configuration.json", candidate)
                try:
                    acquisition = next(b.acquisition for b in candidate.backends if b.backend_name == "acquisition")
                    acquisition.eye_tracking.enabled = False
                    acquisition.eye_tracking.save_video = False
                    await update(candidate)
                    assert acquisition.behavioral.enabled and acquisition.tracking.enabled
                    save("test-configuration-attached.json", candidate)
                    events = [json.loads(line) for line in (OUT.parent / "events.jsonl").read_text().splitlines()]
                    cleanup_ns = next(e["value"]["cleanup_ns"] for e in reversed(events) if e["kind"] == "idle_begin")
                    elapsed = time.perf_counter_ns() - cleanup_ns
                    assert elapsed > 300_000_000_000
                    record("idle_reuse", {"cleanup_ns": cleanup_ns, "elapsed_ns": elapsed, "controller_generation": client.snapshot.controller_generation})
                    await command("Setup")
                    save("ready.json", client.snapshot)
                    await command("CancelSetup")
                    assert client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION and client.snapshot.session.cleanup_confirmed
                    save("cancel-confirmed.json", client.snapshot)
                    record("acceptance", {"idle_over_300_seconds_fresh_setup_cancel": True})
                finally:
                    phase = client.snapshot.session.phase
                    if phase in (pb.SESSION_PHASE_STARTING, pb.SESSION_PHASE_RUNNING):
                        await command("AbortNow")
                    if client.snapshot.session.phase == pb.SESSION_PHASE_FINALIZING:
                        await asyncio.wait_for(client._wait(lambda s: s.session.cleanup_confirmed), 100)
                    if client.snapshot.session.phase in (pb.SESSION_PHASE_SETTING_UP, pb.SESSION_PHASE_READY):
                        await command("CancelSetup")
                    if client.snapshot.session.phase == pb.SESSION_PHASE_ENDED and client.snapshot.session.cleanup_confirmed:
                        await command("NewSession")
                    save("before-restoration.json", client.snapshot)
                    if client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION and client.snapshot.session.cleanup_confirmed:
                        await update(original)
                        assert client.snapshot.configuration_values.current == original
                        # Restore only this test's history; retain any concurrent operator edits.
                        current = json.loads(history.read_bytes()).get("configuration")
                        if current in (MessageToDict(candidate, preserving_proto_field_name=True), MessageToDict(original, preserving_proto_field_name=True), json.loads(saved).get("configuration")):
                            history.write_bytes(saved)
                        record("restoration", {"runtime_equal": True, "saved_bytes_equal": history.read_bytes() == saved,
                                               "saved_sha256": hashlib.sha256(saved).hexdigest()})
                    else:
                        record("restoration_blocked", {"phase": client.snapshot.session.phase, "cleanup": client.snapshot.session.cleanup_confirmed})
                    save("final-snapshot.json", client.snapshot)
    except Exception as exc:
        record("error", repr(exc))
        raise
    finally:
        store.remove_client(principal)


asyncio.run(main())
