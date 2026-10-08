"""Bounded GUI-command-path compile/upload with native stderr retained separately."""

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.gui.managed_device_commands import dispatch_device_action
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).parent
SUFFIX = sys.argv[1]
SKETCH = OUT.parents[1] / "firmware/uno/cephvr2_mcu/cephvr2_mcu.ino"
recorded = {"scope": "checked-in protocol-3 Uno GUI-command-path compile/upload; no configuration edit or scientific session", "checks": {}}


def record(key, value):
    recorded["checks"][key] = value
    (OUT / f"ino-upload-{SUFFIX}.json").write_text(json.dumps(recorded, indent=2), encoding="utf-8")
    print(key, flush=True)


async def run():
    for _ in range(60):
        try:
            endpoint = _existing_endpoint(default_runtime_root())
            break
        except Exception:
            await asyncio.sleep(0.5)
    else:
        raise RuntimeError("Runtime endpoint unavailable")
    recorded["controller_generation"] = endpoint.controller_generation
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                await asyncio.sleep(3)
                try:
                    record("original_configuration", MessageToDict(client.snapshot.configuration_values.current, preserving_proto_field_name=True))
                    assert SKETCH.is_file(), SKETCH
                    for cycle in range(int(sys.argv[2]) if len(sys.argv) > 2 else 1):
                        result = await asyncio.wait_for(dispatch_device_action(client, "mcu_upload", {"path": str(SKETCH.resolve())}, principal), 120)
                        record(f"upload_{cycle}", result)
                        record(f"after_{cycle}", MessageToDict((await client.get_snapshot()).microcontroller, preserving_proto_field_name=True))
                        await asyncio.sleep(2)
                    if SUFFIX == "final":
                        before = (await client.get_snapshot()).microcontroller
                        directory = OUT / "ino-upload-rejected-source"
                        directory.mkdir(exist_ok=True)
                        rejected = directory / "ino-upload-rejected-source.ino"
                        rejected.write_text('#error Deliberate_ino_compile_rejection\nvoid setup() {}\nvoid loop() {}\n', encoding="utf-8")
                        try:
                            await dispatch_device_action(client, "mcu_upload", {"path": str(rejected.resolve())}, principal)
                        except Exception as exc:
                            assert "Deliberate_ino_compile_rejection" in str(exc), str(exc)
                            record("compile_rejection", str(exc))
                        else:
                            raise AssertionError("Invalid sketch was accepted")
                        after = (await client.get_snapshot()).microcontroller
                        assert after.observation.connection_id == before.observation.connection_id
                        assert not after.cleanup_pending
                        record("rejection_serial_preserved", True)
                        record("rejection_after", MessageToDict(after, preserving_proto_field_name=True))
                except Exception as exc:
                    record("error", f"{type(exc).__name__}: {exc}")
                finally:
                    try:
                        result = await client.execute("ShutdownApplication", client.operator_command())
                        record("shutdown", asdict(result))
                    except Exception as exc:
                        record("shutdown_error", str(exc))
            record("release_failure", client.release_failure)
    finally:
        store.remove_client(principal)


asyncio.run(run())
