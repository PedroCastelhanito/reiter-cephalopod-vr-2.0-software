"""Read-only image conversion comparison; retained before implementation as oracle."""
import importlib.util
import json
import statistics
import time
from pathlib import Path

from cephvr.visual_stimulus.config.models.program_model import Asset
from cephvr.visual_stimulus.resources.media import decode_image
from cephvr.visual_stimulus.rendering.upload import linear_rgba_bytes

OUT = Path(__file__).parent
spec = importlib.util.spec_from_file_location("upload_before", OUT / "upload_before.py")
before = importlib.util.module_from_spec(spec)
spec.loader.exec_module(before)
protocol = json.loads(Path("C:/Users/ReiterU_PC/Desktop/Alsu/protocols/texture-presentation-1hr_protocol.json").read_text())
asset = Asset.model_validate(protocol["trials"][0]["program"]["assets"][0])
raw = (Path(protocol["asset_root"]) / asset.logical_path).read_bytes()
pixels = decode_image(asset, raw)
assert before.linear_rgba_bytes(pixels) == linear_rgba_bytes(pixels)
rows = {}
for label, fn in (("before", before.linear_rgba_bytes), ("after", linear_rgba_bytes)):
    for stage in ("conversion", "decode_and_conversion"):
        samples = []
        for _ in range(12):
            start = time.perf_counter()
            data = fn(pixels if stage == "conversion" else decode_image(asset, raw))
            del data
            samples.append(time.perf_counter() - start)
        rows[label + "_" + stage] = {"median_seconds": statistics.median(samples), "samples": samples}
(OUT / "conversion.json").write_text(json.dumps(rows, indent=2))
print(json.dumps(rows, indent=2), flush=True)
