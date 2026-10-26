"""Operator-launched, bounded Visual Stimulus lifecycle verification harness."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

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
HISTORY = ROOT / "config" / "last_configuration.json"
TRIAL_NS = 60_000_000_000


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def json_message(message) -> dict:
    return MessageToDict(message, preserving_proto_field_name=True)


def make_output_dir(stage: str) -> Path:
    output = (
        Path(__file__).resolve().parent
        / "rig-runs"
        / f"{stage}-{time.strftime('%Y%m%d-%H%M%S')}"
    )
    output.mkdir(parents=True, exist_ok=False)
    (output / "output").mkdir()
    return output


def minimal_trial_configuration(source: pb.ExperimentConfiguration):
    from cephvr.gui.protocol_document import blank_program

    candidate = pb.ExperimentConfiguration()
    candidate.CopyFrom(source)
    candidate.mode = pb.SESSION_MODE_OPEN_LOOP
    candidate.subject = "RIGCHECK"
    candidate.experiment = "bounded_lifecycle"
    candidate.subject_metadata.Clear()
    visual = None
    for backend in candidate.backends:
        if backend.backend_name == "visual_stimulus":
            visual = backend
            backend.enabled = True
        else:
            backend.enabled = False
    require(
        visual is not None and visual.WhichOneof("settings") == "visual_stimulus",
        "current configuration has no Visual Stimulus settings to exercise",
    )
    visual.visual_stimulus.save_visual_stimulus_data = False
    require(candidate.trials, "current configuration has no trial to bound")
    del candidate.trials[1:]
    candidate.trials[0].trial_number = 1
    del candidate.gaps[:]

    trial = candidate.trials[0].stimulus
    trial.program.ClearField("logical_source_reference")
    trial.program.program_json = blank_program().model_dump_json()
    return candidate


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stage",
        choices=("visual-stimulus-lifecycle",),
        required=True,
        help="Run one bounded normal trial, NewSession, and display diagnostic.",
    )
    parser.add_argument(
        "--expected-controller-generation",
        required=True,
        help="Exact generation captured from the freshly launched controller.",
    )
    parser.add_argument(
        "--leave-ended",
        action="store_true",
        help="After diagnostic close, run one more bounded trial and leave it Ended for a separate ShutdownApplication check.",
    )
    args = parser.parse_args()
    output = make_output_dir(args.stage)
    events_path = output / "events.jsonl"

    def record(kind: str, value: object) -> None:
        entry = {"host_ns": time.perf_counter_ns(), "kind": kind, "value": value}
        with events_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, sort_keys=True) + "\n")
        print(kind, json.dumps(value, sort_keys=True), flush=True)

    def save(name: str, message) -> None:
        (output / name).write_text(
            json.dumps(json_message(message), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def healthy(snapshot: pb.Snapshot) -> bool:
        if not snapshot.participants:
            # Public participants exist only while a Setup attempt is retained.
            return (
                snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION
                and not snapshot.session.HasField("context")
                and snapshot.visual_stimulus_display.complete
                and not snapshot.visual_stimulus_display.issues
            )
        visual = [
            participant
            for participant in snapshot.participants
            if participant.process.role == "visual_stimulus"
        ]
        return (
            bool(visual)
            and all(
                participant.process_running
                and participant.connected
                and participant.health == "LAUNCH_PHASE_OPERATIONAL"
                and not participant.outstanding_obligations
                for participant in visual
            )
            and all(
                not participant.required
                or (
                    participant.process_running
                    and participant.connected
                    and participant.health == "LAUNCH_PHASE_OPERATIONAL"
                    and not participant.outstanding_obligations
                )
                for participant in snapshot.participants
            )
        )

    def require_configuration(snapshot: pb.Snapshot, *, client_id: str) -> None:
        require(
            snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION,
            "runtime is not in Configuration",
        )
        require(
            not snapshot.session.HasField("context"),
            "a session context is still active",
        )
        require(
            snapshot.session.cleanup_confirmed
            or not snapshot.session.HasField("outcome"),
            "prior session cleanup is not confirmed",
        )
        require(not snapshot.session.cleanup_blockers, "cleanup blockers remain")
        require(healthy(snapshot), "a required participant is not operational/clean")
        require(
            snapshot.control.holder_client_id == client_id,
            "control lease changed",
        )

    endpoint = _existing_endpoint(default_runtime_root())
    record(
        "launcher_generation",
        {
            "expected": args.expected_controller_generation,
            "observed": endpoint.controller_generation,
        },
    )
    require(
        endpoint.controller_generation == args.expected_controller_generation,
        "launcher endpoint generation differs from the explicit expected generation",
    )
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    history_bytes = HISTORY.read_bytes() if HISTORY.exists() else None
    client = None
    controller_generation = endpoint.controller_generation
    original = None
    applied = None

    def history_unchanged() -> bool:
        return (
            HISTORY.read_bytes() == history_bytes
            if history_bytes is not None
            else not HISTORY.exists()
        )

    def observe(snapshot: pb.Snapshot) -> None:
        display = None
        if snapshot.HasField(
            "visual_stimulus_display"
        ) and snapshot.visual_stimulus_display.HasField("calibration"):
            evidence = snapshot.visual_stimulus_display.calibration
            display = (
                evidence.diagnostic_id,
                evidence.state,
                evidence.resources_closed,
            )
        state = (
            snapshot.session.phase,
            snapshot.session.context.session_id,
            snapshot.trial.phase,
            snapshot.trial.context.trial_id,
            snapshot.session.cleanup_confirmed,
            display,
        )
        if getattr(observe, "last", None) != state:
            observe.last = state
            record(
                "state",
                {
                    "controller_generation": snapshot.controller_generation,
                    "session_phase": pb.SessionPhase.Name(snapshot.session.phase),
                    "session_id": snapshot.session.context.session_id,
                    "trial_phase": pb.TrialPhase.Name(snapshot.trial.phase),
                    "trial_id": snapshot.trial.context.trial_id,
                    "cleanup_confirmed": snapshot.session.cleanup_confirmed,
                    "display_calibration": (
                        {
                            "diagnostic_id": display[0],
                            "state": vs_runtime.DisplayCalibrationState.Name(
                                display[1]
                            ),
                            "resources_closed": display[2],
                        }
                        if display is not None
                        else None
                    ),
                },
            )

    async def run_client() -> None:
        nonlocal client, original, applied
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal, on_snapshot=observe)
            async with client.control(takeover=True):
                initial = client.snapshot
                require(
                    initial.controller_generation == controller_generation,
                    "controller generation changed after launcher discovery",
                )
                require_configuration(initial, client_id=principal.generation)
                require(
                    initial.HasField("configuration_values"), "configuration absent"
                )
                arena = ROOT / "assets" / "calibration" / "frame_grid.glb"
                calibration_intent = capture_display_calibration_intent(
                    initial, arena_path=str(arena)
                )
                record(
                    "calibration_asset_preflight",
                    {
                        "arena_path": calibration_intent["arena_path"],
                        "profile_sha256": calibration_intent["expected_profile_sha256"],
                        "arena_sha256": calibration_intent["expected_arena_sha256"],
                    },
                )
                original = pb.ExperimentConfiguration()
                original.CopyFrom(initial.configuration_values.current)
                (output / "runtime-before.json").write_text(
                    json.dumps(json_message(initial), indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                (output / "configuration-before.json").write_text(
                    json.dumps(json_message(original), indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                history_digest = (
                    hashlib.sha256(history_bytes).hexdigest()
                    if history_bytes is not None
                    else None
                )
                record(
                    "baseline",
                    {
                        "controller_generation": controller_generation,
                        "client_generation": principal.generation,
                        "configuration_revision": initial.configuration.revision,
                        "saved_history_sha256": history_digest,
                    },
                )

                async def command(method: str, request=None, *, wait_s: float = 20):
                    request = client.operator_command() if request is None else request
                    command_id = (
                        request.operator.command_id
                        if isinstance(request, rpc.OperatorCommand)
                        else request.command.operator.command_id
                    )
                    record(
                        "command_attempt", {"method": method, "command_id": command_id}
                    )
                    try:
                        result = await asyncio.wait_for(
                            client.execute(method, request), timeout=wait_s
                        )
                    except Exception as exc:
                        try:
                            save("failure-snapshot.json", await client.get_snapshot())
                        finally:
                            record(
                                "command_uncertain_or_failed",
                                {
                                    "method": method,
                                    "command_id": command_id,
                                    "error": repr(exc),
                                },
                            )
                        raise
                    record("command_result", {"method": method, **asdict(result)})
                    save(f"after-{method.lower()}-{command_id}.json", client.snapshot)
                    require(
                        not result.needs_input,
                        f"{method} requires an operator response; stop for review",
                    )
                    return result

                async def wait_state(name: str, predicate, wait_s: float = 30):
                    try:
                        state = await asyncio.wait_for(client._wait(predicate), wait_s)
                    except Exception:
                        save(f"timeout-{name}.json", await client.get_snapshot())
                        raise
                    save(f"{name}.json", state)
                    return state

                candidate = minimal_trial_configuration(original)
                candidate.recording_root = str(ROOT / "cephvr-data" / "lf26")
                record("candidate_recording_root", candidate.recording_root)
                (output / "configuration-candidate.json").write_text(
                    json.dumps(json_message(candidate), indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                update = rpc.UpdateConfigurationRequest(
                    command=client.operator_command(),
                    expected_revision=client.snapshot.configuration.revision,
                    proposed=candidate,
                )
                update_result = await command("UpdateConfiguration", update)
                require(
                    update_result.succeeded and not update_result.needs_input,
                    f"UpdateConfiguration did not complete: {update_result.failure}",
                )
                require(history_unchanged(), "saved configuration history changed")
                applied = pb.ExperimentConfiguration()
                applied.CopyFrom(client.snapshot.configuration_values.current)
                require(
                    applied == candidate,
                    "controller did not install the exact bounded configuration",
                )
                require_configuration(client.snapshot, client_id=principal.generation)

                setup = await command("Setup", wait_s=120)
                require(setup.succeeded, f"Setup failed: {setup.failure}")
                ready = await wait_state(
                    "ready",
                    lambda state: state.session.phase == pb.SESSION_PHASE_READY,
                    60,
                )
                require(healthy(ready), "required participant health failed at Ready")
                start = await command("StartSession")
                require(start.succeeded, f"StartSession failed: {start.failure}")
                running = await wait_state(
                    "running",
                    lambda state: state.trial.phase == pb.TRIAL_PHASE_RUNNING,
                    30,
                )
                require(
                    running.trial.scheduled_end_monotonic_ns
                    - running.trial.start_monotonic_ns
                    == TRIAL_NS,
                    "prepared trial is not exactly 60 seconds",
                )
                stop = await command("StopAfterTrial")
                require(stop.succeeded, f"StopAfterTrial failed: {stop.failure}")
                terminal = await wait_state(
                    "terminal",
                    lambda state: (
                        state.session.phase == pb.SESSION_PHASE_ENDED
                        and state.session.cleanup_confirmed
                        and state.trial.phase == pb.TRIAL_PHASE_ENDED
                    ),
                    100,
                )
                require(
                    terminal.session.outcome == pb.SESSION_OUTCOME_STOPPED
                    and terminal.trial.outcome == pb.TRIAL_OUTCOME_COMPLETED
                    and terminal.trial.actual_end_monotonic_ns
                    == terminal.trial.scheduled_end_monotonic_ns,
                    "normal trial did not end on its planned schedule with exact cleanup",
                )
                require(
                    healthy(terminal), "required participant health failed at terminal"
                )
                new_session = await command("NewSession")
                require(
                    new_session.succeeded, f"NewSession failed: {new_session.failure}"
                )
                configuration = await wait_state(
                    "new-session",
                    lambda state: (
                        state.session.phase == pb.SESSION_PHASE_CONFIGURATION
                        and not state.session.HasField("context")
                        and state.session.cleanup_confirmed
                    ),
                    30,
                )
                require_configuration(configuration, client_id=principal.generation)

                open_request = open_display_calibration_request(
                    client,
                    arena_path=calibration_intent["arena_path"],
                    expected_revision=client.snapshot.configuration.revision,
                    expected_profile_sha256=calibration_intent[
                        "expected_profile_sha256"
                    ],
                    expected_arena_sha256=calibration_intent["expected_arena_sha256"],
                )
                diagnostic_id = open_request.diagnostic_id
                opened = await command(
                    "OpenDisplayCalibration", open_request, wait_s=60
                )
                require(opened.succeeded, f"diagnostic open failed: {opened.failure}")
                active = await wait_state(
                    "diagnostic-active",
                    lambda state: (
                        state.HasField("visual_stimulus_display")
                        and state.visual_stimulus_display.HasField("calibration")
                        and state.visual_stimulus_display.calibration.diagnostic_id
                        == diagnostic_id
                        and state.visual_stimulus_display.calibration.state
                        == vs_runtime.DISPLAY_CALIBRATION_STATE_ACTIVE
                    ),
                    60,
                )
                save("diagnostic-open.json", active)
                close_request = close_display_calibration_request(
                    client,
                    expected_revision=client.snapshot.configuration.revision,
                    diagnostic_id=diagnostic_id,
                )
                closed = await command(
                    "CloseDisplayCalibration", close_request, wait_s=60
                )
                require(closed.succeeded, f"diagnostic close failed: {closed.failure}")
                idle = await wait_state(
                    "diagnostic-closed",
                    lambda state: (
                        state.HasField("visual_stimulus_display")
                        and state.visual_stimulus_display.HasField("calibration")
                        and state.visual_stimulus_display.calibration.diagnostic_id
                        == diagnostic_id
                        and state.visual_stimulus_display.calibration.state
                        == vs_runtime.DISPLAY_CALIBRATION_STATE_IDLE
                        and state.visual_stimulus_display.calibration.HasField(
                            "resources_closed"
                        )
                        and state.visual_stimulus_display.calibration.resources_closed
                    ),
                    60,
                )
                save("diagnostic-closed.json", idle)
                require(
                    healthy(idle), "required participant health failed after diagnostic"
                )

                if args.leave_ended:
                    second_setup = await command("Setup", wait_s=120)
                    require(
                        second_setup.succeeded,
                        f"second Setup failed: {second_setup.failure}",
                    )
                    await wait_state(
                        "shutdown-ready",
                        lambda state: state.session.phase == pb.SESSION_PHASE_READY,
                        60,
                    )
                    second_start = await command("StartSession")
                    require(
                        second_start.succeeded,
                        f"second StartSession failed: {second_start.failure}",
                    )
                    second_running = await wait_state(
                        "shutdown-running",
                        lambda state: state.trial.phase == pb.TRIAL_PHASE_RUNNING,
                        30,
                    )
                    require(
                        second_running.trial.scheduled_end_monotonic_ns
                        - second_running.trial.start_monotonic_ns
                        == TRIAL_NS,
                        "second prepared trial is not exactly 60 seconds",
                    )
                    second_stop = await command("StopAfterTrial")
                    require(
                        second_stop.succeeded,
                        f"second StopAfterTrial failed: {second_stop.failure}",
                    )
                    ended = await wait_state(
                        "shutdown-ended",
                        lambda state: (
                            state.session.phase == pb.SESSION_PHASE_ENDED
                            and state.session.cleanup_confirmed
                            and state.trial.phase == pb.TRIAL_PHASE_ENDED
                        ),
                        100,
                    )
                    require(
                        ended.session.outcome == pb.SESSION_OUTCOME_STOPPED
                        and ended.trial.outcome == pb.TRIAL_OUTCOME_COMPLETED
                        and ended.trial.actual_end_monotonic_ns
                        == ended.trial.scheduled_end_monotonic_ns,
                        "second trial did not end normally with exact cleanup",
                    )
                    require(
                        healthy(ended), "required participant health failed at Ended"
                    )
                    require(history_unchanged(), "saved configuration history changed")
                    save("final-snapshot.json", ended)
                    record(
                        "left_ended_for_shutdown",
                        {
                            "session_id": ended.session.context.session_id,
                            "cleanup_confirmed": ended.session.cleanup_confirmed,
                            "configuration_restored": False,
                        },
                    )
                    return

                require(history_unchanged(), "saved configuration history changed")
                require_configuration(client.snapshot, client_id=principal.generation)
                require(
                    client.snapshot.configuration_values.current == applied,
                    "configuration changed during the bounded run; do not overwrite it",
                )
                restore = rpc.UpdateConfigurationRequest(
                    command=client.operator_command(),
                    expected_revision=client.snapshot.configuration.revision,
                    proposed=original,
                )
                restored = await command("UpdateConfiguration", restore)
                require(
                    restored.succeeded and not restored.needs_input,
                    f"configuration restore failed: {restored.failure}",
                )
                require(
                    client.snapshot.configuration_values.current == original,
                    "restored runtime configuration differs from the saved baseline",
                )
                require(history_unchanged(), "saved configuration history changed")
                save("final-snapshot.json", client.snapshot)
                record(
                    "complete",
                    {
                        "controller_generation": controller_generation,
                        "diagnostic_id": diagnostic_id,
                        "saved_history_sha256": history_digest,
                        "runtime_configuration_restored": True,
                    },
                )

    try:
        await run_client()
    except Exception as exc:
        record("harness_stopped", {"error": repr(exc), "automatic_retry": False})
        if client is not None:
            try:
                save("failure-snapshot.json", client.snapshot)
            except Exception as snapshot_error:
                record("snapshot_unavailable", {"error": repr(snapshot_error)})
        raise
    finally:
        record(
            "control_release",
            {"release_failure": client.release_failure if client is not None else None},
        )
        store.remove_client(principal)


if __name__ == "__main__":
    asyncio.run(main())
