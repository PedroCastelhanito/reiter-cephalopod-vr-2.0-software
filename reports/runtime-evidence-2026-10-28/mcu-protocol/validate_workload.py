"""Offline validation timing with a same-process scheduling witness; no devices."""
import gc
import json
import threading
import time
from pathlib import Path

from google.protobuf.json_format import ParseDict

from cephvr.control.v1 import types_pb2 as pb
from cephvr.visual_stimulus.configuration import validate_configuration

OUT = Path(__file__).parent
baseline = json.loads((OUT / 'baseline-snapshot.json').read_text('utf-8'))
configuration = ParseDict(baseline['configuration_values']['current'], pb.ExperimentConfiguration())
results = []
for path in Path('C:/Users/ReiterU_PC/Desktop/Alsu/protocols').glob('*.json'):
    data = json.loads(path.read_text('utf-8'))
    candidate = pb.ExperimentConfiguration.FromString(configuration.SerializeToString())
    del candidate.trials[:]
    del candidate.gaps[:]
    candidate.asset_root = data['asset_root']
    for number, trial in enumerate(data['trials'], 1):
        item = candidate.trials.add(trial_number=number)
        item.stimulus.program.program_json = json.dumps(trial['program'])
        if trial['stimulus_seed_decimal']:
            item.stimulus.stimulus_seed_decimal = trial['stimulus_seed_decimal']
        item.stimulus.arena_boundaries.boundaries_json = trial['arena_boundaries_json'] or '{"format_version":1,"bindings":[]}'
    stop = threading.Event()
    ready = threading.Event()
    gaps = []
    collections = []
    gc_starts = {}

    def gc_event(phase, info):
        generation = info['generation']
        if phase == 'start':
            gc_starts[generation] = time.perf_counter_ns()
        elif generation in gc_starts:
            collections.append(dict(generation=generation,
                elapsed_ms=(time.perf_counter_ns()-gc_starts.pop(generation))/1e6))

    def witness():
        last = time.perf_counter_ns()
        ready.set()
        while not stop.wait(0.001):
            now = time.perf_counter_ns()
            gaps.append((now-last)/1e6)
            last = now

    thread = threading.Thread(target=witness)
    thread.start()
    ready.wait()
    gc.callbacks.append(gc_event)
    started = time.perf_counter()
    try:
        result = validate_configuration(candidate)
    finally:
        elapsed = (time.perf_counter()-started)*1000
        gc.callbacks.remove(gc_event)
        stop.set()
        thread.join()
    parsed = [json.loads(t.stimulus.program.program_json) for t in configuration.trials]
    row = dict(name=path.name, validation_ms=elapsed, valid=result.valid,
               witness_max_gap_ms=max(gaps, default=None), samples=len(gaps),
               live_program_matches=parsed == [t['program'] for t in data['trials']],
               gc_events=collections,
               issues=[dict(code=i.failure.code, message=i.failure.message) for i in result.issues])
    results.append(row)
    print(json.dumps(row), flush=True)
(OUT / 'workload-validation.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
