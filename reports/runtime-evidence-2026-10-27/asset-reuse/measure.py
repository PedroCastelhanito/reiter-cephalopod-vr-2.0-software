"""Bounded native 4K preparation comparison; no projection or experiment devices."""

import hashlib
import json
import subprocess
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from cephvr.visual_stimulus.config.models.program_model import Asset
from cephvr.visual_stimulus.resources.assets import ProtectedFingerprintCache
from cephvr.visual_stimulus.resources.budget import BoundedBudget
from cephvr.visual_stimulus.resources.prepare import prepare_resources
from cephvr.visual_stimulus.resources.progress import PreparationMetrics


def run(root, assets, reuse):
    budget = BoundedBudget(cpu_limit=2_000_000_000, gpu_limit=1_000_000_000)
    fingerprints = ProtectedFingerprintCache(budget) if reuse else None
    metrics = PreparationMetrics()
    validations = {}
    bundles = []
    started = time.perf_counter()
    try:
        for index in range(6):
            bundles.append(prepare_resources(
                SimpleNamespace(assets=assets, sequence=(), instances=()),
                root, budget, announce=lambda *_: None,
                snapshot_limit_bytes=2_000_000_000,
                video_index_limit_bytes=1_000_000, glb_element_limit=100,
                owner_prefix=f"trial{index}", defer_images=True,
                validated_images=validations, fingerprints=fingerprints,
                metrics=metrics, component_provenance=(),
            ))
        return {"reuse": reuse, "elapsed_seconds": time.perf_counter() - started,
                **asdict(metrics)}
    finally:
        for bundle in bundles:
            assert bundle.asset_set.close() == ()


if __name__ == "__main__":
    destination = Path(__file__).resolve().parent
    metadata = PngInfo()
    metadata.add(b"sRGB", b"\x00")
    with tempfile.TemporaryDirectory(prefix="inputs-", dir=destination) as temporary:
        root = Path(temporary)
        assets = []
        for index in range(2):
            pixels = np.random.default_rng(index).integers(
                0, 256, (2160, 3840, 3), dtype=np.uint8
            )
            Image.fromarray(pixels).save(root / f"image{index}.png", pnginfo=metadata)
            assets.append(Asset(asset_id=f"image{index}", logical_path=f"image{index}.png",
                                profile="png_uint_v1", color_override=None))
        del pixels
        # Reverse order on the second pair to expose simple warm-cache/order effects.
        results = [run(root, tuple(assets), reuse) for reuse in (False, True, True, False)]
    files = [Path("src/cephvr/visual_stimulus/resources") / name for name in
             ("assets.py", "prepare.py", "progress.py", "session.py")]
    evidence = {
        "date": "2026-10-27", "revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True).strip(),
        "source_sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in files},
        "scope": "Two seeded 3840x2160 RGB8 PNGs, six repeated trials; CPU preparation only. "
                 "No schedule compilation, GPU upload, projection or full-workload claim.",
        "results": results,
    }
    (destination / "measurement.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
