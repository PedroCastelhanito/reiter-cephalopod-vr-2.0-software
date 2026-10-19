"""Isolate native writing readback with managed controller shut down."""
import asyncio
import json
import time
from pathlib import Path
from google.protobuf.json_format import MessageToDict, ParseDict
from cephvr.control.v1 import types_pb2 as pb
from cephvr.synchronization.client import SpikeGLXControllerClient
from cephvr.shared.clock import host_time_ns

OUT = Path(__file__).parent
EVENTS = []
def event(**values):
    EVENTS.append(dict(wall_time=time.time(), **values))
    (OUT / "writing-probe.json").write_text(json.dumps(EVENTS, indent=2))
    print(json.dumps(EVENTS[-1]), flush=True)

async def main():
    client = SpikeGLXControllerClient(Path.cwd(), controller_generation="bounded-probe")
    config = ParseDict(json.loads((OUT / "normal-candidate.json").read_text()), pb.ExperimentConfiguration())
    prepared = await client.prepare(config, pb.SessionContext(), "PAIRPROBE-" + time.strftime("%H%M%S"))
    event(prepared=MessageToDict(prepared))
    progress = client._require_progress_io()
    sample = progress.sample_counts
    async def observed(deadline):
        started = time.monotonic()
        try:
            readback, counts = await sample(deadline)
            event(elapsed=time.monotonic()-started, running=readback.running, saving=readback.saving, name=readback.run_name, counts=counts)
            return readback, counts
        except Exception as exc:
            event(elapsed=time.monotonic()-started, error=repr(exc))
            raise
    progress.sample_counts = observed
    try:
        event(writing_gate=await client.start_and_verify_writing())
    finally:
        event(stopped=await client.stop_expected_run(host_time_ns()+20_000_000_000))
        client.io_owner.close(wait=True)

asyncio.run(main())
