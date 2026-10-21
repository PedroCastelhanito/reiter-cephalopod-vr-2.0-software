"""Bounded retained-config CPU/GIL susceptibility probe; no runtime or device RPCs."""
import asyncio
import hashlib
import json
import platform
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from google.protobuf.json_format import ParseDict
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.projections import ProjectionStore
from cephvr.controller.state import (
    ConfigurationState, LifecycleState, ControlState, MetadataState,
    SupervisorState, IncidentState, LimitsState, Watch,
)
from cephvr.visual_stimulus.config.models.program_model import Program
from tests.controller.support_components import default_limits

OUT = Path(__file__).parent
BASE = OUT.parent / "rig-validation"

def profile(label, operation, iterations):
    stop = threading.Event()
    ready = threading.Event()
    gaps = []
    def observer():
        previous = time.perf_counter_ns()
        ready.set()
        while not stop.wait(.001):
            now = time.perf_counter_ns()
            gaps.append(now - previous)
            previous = now
    thread = threading.Thread(target=observer)
    thread.start()
    ready.wait()
    time.sleep(.03)
    spans = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        operation()
        spans.append(time.perf_counter_ns() - started)
    time.sleep(.03)
    stop.set()
    thread.join()
    ordered = sorted(spans)
    return {"label": label, "iterations": iterations,
            "call_max_ms": max(spans) / 1e6,
            "call_median_ms": ordered[len(ordered)//2] / 1e6,
            "observer_gap_max_ms": max(gaps, default=0) / 1e6,
            "observer_gaps_over_100ms": sum(x > 100_000_000 for x in gaps),
            "observer_samples": len(gaps)}

results = []
inputs = []
for label, path in (
    ("dummy", BASE / "test-configuration-attached.json"),
    ("full", BASE / "full-texture/test-configuration-attached.json"),
):
    raw = path.read_bytes()
    config = ParseDict(json.loads(raw), pb.ExperimentConfiguration())
    generation = str(uuid4())
    control = ControlState()
    publisher = SnapshotPublisher(
        generation=generation, clock=time.perf_counter_ns,
        configuration=ConfigurationState(config, pb.ControlPolicies()),
        lifecycle=LifecycleState(), control=control, metadata=MetadataState(8),
        supervisor=SupervisorState(0), incidents=IncidentState(),
        projections=ProjectionStore(generation, {}, max_entries=256, max_payload_bytes=16_777_216),
        limits=LimitsState(default_limits()),
    )
    snapshot = publisher.build_snapshot()
    assert snapshot.configuration_values.current == config
    inputs.append({"label": label, "path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                   "configuration_bytes": config.ByteSize(), "snapshot_bytes": snapshot.ByteSize(),
                   "trial_program_chars": [len(t.stimulus.program.program_json) for t in config.trials]})
    results.append(profile(label + ":build_snapshot", publisher.build_snapshot, 1000))
    results.append(profile(label + ":serialize_snapshot", snapshot.SerializeToString, 1000))
    results.append(profile(label + ":publish_zero_watchers", publisher.publish, 1000))
    control.watches[("probe", "one")] = Watch("probe", "one", asyncio.Queue(maxsize=1), 1)
    results.append(profile(label + ":publish_one_watcher", publisher.publish, 1000))
    programs = [t.stimulus.program.program_json for t in config.trials]
    results.append(profile(label + ":validate_program_models",
                           lambda: [Program.model_validate_json(p) for p in programs], 5))

summary = {"scope": "Offline same-process retained-config susceptibility probe, not historical causality or serial/rig timing acceptance.",
           "watch_scope": "Historical actual watcher count was not retained. One HeadlessClient watch is established by the helper; a live GUI process does not prove an active GUI watch. Zero/one synthetic watchers tested.",
           "observer": "Own thread requests 1ms waits; OS scheduling, timer resolution and GIL all affect observed gaps. Defaults unchanged.",
           "python": sys.version, "platform": platform.platform(), "gil_switch_interval_s": sys.getswitchinterval(),
           "inputs": inputs, "results": results}
(OUT / "controller-gil-profile.json").write_text(json.dumps(summary, indent=2))
for row in results:
    print(row, flush=True)
