"""Read-only boundary observation without taking control from the trial runner."""

import argparse
import asyncio
import json
from pathlib import Path
import time

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

parser = argparse.ArgumentParser()
parser.add_argument("run", type=Path)
args = parser.parse_args()


def tail_json(path, count=2):
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 131072))
        lines = stream.read().splitlines()
    result = []
    for line in lines:
        try:
            result.append(json.loads(line))
        except ValueError:
            pass
    return result[-count:]


async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    assert endpoint is not None
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16777216) as channel:
            snapshot = await HeadlessClient(channel, principal).get_snapshot()
        now = time.perf_counter_ns()
        (args.run / f"boundary-{now}.pb").write_bytes(snapshot.SerializeToString())
        row = dict(observed_monotonic_ns=now,
                   controller_generation=snapshot.controller_generation,
                   session=MessageToDict(snapshot.session, preserving_proto_field_name=True),
                   trial=MessageToDict(snapshot.trial, preserving_proto_field_name=True),
                   errors=[MessageToDict(e, preserving_proto_field_name=True) for e in snapshot.errors],
                   prompts=[MessageToDict(e, preserving_proto_field_name=True) for e in snapshot.prompts])
        start = snapshot.trial.start_monotonic_ns
        row["elapsed_trial_seconds"] = (now - start) / 1e9 if start else None
        samples = tail_json(args.run / "monitor.jsonl")
        if len(samples) == 2:
            previous, current = samples
            a, b = previous["system"], current["system"]
            total = b["kernel_100ns"] + b["user_100ns"] - a["kernel_100ns"] - a["user_100ns"]
            row["recent_system_cpu_percent"] = 100 * (total - b["idle_100ns"] + a["idle_100ns"]) / total if total and a["valid"] and b["valid"] else None
            row["monitor_sample_duration_ms"] = current["sample_duration_ns"] / 1e6
            row["gpu_samples"] = current["gpu_samples"]
            row["storage"] = current["storage"]
        row["source_tails"] = {}
        for path in Path(snapshot.session.directory).rglob("*_frames.jsonl"):
            rows = tail_json(path, 1)
            row["source_tails"][path.name] = rows[0] if rows else None
            if "stimulus" in path.name:
                for item in reversed(tail_json(path, 64)):
                    item = item.get("payload", item)
                    if item.get("kind") == "render_group":
                        row["stimulus_recent_group"] = item
                        break
        with (args.run / "boundary-observations.jsonl").open("a") as stream:
            stream.write(json.dumps(row) + "\n")
        print(json.dumps(dict(elapsed_seconds=row["elapsed_trial_seconds"],
                              session_phase=row["session"].get("phase"),
                              trial_phase=row["trial"].get("phase"),
                              errors=row["errors"], prompts=row["prompts"],
                              cpu_percent=row.get("recent_system_cpu_percent"),
                              stimulus_group_id=row.get("stimulus_recent_group", {}).get("group_id"),
                              scene=row.get("stimulus_recent_group", {}).get("state", {}).get("scene_id"),
                              epoch=row.get("stimulus_recent_group", {}).get("state", {}).get("epoch_occurrence"),
                              gpu_samples=row.get("gpu_samples"),
                              storage=row.get("storage"))))
    finally:
        store.remove_client(principal)


asyncio.run(main())
