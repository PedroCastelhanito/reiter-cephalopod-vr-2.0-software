"""Protected native image validation only; no graphics, serial or camera access."""
import hashlib
import json
import time
from pathlib import Path

from cephvr.platform.windows.protected_source import ProtectedWindowsSource
from cephvr.visual_stimulus.config.models.program_model import Asset
from cephvr.visual_stimulus.configuration import load_file_policies
from cephvr.visual_stimulus.resources.assets import PreparedAsset
from cephvr.visual_stimulus.resources.budget import BoundedBudget
from cephvr.visual_stimulus.resources.image_source import validate_image_source
from cephvr.visual_stimulus.resources.media import MediaPreparationError

OUT = Path(__file__).parent
path = Path('C:/Users/ReiterU_PC/Desktop/Alsu/protocols/texture-presentation-1hr_protocol.json')
raw = path.read_bytes()
document = json.loads(raw)
limits = load_file_policies(Path.cwd()).limits
assert limits.max_asset_cpu_bytes == 2_147_483_648
assert limits.max_asset_gpu_bytes == 4_294_967_296


class PeakBudget(BoundedBudget):
    peak = 0

    def reserve(self, **kwargs):
        super().reserve(**kwargs)
        self.peak = max(self.peak, self.usage.cpu_bytes)


rows = []
for item in document['trials'][0]['program']['assets']:
    asset = Asset.model_validate(item)
    source = ProtectedWindowsSource(Path(document['asset_root']) / asset.logical_path)
    try:
        with source.independent_reader() as reader:
            digest = hashlib.file_digest(reader, 'sha256').hexdigest()
            count = reader.tell()
        prepared = PreparedAsset(asset.asset_id, asset.logical_path, asset.profile,
                                 digest, count, source, None)
        if not rows:
            old = BoundedBudget(cpu_limit=1_073_741_824, gpu_limit=limits.max_asset_gpu_bytes)
            try:
                validate_image_source(asset, prepared, budget=old, owner='old-limit',
                                      output_count=4, max_document_bytes=limits.max_document_bytes)
            except MemoryError as error:
                print('old ceiling:', str(error), flush=True)
            else:
                raise AssertionError('Expected old CPU ceiling rejection')
            assert old.usage.cpu_bytes == 0
        budget = PeakBudget(cpu_limit=limits.max_asset_cpu_bytes, gpu_limit=limits.max_asset_gpu_bytes)
        started = time.perf_counter()
        try:
            image, info = validate_image_source(asset, prepared, budget=budget, owner='validation',
                                               output_count=4, max_document_bytes=limits.max_document_bytes)
        except MediaPreparationError as error:
            if 'image transfer/primaries are not explicit' not in str(error):
                raise
            row = dict(path=asset.logical_path, source_sha256=digest, encoded_bytes=count,
                       cpu_peak_reserved=budget.peak, status='blocked_colour_declaration',
                       failure=str(error), seconds=time.perf_counter()-started)
        else:
            row = dict(path=asset.logical_path, source_sha256=digest, encoded_bytes=count,
                       width=info.width, height=info.height, dtype=info.dtype,
                       cpu_peak_reserved=budget.peak, subsequent_load_cpu_bytes=image.cpu_bytes,
                       status='validated', seconds=time.perf_counter()-started)
        assert budget.usage.cpu_bytes == budget.usage.gpu_bytes == 0
        rows.append(row)
        print(json.dumps(row), flush=True)
    finally:
        source.close_after_consumers()

(OUT / 'results.json').write_text(json.dumps(dict(protocol_sha256=hashlib.sha256(raw).hexdigest(),
    cpu_limit=limits.max_asset_cpu_bytes, gpu_limit=limits.max_asset_gpu_bytes, images=rows), indent=2), encoding='utf-8')
