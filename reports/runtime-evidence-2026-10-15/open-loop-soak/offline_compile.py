"""Compile supplied assets and actual geometry without rendering or device access."""

import argparse
import json
from pathlib import Path

from cephvr.control.v1 import types_pb2 as pb
from cephvr.visual_stimulus.compiler.compile import CompileContext, compile_trial
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.config.models.evidence_model import Identity
from cephvr.visual_stimulus.config.models.program_model import Program, TrialArenaBoundaries
from cephvr.visual_stimulus.resources.budget import BoundedBudget
from cephvr.visual_stimulus.resources.prepare import prepare_resources

OUT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--gpu-limit", type=int, default=536_870_912)
parser.add_argument("--label", default="offline-compile")
args = parser.parse_args()
result = {}
for label in ("textures60", "arena60", "combined60", "combined120", "combined900"):
    candidate = pb.ExperimentConfiguration.FromString((OUT / f"candidate-{label}.pb").read_bytes())
    stimulus = candidate.trials[0].stimulus
    program = Program.model_validate_json(stimulus.program.program_json)
    display = DisplayProfile.model_validate_json(next(b.visual_stimulus.display.profile_json for b in candidate.backends if b.backend_name == "visual_stimulus"))
    budget = BoundedBudget(cpu_limit=1_073_741_824, gpu_limit=args.gpu_limit)
    bundle = None
    try:
        bundle = prepare_resources(program, Path(candidate.asset_root), budget,
            announce=lambda *_: None, snapshot_limit_bytes=16_777_216,
            video_index_limit_bytes=16_777_216, glb_element_limit=2_000_000, output_count=4,
            display=display, max_document_bytes=16_777_216)
        context = CompileContext(identity=Identity(session_id="offline", trial_id=label, configuration_revision=1, prepared_generation="offline", renderer_generation="offline", resource_generation="offline"),
            display=display, arena_boundaries=TrialArenaBoundaries.model_validate_json(stimulus.arena_boundaries.boundaries_json), manifest=bundle.manifest,
            seed_decimal=stimulus.stimulus_seed_decimal, source_json=stimulus.program.program_json, uniform_layouts=bundle.uniform_layouts)
        plan = compile_trial(program, context, max_expanded_epochs=100_000, max_prepared_plan_bytes=8_388_608, preparation_budget=budget)
        result[label] = dict(compiled=True, duration_ns=plan.epochs[-1].end_ns, epoch_count=len(plan.epochs), budget=budget.usage.__dict__ if hasattr(budget.usage, "__dict__") else str(budget.usage))
    except Exception as error:
        result[label] = dict(compiled=False, error=f"{type(error).__name__}: {error}")
    finally:
        if bundle is not None:
            result[label]["source_close_errors"] = bundle.asset_set.close()
        result[label]["gpu_limit_bytes"] = args.gpu_limit
        (OUT / f"{args.label}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(label, result[label], flush=True)
if not all(row["compiled"] and not row["source_close_errors"] for row in result.values()):
    raise SystemExit(1)
