"""Bounded real-device checks using the exact managed GUI dispatch helpers."""
import asyncio
import json
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.gui.managed_device_commands import dispatch_device_action
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).parent
record = {"scope": "actual GUI command dispatch, native devices; no experiment", "checks": {}}

def keep(name, value):
    record["checks"][name] = value
    (OUT / "live-features.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(name, json.dumps(value), flush=True)

async def run():
    endpoint = _existing_endpoint(default_runtime_root())
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    record["controller_generation"] = endpoint.controller_generation
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                original = await client.get_snapshot()
                if original.session.phase != 1:
                    raise RuntimeError("Controller is no longer in Configuration")
                settings = next(b.acquisition for b in original.configuration_values.current.backends if b.backend_name == "acquisition")
                cameras = [(i, getattr(settings, role).device.device_id) for i, role in ((1, "behavioral"), (2, "tracking")) if getattr(settings, role).enabled]
                for name, action, options in (
                    ("camera_connections", "test_cameras", {"cameras": cameras}),
                    ("mcu_connect", "mcu", {"kind": rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT}),
                    ("mcu_status", "mcu", {"kind": rpc.MICROCONTROLLER_COMMAND_KIND_STATUS}),
                    ("spikeglx_connection", "spikeglx_connection", {}),
                ):
                    try:
                        keep(name, await dispatch_device_action(client, action, options, principal))
                    except Exception as exc:
                        keep(name, {"error": f"{type(exc).__name__}: {exc}"})
                for role, serial in cameras:
                    name = f"camera_{serial}"
                    try:
                        keep(name + "_connect", await dispatch_device_action(client, "camera", {"role": role, "kind": rpc.CAMERA_COMMAND_KIND_START_PREVIEW}, principal))
                        await asyncio.sleep(3)
                        state = await client.get_snapshot()
                        view = state.acquisition_devices.behavioral if role == 1 else state.acquisition_devices.tracking
                        keep(name + "_state", MessageToDict(view, preserving_proto_field_name=True))
                    except Exception as exc:
                        keep(name + "_error", {"error": f"{type(exc).__name__}: {exc}"})
                    finally:
                        try:
                            keep(name + "_disconnect", await dispatch_device_action(client, "camera", {"role": role, "kind": rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW}, principal))
                        except Exception as exc:
                            keep(name + "_cleanup_error", {"error": f"{type(exc).__name__}: {exc}"})
                state = await client.get_snapshot()
                keep("configuration_unchanged", state.configuration_values.current == original.configuration_values.current)
                keep("final_devices", MessageToDict(state.acquisition_devices, preserving_proto_field_name=True))
            keep("release_failure", client.release_failure)
    finally:
        store.remove_client(principal)

asyncio.run(run())
