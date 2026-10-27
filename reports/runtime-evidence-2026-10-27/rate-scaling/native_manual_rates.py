"""Bounded exact-generation headless lease-release probe; inert without --execute."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
import tomllib
from dataclasses import asdict
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

ROOT = Path(__file__).resolve().parents[3]
ROLES = ("behavioral", "tracking", "eye_tracking")
DIAGNOSTICS = ("errors", "warnings", "recoveries", "runtime_incidents")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def document(message):
    return MessageToDict(message, preserving_proto_field_name=True)


def check_idle(state, generation):
    require(state.controller_generation == generation, "controller generation changed")
    require(
        state.session.phase == pb.SESSION_PHASE_CONFIGURATION
        and not state.session.HasField("context")
        and not state.session.shutdown_requested,
        "unexpected session or application shutdown",
    )
    require(not state.session.cleanup_blockers, "session cleanup blockers remain")
    require(
        state.session.cleanup_confirmed or not state.session.HasField("outcome"),
        "prior cleanup is not confirmed",
    )
    require(not state.prompts, "operator input required; probe cannot answer")
    require(
        not state.microcontroller.diagnostic.active
        and not state.acquisition_devices.diagnostic.active
        and not state.tracking_diagnostic.active,
        "unexpected diagnostic activity",
    )


def cameras_closed(state, *, required=()):
    return all(
        (role not in required and not view.ByteSize())
        or (
            all(
                view.HasField(field) and not getattr(view, field)
                for field in ("device_open", "preview_running", "cleanup_pending")
            )
            and not view.preview_prepared
            and not view.preview_run_id
        )
        for role, view in (
            (role, getattr(state.acquisition_devices, role)) for role in ROLES
        )
    )


async def run(args):
    output = args.output.resolve()
    require(output.is_relative_to(ROOT), "output must remain in the workspace")
    require(not output.exists(), "use a fresh evidence directory")
    endpoint = _existing_endpoint(default_runtime_root())
    require(
        endpoint is not None
        and endpoint.controller_generation == args.expected_controller_generation,
        "explicit controller generation does not match the live endpoint",
    )
    output.mkdir(parents=True)

    def record(kind, value):
        event = {"host_ns": time.perf_counter_ns(), "kind": kind, "value": value}
        with (output / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event) + "\n")
        print(kind, json.dumps(value), flush=True)

    def save(name, state):
        (output / name).write_text(
            json.dumps(document(state), indent=2), encoding="utf-8"
        )

    paths = sorted((ROOT / "config/backends").glob("*.toml")) + [
        ROOT / "config" / name
        for name in ("last_configuration.json", "runtime_gui.json", "review_draft.json")
    ]
    baseline = {path: path.read_bytes() if path.exists() else None for path in paths}
    record(
        "settings_before",
        {
            str(path.relative_to(ROOT)): hashlib.sha256(data).hexdigest()
            if data
            else None
            for path, data in baseline.items()
        },
    )
    settings = tomllib.loads(
        (ROOT / "config/backends/experiment_config.toml").read_text()
    )
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    client = None
    try:
        async with loopback_channel(
            settings["rpc"]["port"], settings["rpc"]["max_message_bytes"]
        ) as channel:
            client = HeadlessClient(channel, principal)
            async with client.observe():
                initial = client.snapshot
                save("initial.json", initial)
                check_idle(initial, args.expected_controller_generation)
                require(
                    cameras_closed(initial),
                    "pre-existing camera ownership; do not take over",
                )
                require(
                    not initial.microcontroller.cleanup_pending, "MCU cleanup remains"
                )
                require(
                    not initial.microcontroller.HasField("observation"),
                    "pre-existing MCU connection",
                )
                require(
                    all(op.complete for op in initial.operations),
                    "pending manual operation",
                )
                baseline_diagnostics = {
                    field: {
                        item.SerializeToString(deterministic=True)
                        for item in getattr(initial, field)
                    }
                    for field in DIAGNOSTICS
                }
                acquisition = next(
                    backend.acquisition
                    for backend in initial.configuration_values.current.backends
                    if backend.backend_name == "acquisition"
                )
                selected = [
                    role
                    for role in ROLES
                    if getattr(acquisition, role).enabled
                    and getattr(acquisition, role).device.frame_timing
                    == camera.FRAME_TIMING_EXTERNAL_TRIGGER
                ]
                require(
                    len(selected) == 2,
                    "probe requires exactly two enabled external cameras",
                )
                require(
                    all(
                        getattr(acquisition, role).device.device_id for role in selected
                    ),
                    "configured camera ID missing",
                )
                record("selected_roles", selected)

                def check(state, *, owned=False):
                    check_idle(state, args.expected_controller_generation)
                    require(
                        state.configuration_values.current
                        == initial.configuration_values.current
                        and state.configuration.revision
                        == initial.configuration.revision,
                        "configuration/readback changed; stop probe without blind restoration",
                    )
                    for field in DIAGNOSTICS:
                        require(
                            all(
                                item.SerializeToString(deterministic=True)
                                in baseline_diagnostics[field]
                                for item in getattr(state, field)
                            ),
                            f"new {field}; retain evidence and inspect before further work",
                        )
                    require(not state.microcontroller.failure, "MCU failure")
                    require(
                        all(
                            not getattr(
                                state.acquisition_devices, role
                            ).last_failure.code
                            for role in ROLES
                        ),
                        "camera failure",
                    )
                    if owned:
                        require(
                            state.control.holder_client_id == principal.generation
                            and state.control.control_generation == lease_generation,
                            "exact lease lost; no further mutations",
                        )

                await client.claim_control(takeover=True)
                lease_generation = client.snapshot.control.control_generation
                check(client.snapshot, owned=True)
                runs = {}
                for role in selected:
                    check(client.snapshot, owned=True)
                    request = rpc.CameraCommandRequest(
                        command=client.operator_command(),
                        expected_configuration_revision=initial.configuration.revision,
                        camera=getattr(camera, "CAMERA_ROLE_" + role.upper()),
                        kind=rpc.CAMERA_COMMAND_KIND_START_PREVIEW,
                    )
                    record(
                        "command_attempt",
                        {
                            "method": "ExecuteCameraCommand",
                            "role": role,
                            "command_id": request.command.operator.command_id,
                        },
                    )
                    result = await asyncio.wait_for(
                        client.execute("ExecuteCameraCommand", request), 45
                    )
                    record("command_result", asdict(result))
                    save("after-start-" + role + ".json", client.snapshot)
                    require(
                        result.succeeded and not result.needs_input,
                        f"{role} preview did not succeed",
                    )
                    check(client.snapshot, owned=True)
                    view = getattr(client.snapshot.acquisition_devices, role)
                    require(
                        view.device_open
                        and view.preview_running
                        and view.preview_run_id,
                        f"{role} capture unconfirmed",
                    )
                    require(not view.preview_visible, "unexpected native viewer")
                    require(
                        view.device.configured_id
                        == getattr(acquisition, role).device.device_id
                        and view.device.physical_id,
                        "camera identity mismatch",
                    )
                    runs[role] = view.preview_run_id
                def measured(state):
                    check(state, owned=True)
                    now = time.perf_counter_ns()
                    return all(
                        view.acquisition_rate.acquisition_run_id == runs[role]
                        and view.acquisition_rate.device_id == getattr(acquisition, role).device.device_id
                        and view.acquisition_rate.HasField("received_fps")
                        and 0 < view.acquisition_rate.received_fps < 10000
                        and view.acquisition_rate.observed_monotonic_ns <= now < view.acquisition_rate.valid_until_monotonic_ns
                        for role, view in (
                            (role, getattr(state.acquisition_devices, role))
                            for role in selected
                        )
                    )
                await asyncio.wait_for(client._wait(measured), 20)
                check(client.snapshot, owned=True)
                require(
                    all(
                        getattr(
                            client.snapshot.acquisition_devices, role
                        ).preview_running
                        and getattr(
                            client.snapshot.acquisition_devices, role
                        ).preview_run_id
                        == run
                        for role, run in runs.items()
                    ),
                    "capture run changed before release",
                )
                save("before-release.json", client.snapshot)
                await asyncio.sleep(15)  # Bounded native HUD observation while capture remains headless.
                request = client.operator_command()
                record(
                    "release_attempt",
                    {"command_id": request.operator.command_id, "runs": runs},
                )
                admission = await client._admit("ReleaseControl", request)
                record("release_admission", document(admission))

                def released(state):
                    check(state)
                    require(
                        state.control.holder_client_id in ("", principal.generation),
                        "another client took control during observation",
                    )
                    return (
                        state.control.holder_client_id != principal.generation
                        and cameras_closed(state, required=selected)
                        and all(
                            not getattr(state.acquisition_devices, role).HasField("acquisition_rate")
                            for role in selected
                        )
                        and not state.microcontroller.cleanup_pending
                        and not state.microcontroller.HasField("observation")
                        and all(op.complete for op in state.operations)
                    )

                terminal = await asyncio.wait_for(client._wait(released), 45)
                save("release-confirmed.json", terminal)
                # Keep the same read-only watch briefly to catch delayed escalation.
                await asyncio.sleep(3)
                require(released(client.snapshot), "release did not remain stable")
                save("release-stable.json", client.snapshot)
                record(
                    "result",
                    {
                        "lease_release_and_closed_views": True,
                        "no_reacquisition": True,
                        "native_ring_proof": "verify retained worker/supervisor evidence separately",
                    },
                )
    except Exception as exc:
        if client is not None and client.views.current is not None:
            save("failure-snapshot.json", client.snapshot)
        record("failure", {"error": repr(exc), "retry": False})
        raise
    finally:
        unchanged = {
            str(path.relative_to(ROOT)): (path.read_bytes() if path.exists() else None)
            == data
            for path, data in baseline.items()
        }
        record("settings_unchanged", unchanged)
        record("control_release_failure", client.release_failure if client else None)
        store.remove_client(principal)
        require(
            all(unchanged.values()),
            "saved settings changed; no blind file restoration performed",
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-controller-generation")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.execute:
        print(
            json.dumps(
                {
                    "execute": False,
                    "scope": "two configured external-camera headless captures, exact lease release, read-only closure observation",
                    "settings_changes": False,
                }
            )
        )
        return
    require(
        args.output and args.expected_controller_generation,
        "execution requires exact generation and fresh output",
    )
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
