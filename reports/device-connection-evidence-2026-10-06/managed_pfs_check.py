"""Restore the operator draft and repeat its selected PFS import, without capture."""

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

from google.protobuf.json_format import MessageToDict, ParseDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.device_requests import import_camera_preset
from cephvr.shared.credentials import CredentialStore, default_runtime_root


async def run():
    output = Path(__file__).parent
    store = CredentialStore(default_runtime_root(), sys.argv[1])
    principal = store.provision_client("cli")
    result = {"generation": sys.argv[1]}
    try:
        proposed = ParseDict(json.loads((output / "settings-preserved-draft.json").read_text()), pb.ExperimentConfiguration())
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control():
                outcome = await client.execute("UpdateConfiguration", rpc.UpdateConfigurationRequest(
                    command=client.operator_command(), expected_revision=client.snapshot.configuration.revision,
                    proposed=proposed,
                ))
                result["restore_operator_draft"] = asdict(outcome)
                if not outcome.succeeded:
                    raise RuntimeError(outcome.failure)
                settings = next(b.acquisition.behavioral.device for b in proposed.backends if b.backend_name == "acquisition")
                await import_camera_preset(client, 1, settings.pfs_source_filename)
                result["managed_pfs_import_and_finish"] = "passed"
                state = await client.get_snapshot()
                result["devices"] = MessageToDict(state.acquisition_devices, preserving_proto_field_name=True)
                result["configuration_revision"] = state.configuration.revision
            result["lease_released"] = client.release_failure is None
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        store.remove_client(principal)
        (output / "managed-pfs-check.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))


asyncio.run(asyncio.wait_for(run(), 55))
