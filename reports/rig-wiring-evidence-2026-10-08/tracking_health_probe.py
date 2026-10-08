"""Bounded managed Tracking import/Connect/Stop with retained heartbeat stderr."""

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.managed_device_commands import dispatch_device_action
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).parent
SUFFIX = sys.argv[1]
result = {"scope": "real managed Tracking preview; no scientific session", "checks": {}}


def record(name, value):
    result["checks"][name] = value
    (OUT / f"tracking-health-{SUFFIX}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(name, flush=True)


async def run():
    for _ in range(60):
        try:
            endpoint = _existing_endpoint(default_runtime_root())
            break
        except Exception:
            await asyncio.sleep(0.5)
    else:
        raise RuntimeError("launcher endpoint unavailable")
    result["controller_generation"] = endpoint.controller_generation
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                await asyncio.sleep(3)
                original = pb.ExperimentConfiguration()
                original.CopyFrom(client.snapshot.configuration_values.current)
                record("original", MessageToDict(original, preserving_proto_field_name=True))
                try:
                    await dispatch_device_action(client, "save_camera_settings", {
                        "serial": "40747103", "clock": "External controller", "source": "Line2",
                        "preset": "C:/Data/projects/reiter-cephalopod-vr/cephvr-assets/camera-configs/a2A2464-77umPRO_40747103_BehaviorSquid.pfs",
                        "rate": "60", "import_preset": True,
                    }, principal)
                    record("import", "confirmed")
                    for cycle in range(2):
                        await dispatch_device_action(client, "camera", {
                            "role": 2, "kind": rpc.CAMERA_COMMAND_KIND_START_PREVIEW,
                            "show_preview": True,
                        }, principal)
                        record(f"start_{cycle}", "confirmed")
                        await asyncio.sleep(6)
                        record(f"running_{cycle}", MessageToDict((await client.get_snapshot()).acquisition_devices.tracking, preserving_proto_field_name=True))
                        await dispatch_device_action(client, "camera", {"role": 2, "kind": rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW}, principal)
                        record(f"stop_{cycle}", "confirmed")
                except Exception as exc:
                    record("error", f"{type(exc).__name__}: {exc}")
                finally:
                    try:
                        restored = await client.execute("UpdateConfiguration", rpc.UpdateConfigurationRequest(command=client.operator_command(), expected_revision=client.snapshot.configuration.revision, proposed=original))
                        record("restore", asdict(restored))
                    except Exception as exc:
                        record("restore_error", str(exc))
                    try:
                        closed = await client.execute("ShutdownApplication", client.operator_command())
                        record("shutdown", asdict(closed))
                    except Exception as exc:
                        record("shutdown_error", str(exc))
            record("release_failure", client.release_failure)
    finally:
        store.remove_client(principal)


asyncio.run(run())
