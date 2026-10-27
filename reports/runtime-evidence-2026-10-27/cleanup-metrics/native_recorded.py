"""Prepared bounded native recording harness. No workload runs without --execute."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
import tomllib
from dataclasses import asdict
from pathlib import Path

from google.protobuf.json_format import MessageToDict, ParseDict

from cephvr.client.session import ClientError, HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.protocol_document import blank_program
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root
from cephvr.visual_stimulus.config.models.program_model import Fixed, Time

ROOT = Path(__file__).resolve().parents[3]
ROLES = ("behavioral", "tracking", "eye_tracking")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def document(message):
    return MessageToDict(message, preserving_proto_field_name=True)


def candidate_configuration(original, output, seconds):
    require(seconds == 60, "E05 permits this bounded harness only at 60 seconds")
    candidate = pb.ExperimentConfiguration()
    candidate.CopyFrom(original)
    candidate.mode = pb.SESSION_MODE_OPEN_LOOP
    candidate.subject = "RIGCHECK"
    candidate.experiment = "hierarchy_audit"
    candidate.recording_root = str(output / "recordings")
    candidate.subject_metadata.Clear()
    selected = []
    for backend in candidate.backends:
        backend.enabled = backend.backend_name in ("acquisition", "visual_stimulus")
        if backend.backend_name == "acquisition":
            for role in ROLES:
                settings = getattr(backend.acquisition, role)
                if settings.enabled:
                    require(settings.device.device_id, f"{role}: configured ID missing")
                    settings.save_video = True
                    selected.append(role)
        if backend.backend_name == "visual_stimulus":
            backend.visual_stimulus.save_visual_stimulus_data = True
    require(selected, "no currently enabled configured camera")
    require(candidate.trials, "no current trial to bound")
    del candidate.trials[1:]
    del candidate.gaps[:]
    candidate.trials[0].trial_number = 1
    program = blank_program()
    epoch = program.sequence[0].model_copy(
        update={"duration": Fixed(kind="fixed", duration=Time(seconds=str(seconds)))}
    )
    program = program.model_copy(update={"sequence": (epoch,)})
    reference = candidate.trials[0].stimulus.program
    reference.ClearField("logical_source_reference")
    reference.program_json = program.model_dump_json()
    return candidate, selected


def validate_candidate(candidate):
    from cephvr.controller.configuration import controller_validators
    from cephvr.controller.startup.providers import _installed_validators

    results = {
        name: validator(candidate)
        for name, validator in controller_validators(
            _installed_validators(ROOT)
        ).items()
    }
    require(
        all(result.completed and result.valid for result in results.values()),
        "authoritative offline candidate validation failed: "
        + json.dumps({name: document(result) for name, result in results.items()}),
    )
    return {name: document(result) for name, result in results.items()}


async def run(args):
    output = args.output.resolve()
    require(output.is_relative_to(ROOT), "output must remain inside the workspace")
    require(not output.exists(), "output already exists; select a fresh directory")
    output.mkdir(parents=True)
    (output / "recordings").mkdir()

    def record(kind, value):
        entry = {"host_ns": time.perf_counter_ns(), "kind": kind, "value": value}
        with (output / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry) + "\n")
        print(kind, json.dumps(value), flush=True)

    def save(name, message):
        (output / name).write_text(
            json.dumps(document(message), indent=2), encoding="utf-8"
        )

    settings_paths = [*sorted((ROOT / "config/backends").glob("*.toml"))]
    settings_paths += [
        ROOT / "config" / name
        for name in ("last_configuration.json", "runtime_gui.json", "review_draft.json")
    ]
    baseline = {
        path: path.read_bytes() if path.exists() else None for path in settings_paths
    }
    backup = output / "settings-before"
    backup.mkdir()
    for path, content in baseline.items():
        if content is not None:
            (backup / path.name).write_bytes(content)
    record(
        "settings_before",
        {
            str(path.relative_to(ROOT)): hashlib.sha256(data).hexdigest()
            if data is not None
            else None
            for path, data in baseline.items()
        },
    )
    endpoint = _existing_endpoint(default_runtime_root())
    require(
        endpoint.controller_generation == args.expected_controller_generation,
        "fresh controller generation does not match",
    )
    controller = tomllib.loads(
        (ROOT / "config/backends/experiment_config.toml").read_text()
    )
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    client = None
    original = None
    applied = None
    revision = None
    session_id = None
    lease_generation = None
    update_rejected = False

    def authority(snapshot):
        require(
            snapshot.controller_generation == args.expected_controller_generation,
            "controller generation changed",
        )
        require(
            snapshot.control.holder_client_id == principal.generation,
            "exact control lease lost; no further mutation",
        )
        require(
            lease_generation is None
            or snapshot.control.control_generation == lease_generation,
            "control lease generation changed; no further mutation",
        )

    async def command(method, request=None, wait_s=45):
        nonlocal update_rejected
        authority(client.snapshot)
        request = client.operator_command() if request is None else request
        command_id = (
            request.operator.command_id
            if isinstance(request, rpc.OperatorCommand)
            else request.command.operator.command_id
        )
        record("command_attempt", {"method": method, "command_id": command_id})
        try:
            result = await asyncio.wait_for(client.execute(method, request), wait_s)
        except Exception as exc:
            update_rejected = (
                method == "UpdateConfiguration"
                and applied is None
                and isinstance(exc, ClientError)
                and not exc.admission_uncertain
                and str(exc).startswith("REJECTED:")
            )
            save("command-failure-snapshot.json", client.snapshot)
            record(
                "command_failed_or_uncertain",
                {
                    "method": method,
                    "command_id": command_id,
                    "error": repr(exc),
                    "retry": False,
                },
            )
            raise
        record("command_result", {"method": method, **asdict(result)})
        save(f"after-{method}-{result.command_id}.json", client.snapshot)
        require(
            result.succeeded and not result.needs_input,
            f"{method} failed/needs input: {result.failure}",
        )
        return result

    async def wait_state(name, predicate, wait_s=60):
        state = await asyncio.wait_for(client._wait(predicate), wait_s)
        authority(state)
        save(name + ".json", state)
        return state

    async def restore():
        authority(client.snapshot)
        state = client.snapshot
        if state.session.HasField("context"):
            require(
                session_id and state.session.context.session_id == session_id,
                "different/unknown session; do not change it",
            )
        if state.session.phase in (pb.SESSION_PHASE_SETTING_UP, pb.SESSION_PHASE_READY):
            await command("CancelSetup", wait_s=60)
        elif state.session.phase in (
            pb.SESSION_PHASE_STARTING,
            pb.SESSION_PHASE_RUNNING,
        ):
            await command("AbortNow", wait_s=60)
        state = await wait_state(
            "cleanup-confirmed",
            lambda s: (
                (
                    s.session.cleanup_confirmed
                    or (
                        not s.session.HasField("context")
                        and not s.session.HasField("outcome")
                    )
                )
                and not s.session.cleanup_blockers
                and s.session.phase
                in (pb.SESSION_PHASE_ENDED, pb.SESSION_PHASE_CONFIGURATION)
            ),
            90,
        )
        if state.session.phase == pb.SESSION_PHASE_ENDED:
            await command("NewSession")
        require(
            client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION,
            "not Configuration after cleanup",
        )
        require(
            not client.snapshot.session.HasField("context"), "session identity remains"
        )
        require(
            client.snapshot.configuration.revision == revision,
            "configuration revision changed externally; no overwrite",
        )
        require(
            client.snapshot.configuration_values.current == applied,
            "configuration changed since application; no overwrite",
        )
        await command(
            "UpdateConfiguration",
            rpc.UpdateConfigurationRequest(
                command=client.operator_command(),
                expected_revision=revision,
                proposed=original,
            ),
        )
        require(
            client.snapshot.configuration_values.current == original,
            "runtime restore is not exact",
        )
        save("restored-runtime.json", client.snapshot)

    try:
        async with loopback_channel(
            controller["rpc"]["port"], controller["rpc"]["max_message_bytes"]
        ) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                initial = client.snapshot
                lease_generation = initial.control.control_generation
                authority(initial)
                require(
                    initial.session.phase == pb.SESSION_PHASE_CONFIGURATION,
                    "runtime is not in Configuration",
                )
                require(
                    not initial.session.HasField("context"), "a session remains active"
                )
                require(
                    initial.session.cleanup_confirmed
                    or not initial.session.HasField("outcome"),
                    "prior cleanup is not confirmed",
                )
                require(not initial.session.cleanup_blockers, "cleanup blockers remain")
                require(not initial.prompts, "operator prompts remain")
                require(
                    all(operation.complete for operation in initial.operations),
                    "an operator/manual camera or MCU operation remains pending",
                )
                require(
                    not initial.microcontroller.cleanup_pending
                    and not initial.microcontroller.diagnostic.active,
                    "MCU cleanup or diagnostic remains active",
                )
                require(
                    not initial.acquisition_devices.diagnostic.active,
                    "acquisition MCU diagnostic remains active",
                )
                require(
                    all(
                        not getattr(initial.acquisition_devices, role).preview_running
                        and not getattr(
                            initial.acquisition_devices, role
                        ).preview_prepared
                        and not getattr(
                            initial.acquisition_devices, role
                        ).preview_run_id
                        and not getattr(
                            initial.acquisition_devices, role
                        ).cleanup_pending
                        for role in ROLES
                    ),
                    "manual preview/cleanup remains on a camera role",
                )
                require(
                    not initial.HasField("tracking_diagnostic")
                    or not initial.tracking_diagnostic.active,
                    "Tracking diagnostic remains active",
                )
                original = pb.ExperimentConfiguration()
                original.CopyFrom(initial.configuration_values.current)
                save("initial-snapshot.json", initial)
                candidate, roles = candidate_configuration(
                    original, output, args.seconds
                )
                record("live_candidate_validation", validate_candidate(candidate))
                acquisition = next(
                    b.acquisition
                    for b in candidate.backends
                    if b.backend_name == "acquisition"
                )
                for role in roles:
                    view = getattr(initial.acquisition_devices, role)
                    device = getattr(acquisition, role).device
                    require(
                        not view.cleanup_pending, f"{role}: cleanup ownership remains"
                    )
                    require(
                        not view.preview_running
                        and not view.preview_prepared
                        and not view.preview_run_id,
                        f"{role}: manual preview ownership remains; do not start this probe",
                    )
                    if view.device_open:
                        require(
                            view.device.configured_id == device.device_id
                            and view.device.physical_id,
                            f"{role}: live configured/physical identity mismatch",
                        )
                        require(
                            view.applied_settings == device.settings,
                            f"{role}: live settings mismatch",
                        )
                    record(
                        "manual_device_before_setup",
                        {
                            "role": role,
                            "view": document(view),
                            "native_validation": "already-connected identity/settings verified"
                            if view.device_open
                            else "deferred to normal Setup native validation and exact Ready",
                        },
                    )
                save("candidate.json", candidate)
                record("selected_cameras", roles)
                try:
                    await command(
                        "UpdateConfiguration",
                        rpc.UpdateConfigurationRequest(
                            command=client.operator_command(),
                            expected_revision=initial.configuration.revision,
                            proposed=candidate,
                        ),
                    )
                    applied = pb.ExperimentConfiguration()
                    applied.CopyFrom(client.snapshot.configuration_values.current)
                    revision = client.snapshot.configuration.revision
                    require(applied == candidate, "candidate was not applied exactly")
                    await command("Setup", wait_s=220)
                    session_id = client.snapshot.session.context.session_id
                    ready = await wait_state(
                        "ready", lambda s: s.session.phase == pb.SESSION_PHASE_READY
                    )
                    require(
                        any(
                            p.process.role == "acquisition"
                            and p.required
                            and p.ready.required_checks_passed
                            for p in ready.participants
                        )
                        and all(
                            not p.required
                            or (
                                p.process_running
                                and p.connected
                                and p.health == "LAUNCH_PHASE_OPERATIONAL"
                                and not p.outstanding_obligations
                            )
                            for p in ready.participants
                        ),
                        "required participant unhealthy at Ready",
                    )
                    await command("StartSession")
                    running = await wait_state(
                        "running", lambda s: s.trial.phase == pb.TRIAL_PHASE_RUNNING, 30
                    )
                    require(
                        running.session.context.session_id == session_id,
                        "session identity changed",
                    )
                    require(
                        running.trial.scheduled_end_monotonic_ns
                        - running.trial.start_monotonic_ns
                        == args.seconds * 1_000_000_000,
                        "trial duration is not bounded exactly",
                    )
                    trial_id = running.trial.context.trial_id
                    await command("StopAfterTrial")
                    terminal = await wait_state(
                        "terminal",
                        lambda s: (
                            s.session.phase == pb.SESSION_PHASE_ENDED
                            and s.session.cleanup_confirmed
                            and s.trial.phase == pb.TRIAL_PHASE_ENDED
                        ),
                        args.seconds + 90,
                    )
                    require(
                        terminal.session.context.session_id == session_id
                        and terminal.trial.context.trial_id == trial_id,
                        "terminal identity changed",
                    )
                    require(
                        terminal.trial.outcome == pb.TRIAL_OUTCOME_COMPLETED
                        and terminal.session.outcome == pb.SESSION_OUTCOME_STOPPED
                        and terminal.trial.actual_end_monotonic_ns
                        == terminal.trial.scheduled_end_monotonic_ns,
                        "trial completion/interval is not exact",
                    )
                    record("recording_directory", terminal.session.directory)
                finally:
                    if (
                        applied is None
                        and client.snapshot.configuration_values.current == candidate
                    ):
                        # Exact installed state may survive an uncertain Update reply.
                        applied = pb.ExperimentConfiguration()
                        applied.CopyFrom(candidate)
                        revision = client.snapshot.configuration.revision
                    if applied is not None:
                        if session_id is None and client.snapshot.session.HasField(
                            "context"
                        ):
                            session_id = client.snapshot.session.context.session_id
                        try:
                            await restore()
                        except Exception as exc:
                            save("restoration-failed-snapshot.json", client.snapshot)
                            record(
                                "restoration_failed",
                                {"error": repr(exc), "blind_file_restore": False},
                            )
                            raise
                    elif update_rejected and all(
                        (
                            client.snapshot.configuration == initial.configuration,
                            client.snapshot.configuration_values
                            == initial.configuration_values,
                            client.snapshot.session == initial.session,
                            client.snapshot.trial == initial.trial,
                            client.snapshot.controller_generation
                            == initial.controller_generation,
                        )
                    ):
                        save("update-rejected-unchanged.json", client.snapshot)
                        record(
                            "runtime_unchanged_after_rejection",
                            {
                                "explicit_admission_rejected": True,
                                "setup_ran": False,
                                "runtime_configuration_and_work_exact": True,
                            },
                        )
                    else:
                        record(
                            "runtime_restoration_unconfirmed",
                            {
                                "reason": "Update did not confirm candidate installation; no blind restore or retry",
                                "parent_followup_required": True,
                            },
                        )
    finally:
        record(
            "settings_unchanged",
            {
                str(path.relative_to(ROOT)): (
                    path.read_bytes() if path.exists() else None
                )
                == content
                for path, content in baseline.items()
            },
        )
        record(
            "control_release", {"failure": client.release_failure if client else None}
        )
        store.remove_client(principal)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-controller-generation")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seconds", type=int, choices=(60,), default=60)
    args = parser.parse_args()
    original = ParseDict(
        json.loads((ROOT / "config/last_configuration.json").read_text())[
            "configuration"
        ],
        pb.ExperimentConfiguration(),
    )
    candidate, roles = candidate_configuration(
        original, Path("PREVIEW-ONLY"), args.seconds
    )
    validation = validate_candidate(candidate)
    if not args.execute:
        print(
            json.dumps(
                {
                    "execute": False,
                    "seconds": args.seconds,
                    "camera_roles": roles,
                    "authoritative_validation": validation,
                }
            )
        )
        return
    require(
        args.output and args.expected_controller_generation,
        "execution needs explicit fresh output and exact controller generation",
    )
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
