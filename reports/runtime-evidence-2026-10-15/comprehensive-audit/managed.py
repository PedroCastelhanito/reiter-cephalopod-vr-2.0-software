"""Bounded authenticated operations with exact current configuration evidence."""

import argparse
import asyncio
import dataclasses
import json
from pathlib import Path
import time

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.gui.managed_device_commands import dispatch_device_action
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

parser = argparse.ArgumentParser()
parser.add_argument("mode", choices=("previews", "mcu", "shutdown", "recover"))
parser.add_argument("--label", required=True)
args = parser.parse_args()
out = Path(__file__).parent / args.label
out.mkdir(exist_ok=False)
record = {"mode": args.mode, "events": []}


def view(value):
    return MessageToDict(value, preserving_proto_field_name=True)


def keep(name, value):
    record["events"].append({"name": name, "monotonic_ns": time.perf_counter_ns(), "value": value})
    (out / "events.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(name, json.dumps(value), flush=True)


async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    assert endpoint is not None
    record["generation"] = endpoint.controller_generation
    keep("endpoint", {"controller_generation": endpoint.controller_generation})
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                keep("control", view(client.snapshot.control))
                assert client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION
                assert not client.snapshot.prompts or args.mode == "recover"
                (out / "before.pb").write_bytes(client.snapshot.SerializeToString())
                original = client.snapshot.configuration_values.current.SerializeToString()
                if args.mode == "recover":
                    assert len(client.snapshot.prompts) == 1
                    prompt = client.snapshot.prompts[0]
                    assert prompt.setup.controller_generation in {"d36751b3-82b5-4ff7-8054-3a5c31cae8a4", "aeeeb20a-4ba2-4584-918e-e181a3dbcb9b"}
                    assert "comprehensive_audit_textures60-cq23" in prompt.explanation
                    keep("recovery_prompt", view(prompt))
                    response = rpc.PromptResponse(command=client.operator_command(), prompt_id=prompt.prompt_id, setup=prompt.setup, setup_operation=prompt.operation, choice="continue")
                    result = await asyncio.wait_for(client.execute("RespondToPrompt", response), 30)
                    keep("recovery", dataclasses.asdict(result))
                    assert result.succeeded and not client.snapshot.prompts
                    return
                if args.mode == "shutdown":
                    result = await asyncio.wait_for(client.execute("ShutdownApplication"), 90)
                    keep("shutdown", dataclasses.asdict(result))
                    assert result.succeeded
                    return
                if args.mode == "mcu":
                    result = await asyncio.wait_for(dispatch_device_action(client, "mcu", {"kind": rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT}, principal), 90)
                    keep("connect", result)
                    assert result and result[0]
                    keep("microcontroller", view(client.snapshot.microcontroller))
                if args.mode == "previews":
                    for cycle in range(2):
                        for role, name in ((1, "behavioral"), (2, "tracking"), (3, "eye_tracking")):
                            prior = getattr(client.snapshot.acquisition_devices, name)
                            assert not (prior.device_open or prior.preview_run_id or prior.cleanup_pending)
                            try:
                                result = await asyncio.wait_for(dispatch_device_action(client, "camera", {"role": role, "kind": rpc.CAMERA_COMMAND_KIND_START_PREVIEW, "show_preview": False}, principal), 40)
                                keep(f"{cycle}-{name}-start", result)
                                assert result and result[0]
                                await asyncio.sleep(2)
                                keep(f"{cycle}-{name}-active", view(getattr(client.snapshot.acquisition_devices, name)))
                            finally:
                                current = getattr(client.snapshot.acquisition_devices, name)
                                if current.device_open or current.preview_run_id or current.cleanup_pending:
                                    result = await asyncio.wait_for(dispatch_device_action(client, "camera", {"role": role, "kind": rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW}, principal), 40)
                                    keep(f"{cycle}-{name}-stop", result)
                                    assert result and result[0]
                            released = getattr(client.snapshot.acquisition_devices, name)
                            keep(f"{cycle}-{name}-released", view(released))
                            assert not (released.device_open or released.preview_run_id or released.cleanup_pending)
                keep("configuration_unchanged", client.snapshot.configuration_values.current.SerializeToString() == original)
                (out / "after.pb").write_bytes(client.snapshot.SerializeToString())
    except BaseException as error:
        try:
            current = client.snapshot
            (out / "failure.pb").write_bytes(current.SerializeToString())
            keep("failure_snapshot", view(current))
        except Exception as snapshot_error:
            keep("failure_snapshot_error", str(snapshot_error))
        keep("error", f"{type(error).__name__}: {error}")
        raise
    finally:
        store.remove_client(principal)


asyncio.run(main())
