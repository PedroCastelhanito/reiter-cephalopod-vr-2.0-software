"""Actual 600-image CPU preparation/compilation; no graphics or device commands."""
import cProfile
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

from cephvr.visual_stimulus.compiler import CompileContext, compile_trial, serialize_prepared_trial
from cephvr.visual_stimulus.config.models.artifact_models import parse_prepared_json
from cephvr.visual_stimulus.config.models.display_profile import parse_display_json
from cephvr.visual_stimulus.config.models.evidence_model import Identity
from cephvr.visual_stimulus.config.models.program_model import parse_program_json, TrialArenaBoundaries
from cephvr.visual_stimulus.configuration import load_file_policies
from cephvr.visual_stimulus.resources.budget import BoundedBudget
from cephvr.visual_stimulus.resources.prepare import prepare_resources
from cephvr.visual_stimulus.resources.progress import PreparationMetrics

OUT = Path(__file__).parent
protocol_raw = Path("C:/Users/ReiterU_PC/Desktop/Alsu/protocols/texture-presentation-1hr_protocol.json").read_bytes()
doc = json.loads(protocol_raw)
trial = doc["trials"][0]
source = json.dumps(trial["program"])
snapshot = json.loads((OUT.parent / "image-cpu-capacity/native-setup/applied.json").read_text())
backend = next(b for b in snapshot["configuration_values"]["current"]["backends"] if b["backend_name"] == "visual_stimulus")
display = parse_display_json(backend["visual_stimulus"]["display"]["profile_json"], max_bytes=16_777_216)
limits = load_file_policies(Path.cwd()).limits
program = parse_program_json(source, max_bytes=limits.max_document_bytes)
metrics = PreparationMetrics()
start = time.perf_counter()
budget = BoundedBudget(cpu_limit=limits.max_asset_cpu_bytes, gpu_limit=limits.max_asset_gpu_bytes, deadline_ns=time.perf_counter_ns()+180_000_000_000)
bundle = prepare_resources(program, Path(doc["asset_root"]), budget, announce=lambda *_: None,
    snapshot_limit_bytes=limits.max_asset_cpu_bytes, video_index_limit_bytes=limits.decoded_bytes_total,
    glb_element_limit=limits.max_asset_cpu_bytes//256, output_count=len(display.active_outputs),
    display=display, max_document_bytes=limits.max_document_bytes, defer_images=True, metrics=metrics,
    image_progress=lambda done,total: print(f"validated {done}/{total} elapsed={time.perf_counter()-start:.1f}s",flush=True) if done%100==0 else None)
try:
    context = CompileContext(identity=Identity(session_id="benchmark",trial_id="benchmark",configuration_revision=1,prepared_generation="benchmark",renderer_generation="benchmark",resource_generation="benchmark"),display=display,
        arena_boundaries=TrialArenaBoundaries.model_validate_json(trial["arena_boundaries_json"]),manifest=bundle.manifest,seed_decimal=trial.get("stimulus_seed_decimal") or "17",source_json=source,uniform_layouts=bundle.uniform_layouts)
    phase = time.perf_counter()
    plan = compile_trial(program,context,max_expanded_epochs=limits.max_expanded_epochs,max_prepared_plan_bytes=limits.max_prepared_plan_bytes,preparation_budget=budget)
    compilation = time.perf_counter()-phase
    phase = time.perf_counter()
    data = serialize_prepared_trial(plan)
    serialization = time.perf_counter()-phase
    (OUT / "prepared.json").write_bytes(data)
    phase = time.perf_counter()
    parsed = parse_prepared_json(data.decode(),max_bytes=limits.max_prepared_plan_bytes)
    parsing = time.perf_counter()-phase
    assert parsed == plan
    result = dict(protocol_sha256=hashlib.sha256(protocol_raw).hexdigest(),metrics=asdict(metrics),compile_seconds=compilation,serialization_seconds=serialization,parse_seconds=parsing,total_seconds=time.perf_counter()-start,bytes=len(data),epochs=len(plan.epochs))
    (OUT / "preparation.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2),flush=True)
    profiler=cProfile.Profile()
    profiler.runcall(parse_prepared_json,data.decode(),max_bytes=limits.max_prepared_plan_bytes)
    profiler.dump_stats(str(OUT / "parse-before.prof"))
finally:
    assert not bundle.asset_set.close()
