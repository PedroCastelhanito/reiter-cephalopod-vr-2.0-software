"""One explicit GPU-budget rejection and fresh Setup/cancel on the real runtime."""

import argparse
import asyncio
import hashlib
import json
import re
import time
import tomllib
from dataclasses import asdict
from pathlib import Path

from bounded_lifecycle import minimal_trial_configuration
from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.managed_display_operations import (
    capture_display_calibration_intent,
    close_display_calibration_request,
    open_display_calibration_request,
)
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root
from cephvr.visual_stimulus.v1 import runtime_pb2 as vs_runtime

ROOT = Path(__file__).resolve().parents[3]
POLICY = ROOT / "config/backends/visual_stimulus_config.toml"


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-controller-generation", required=True)
    parser.add_argument("--with-behavioral", action="store_true")
    args = parser.parse_args()
    out = Path(__file__).parent / "rig-runs" / time.strftime("budget-%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    original_policy = POLICY.read_bytes()
    low_policy, substitutions = re.subn(
        rb"(?m)^max_asset_gpu_bytes\s*=\s*[^\r\n]+",
        b"max_asset_gpu_bytes = 1",
        original_policy,
    )
    assert substitutions == 1
    before = tomllib.loads(original_policy.decode())
    lowered = tomllib.loads(low_policy.decode())
    assert lowered["resources"].pop("max_asset_gpu_bytes") == 1
    assert before["resources"].pop("max_asset_gpu_bytes") > 1
    assert lowered == before
    history = ROOT / "config/last_configuration.json"
    original_history = history.read_bytes()
    sessions = []

    def record(kind, value):
        row = {"host_ns": time.perf_counter_ns(), "kind": kind, "value": value}
        with (out / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")
        print(kind, json.dumps(value), flush=True)

    def save(name, value):
        (out / name).write_text(
            json.dumps(
                MessageToDict(value, preserving_proto_field_name=True), indent=2
            ),
            encoding="utf-8",
        )

    def observe(state):
        session = state.session.context.session_id
        if session and session not in sessions:
            sessions.append(session)
            record("session", {"id": session, "phase": state.session.phase})

    endpoint = _existing_endpoint(default_runtime_root())
    assert endpoint.controller_generation == args.expected_controller_generation
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    client = None

    def ready_for_setup(state):
        return (
            state.controller_generation == endpoint.controller_generation
            and state.session.phase == pb.SESSION_PHASE_CONFIGURATION
            and not state.session.HasField("context")
            and (
                state.session.cleanup_confirmed or not state.session.HasField("outcome")
            )
            and not state.session.cleanup_blockers
            and state.visual_stimulus_display.complete
            and not state.visual_stimulus_display.issues
            and all(
                not participant.required
                or (
                    participant.process_running
                    and participant.connected
                    and participant.health == "LAUNCH_PHASE_OPERATIONAL"
                    and not participant.outstanding_obligations
                )
                for participant in state.participants
            )
        )

    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal, on_snapshot=observe)
            async with client.control(takeover=True):
                assert (
                    client.snapshot.controller_generation
                    == endpoint.controller_generation
                )
                assert client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION
                assert not client.snapshot.session.HasField("context")
                assert not client.snapshot.session.cleanup_blockers
                original = pb.ExperimentConfiguration()
                original.CopyFrom(client.snapshot.configuration_values.current)
                save("before.json", client.snapshot)

                async def command(method, request=None):
                    if request is None:
                        request = client.operator_command()
                    command_id = (
                        request.operator.command_id
                        if isinstance(request, rpc.OperatorCommand)
                        else request.command.operator.command_id
                    )
                    record(
                        "command_attempt", {"method": method, "command_id": command_id}
                    )
                    result = await asyncio.wait_for(
                        client.execute(method, request), 120
                    )
                    record(method, asdict(result))
                    save("after-" + method + ".json", client.snapshot)
                    assert not result.needs_input, (
                        "operator prompt; stop without choosing"
                    )
                    return result

                async def update(config):
                    result = await command(
                        "UpdateConfiguration",
                        rpc.UpdateConfigurationRequest(
                            command=client.operator_command(),
                            expected_revision=client.snapshot.configuration.revision,
                            proposed=config,
                        ),
                    )
                    assert result.succeeded, result
                    assert client.snapshot.configuration_values.current == config

                candidate = minimal_trial_configuration(original)
                candidate.experiment = "budget_rejection"
                candidate.recording_root = str(ROOT / "cephvr-data/lf26")
                await asyncio.to_thread(
                    Path(candidate.recording_root).mkdir, parents=True, exist_ok=True
                )
                if args.with_behavioral:
                    acquisition = next(
                        b for b in candidate.backends if b.backend_name == "acquisition"
                    )
                    acquisition.enabled = True
                    assert acquisition.acquisition.behavioral.enabled
                    assert acquisition.acquisition.behavioral.save_video
                    acquisition.acquisition.tracking.enabled = False
                    acquisition.acquisition.eye_tracking.enabled = False
                await update(candidate)
                save("candidate.json", candidate)

                intent = capture_display_calibration_intent(
                    client.snapshot,
                    arena_path=str(ROOT / "assets/calibration/frame_grid.glb"),
                )
                opening = open_display_calibration_request(client, **intent)
                assert (await command("OpenDisplayCalibration", opening)).succeeded
                closing = close_display_calibration_request(
                    client,
                    expected_revision=client.snapshot.configuration.revision,
                    diagnostic_id=opening.diagnostic_id,
                )
                assert (await command("CloseDisplayCalibration", closing)).succeeded
                calibration = client.snapshot.visual_stimulus_display.calibration
                assert calibration.diagnostic_id == opening.diagnostic_id
                assert calibration.state == vs_runtime.DISPLAY_CALIBRATION_STATE_IDLE
                assert (
                    calibration.HasField("resources_closed")
                    and calibration.resources_closed
                )
                await asyncio.wait_for(client._wait(ready_for_setup), 30)
                assert POLICY.read_bytes() == original_policy
                POLICY.write_bytes(low_policy)
                record(
                    "gpu_limit", {"bytes": 1, "behavioral_camera": args.with_behavioral}
                )
                try:
                    rejected = await command("Setup")
                    assert rejected.complete and rejected.succeeded is False, rejected
                    save("rejected.json", client.snapshot)
                    failures = rejected.failure
                    assert "gpu" in failures.lower() and "budget" in failures.lower(), (
                        failures[:500]
                    )
                    assert len(sessions) == 1, sessions
                    await asyncio.wait_for(
                        client._wait(
                            lambda s: (
                                s.session.phase == pb.SESSION_PHASE_CONFIGURATION
                                and s.session.cleanup_confirmed
                                and not s.session.cleanup_blockers
                            )
                        ),
                        30,
                    )
                    save("rejected-cleanup.json", client.snapshot)
                finally:
                    assert POLICY.read_bytes() == low_policy, (
                        "concurrent TOML change; do not overwrite"
                    )
                    POLICY.write_bytes(original_policy)
                    record(
                        "gpu_limit_restored",
                        {"sha256": hashlib.sha256(original_policy).hexdigest()},
                    )
                await asyncio.wait_for(client._wait(ready_for_setup), 30)
                save("before-fresh-setup.json", client.snapshot)
                fresh = await command("Setup")
                assert fresh.succeeded, fresh
                assert client.snapshot.session.phase == pb.SESSION_PHASE_READY
                assert len(sessions) == 2 and sessions[0] != sessions[1], sessions
                save("fresh-ready.json", client.snapshot)
                assert (await command("CancelSetup")).succeeded
                assert client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION
                assert client.snapshot.session.cleanup_confirmed
                assert not client.snapshot.session.cleanup_blockers
                assert client.snapshot.configuration_values.current == candidate
                assert history.read_bytes() == original_history
                await update(original)
                assert history.read_bytes() == original_history
                save("restored.json", client.snapshot)
                record(
                    "complete",
                    {
                        "sessions": sessions,
                        "settings_restored": True,
                        "trial_started": False,
                    },
                )
    except Exception as exc:
        if client is not None:
            save("failure-cached-snapshot.json", client.snapshot)
        record("stopped", {"error": repr(exc), "automatic_retry": False})
        raise
    finally:
        store.remove_client(principal)


if __name__ == "__main__":
    asyncio.run(main())
