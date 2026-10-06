"""Bounded live controller diagnostics using a temporary nonparticipating draft."""

import asyncio
import json
import sys
import tomllib
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.credentials import CredentialStore, default_runtime_root


async def run():
    root = Path(__file__).resolve().parents[2]
    settings = tomllib.loads(
        (root / "config/backends/experiment_config.toml").read_text()
    )["rpc"]
    store = CredentialStore(default_runtime_root(), sys.argv[1])
    principal = store.provision_client("cli")
    result = {"captured_at": datetime.now().astimezone().isoformat()}
    try:
        async with loopback_channel(settings["port"], settings["max_message_bytes"]) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control():
                state = client.snapshot
                result["controller_generation"] = state.controller_generation
                result["phase"] = pb.SessionPhase.Name(state.session.phase)
                result["configuration_revision"] = state.configuration.revision
                result["initial_devices"] = MessageToDict(
                    state.acquisition_devices, preserving_proto_field_name=True
                )
                for kind in (
                    rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT,
                ):
                    name = rpc.MicrocontrollerCommandKind.Name(kind)
                    try:
                        outcome = await asyncio.wait_for(
                            client.execute(
                                "ExecuteMicrocontrollerCommand",
                                rpc.MicrocontrollerCommandRequest(
                                    command=client.operator_command(),
                                    expected_configuration_revision=client.snapshot.configuration.revision,
                                    kind=kind,
                                ),
                            ), 12
                        )
                        result[name] = asdict(outcome)
                    except Exception as exc:
                        result[name] = {"error": str(exc)}
                acquisition = next(
                    item.acquisition
                    for item in client.snapshot.configuration_values.current.backends
                    if item.backend_name == "acquisition"
                )
                original = pb.ExperimentConfiguration()
                original.CopyFrom(client.snapshot.configuration_values.current)
                proposed = pb.ExperimentConfiguration()
                proposed.CopyFrom(original)
                entry = next(item for item in proposed.backends if item.backend_name == "acquisition")
                entry.enabled = True
                entry.acquisition.behavioral.enabled = False
                entry.acquisition.tracking.enabled = False
                outcome = await client.execute("UpdateConfiguration", rpc.UpdateConfigurationRequest(
                    command=client.operator_command(),
                    expected_revision=client.snapshot.configuration.revision,
                    proposed=proposed,
                ))
                result["diagnostic_configuration"] = asdict(outcome)
                if not outcome.succeeded:
                    raise RuntimeError(outcome.failure)
                # Both assignments are tested without session enablement or capture.
                for role, value in ((1, acquisition.behavioral), (2, acquisition.tracking)):
                    try:
                        outcome = await asyncio.wait_for(client.execute(
                            "ExecuteCameraCommand",
                            rpc.CameraCommandRequest(
                                command=client.operator_command(),
                                expected_configuration_revision=client.snapshot.configuration.revision,
                                camera=role,
                                kind=rpc.CAMERA_COMMAND_KIND_TEST_CONNECTION,
                            ),
                        ), 12)
                        result[value.device.device_id] = asdict(outcome)
                    except Exception as exc:
                        result[value.device.device_id] = {"error": f"{type(exc).__name__}: {exc}"}
                result["final_devices"] = MessageToDict(
                    client.snapshot.acquisition_devices, preserving_proto_field_name=True
                )
                outcome = await client.execute("UpdateConfiguration", rpc.UpdateConfigurationRequest(
                    command=client.operator_command(),
                    expected_revision=client.snapshot.configuration.revision,
                    proposed=original,
                ))
                result["restore_original_configuration"] = asdict(outcome)
            result["control_release_failure"] = client.release_failure
    except Exception as exc:
        result["error"] = repr(exc)
    finally:
        store.remove_client(principal)
        (Path(__file__).parent / "managed-connections.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, indent=2))


asyncio.run(asyncio.wait_for(run(), 55))
