"""Preserve reusable configuration and request an exact normal runtime exit."""
import asyncio
import argparse
import dataclasses
import json
from pathlib import Path

from google.protobuf.json_format import ParseDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.platform.windows.guard import SingleInstanceGuard
from cephvr.shared.credentials import CredentialStore, default_runtime_root
from cephvr.shared.recovery import RecoveryStore

OUT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--verify-shutdown-save", action="store_true")
parser.add_argument("--label", default="restart")
parser.add_argument("--failed-setup", action="store_true")
parser.add_argument("--prepared-dummy", action="store_true")
parser.add_argument("--ended-dummy", action="store_true")
args = parser.parse_args()

async def main():
    root = default_runtime_root()
    endpoint = _existing_endpoint(root)
    store = CredentialStore(root, endpoint.controller_generation)
    principal = store.provision_client("cli")
    result = {"controller_generation": endpoint.controller_generation}
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                original = await client.get_snapshot()
                allowed_failed = (
                    args.failed_setup and original.session.phase == pb.SESSION_PHASE_SETTING_UP
                    and original.configuration_values.current.subject == "DUMMY"
                    and original.configuration_values.current.experiment == "gui_backend_dummy"
                )
                allowed_prepared = (
                    args.prepared_dummy and original.session.phase == pb.SESSION_PHASE_READY
                    and original.configuration_values.current.subject == "DUMMY"
                    and original.configuration_values.current.experiment == "gui_backend_dummy"
                )
                allowed_ended = (
                    args.ended_dummy and original.session.phase == pb.SESSION_PHASE_ENDED
                    and original.configuration_values.current.subject == "DUMMY"
                    and original.configuration_values.current.experiment == "gui_backend_dummy"
                )
                if original.session.phase != 1 and not allowed_failed and not allowed_prepared and not allowed_ended:
                    raise RuntimeError("Normal test restart requires Configuration phase")
                (OUT / f"pre-{args.label}-snapshot.pb").write_bytes(original.SerializeToString())
                if args.verify_shutdown_save:
                    proposed = pb.ExperimentConfiguration()
                    proposed.CopyFrom(original.configuration_values.current)
                    proposed.experiment = "DUMMY_SHUTDOWN_HISTORY_CHECK"
                    changed = await client.execute("UpdateConfiguration", rpc.UpdateConfigurationRequest(
                        command=client.operator_command(), expected_revision=original.configuration.revision,
                        proposed=proposed))
                    result["marker_update"] = dataclasses.asdict(changed)
                    if not changed.succeeded:
                        raise RuntimeError(changed.failure)
                else:
                    proposed = original.configuration_values.current
                    saved = await client.execute("SaveConfigurationHistory")
                    result["save"] = dataclasses.asdict(saved)
                    if not saved.succeeded:
                        raise RuntimeError(saved.failure)
                try:
                    result["shutdown"] = dataclasses.asdict(await client.execute("ShutdownApplication"))
                except Exception as exc:
                    result["shutdown_watch"] = str(exc)
        for _ in range(600):
            receipt = RecoveryStore(root).read_exit_receipt(endpoint.controller_generation)
            if receipt is not None:
                if receipt.supervisor_generation != endpoint.supervisor_generation:
                    raise RuntimeError("Exit receipt supervisor generation mismatch")
                with SingleInstanceGuard("application"):
                    result["exit_receipt"] = dataclasses.asdict(receipt)
                    result["application_guard_released"] = True
                history = json.loads((OUT.parents[2] / "config/last_configuration.json").read_text(encoding="utf-8"))
                restored = ParseDict(history["configuration"], pb.ExperimentConfiguration())
                result["history_matches_accepted_configuration"] = restored == proposed
                break
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("Exact normal exit not confirmed")
    finally:
        store.remove_client(principal)
        (OUT / f"{args.label}-shutdown.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))

asyncio.run(main())
