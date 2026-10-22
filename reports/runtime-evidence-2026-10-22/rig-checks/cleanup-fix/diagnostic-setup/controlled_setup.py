"""One approved full-protocol Setup/noStart then bounded CancelSetup."""

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

OUT = Path(__file__).resolve().parent
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
    saved = (OUT / "latest-baseline-history.json").read_bytes()
    assert history.read_bytes() == saved, "latest baseline history changed; stop"
    assert not (OUT / "setup-attempted.json").exists(), "single attempt already consumed"
    last = None

    def observe(state):
        nonlocal last
        key = (state.session.phase, state.trial.phase, state.session.cleanup_confirmed,
               tuple((o.context.command_id, o.progress, o.complete) for o in state.operations),
               tuple((p.process.SerializeToString(), p.started.SerializeToString(), p.stopped.SerializeToString(), p.finished.SerializeToString()) for p in state.participants))
        if key != last:
            last = key
            record("state", {"phase": pb.SessionPhase.Name(state.session.phase),
                             "trial": pb.TrialPhase.Name(state.trial.phase),
                             "cleanup": state.session.cleanup_confirmed,
                             "operations": [MessageToDict(o, preserving_proto_field_name=True)
                                            for o in state.operations],
                             "trial_state": MessageToDict(state.trial, preserving_proto_field_name=True),
                             "participants": [MessageToDict(p, preserving_proto_field_name=True) for p in state.participants]})

    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal, on_snapshot=observe)
            async with client.control(takeover=True):
                assert client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION
                assert client.snapshot.session.cleanup_confirmed or not client.snapshot.session.HasField("context")
                assert client.snapshot.controller_generation == json.loads((OUT / "latest-baseline-snapshot.json").read_text())["controller_generation"]
                assert not client.snapshot.session.HasField("context")
                assert all(o.complete and o.succeeded for o in client.snapshot.operations)
                assert not client.snapshot.acquisition_devices.source.backend_generation
                original = pb.ExperimentConfiguration()
                original.CopyFrom(client.snapshot.configuration_values.current)
                prior = pb.Snapshot()
                from google.protobuf.json_format import Parse
                Parse((OUT / "latest-baseline-snapshot.json").read_text(), prior)
                assert original == prior.configuration_values.current, "concurrent runtime edit; stop"
                save("runtime-before.json", client.snapshot)

                async def command(name, request=None, *, expect_success=True):
                    started = time.perf_counter_ns()
                    result = await asyncio.wait_for(client.execute(name, request), 300)
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
                candidate.experiment = "diag22"
                candidate.recording_root = str(ROOT / "cephvr-data" / "r22")
                Path(candidate.recording_root).mkdir(parents=True, exist_ok=True)
                document = json.loads(Path("C:/Users/ReiterU_PC/Desktop/Pedro/primate_cuttlebase_20min.json").read_text(encoding="utf-8"))
                candidate.asset_root = document["asset_root"]
                del candidate.trials[:]
                del candidate.gaps[:]
                from decimal import Decimal
                for number, draft in enumerate(document["trials"], start=1):
                    trial = candidate.trials.add(trial_number=number)
                    trial.stimulus.program.program_json = json.dumps(draft["program"])
                    if draft["path"]:
                        trial.stimulus.program.logical_source_reference = draft["path"]
                    if draft["stimulus_seed_decimal"]:
                        trial.stimulus.stimulus_seed_decimal = draft["stimulus_seed_decimal"]
                    trial.stimulus.arena_boundaries.boundaries_json = draft["arena_boundaries_json"] or '{"format_version":1,"bindings":[]}'
                    if draft["gap_after_seconds"]:
                        candidate.gaps.add(after_trial_number=number, minimum_duration_ns=int(Decimal(draft["gap_after_seconds"]) * 1_000_000_000))
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
                    candidate.CopyFrom(client.snapshot.configuration_values.current)
                    acquisition = next(b.acquisition for b in candidate.backends if b.backend_name == "acquisition")
                    assert acquisition.behavioral.enabled and acquisition.tracking.enabled
                    save("test-configuration-attached.json", candidate)
                    (OUT / "setup-attempted.json").write_text(json.dumps({"host_ns": time.perf_counter_ns()}))
                    outcome = await command("Setup", expect_success=False)
                    save("setup-result-snapshot.json", client.snapshot)
                    record("setup_outcome", {"succeeded": outcome.succeeded, "no_start_issued": True})
                    if client.snapshot.session.phase == pb.SESSION_PHASE_READY:
                        save("ready.json", client.snapshot)
                finally:
                    client.views.install(await client.get_snapshot())
                    phase = client.snapshot.session.phase
                    if phase in (pb.SESSION_PHASE_STARTING, pb.SESSION_PHASE_RUNNING):
                        await command("AbortNow")
                    if client.snapshot.session.phase == pb.SESSION_PHASE_FINALIZING:
                        await asyncio.wait_for(client._wait(lambda s: s.session.cleanup_confirmed), 100)
                    if client.snapshot.session.phase in (pb.SESSION_PHASE_SETTING_UP, pb.SESSION_PHASE_READY):
                        await command("CancelSetup", expect_success=False)
                        client.views.install(await client.get_snapshot())
                        save("cancel-result-snapshot.json", client.snapshot)
                    if client.snapshot.session.phase == pb.SESSION_PHASE_ENDED and client.snapshot.session.cleanup_confirmed:
                        await command("NewSession")
                    save("before-restoration.json", client.snapshot)
                    if client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION and client.snapshot.session.cleanup_confirmed:
                        assert client.snapshot.controller_generation == endpoint.controller_generation, "generation changed; stop"
                        assert client.snapshot.configuration_values.current == candidate, "concurrent config changed; do not overwrite"
                        assert history.read_bytes() == saved, "concurrent history edit; do not overwrite"
                        await update(original)
                        assert client.snapshot.configuration_values.current == original
                        assert history.read_bytes() == saved, "history changed during restoration"
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

