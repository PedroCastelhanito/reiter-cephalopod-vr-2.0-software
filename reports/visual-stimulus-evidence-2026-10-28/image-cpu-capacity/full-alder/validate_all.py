"""Validate all verified ALDER sources sequentially under actual CPU/GPU ceilings."""
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

OUT=Path(__file__).parent
path=Path('C:/Users/ReiterU_PC/Desktop/Alsu/protocols/texture-presentation-1hr_protocol.json')
raw=path.read_bytes()
document=json.loads(raw)
assert len(document['trials'][0]['program']['assets'])==600
assert raw==(OUT/'linear.protocol.json').read_bytes()
provenance={r['asset_id']:r for r in json.loads((OUT/'provenance.json').read_text())['assets']}
limits=load_file_policies(Path.cwd()).limits
started=time.perf_counter()
deadline=time.perf_counter_ns()+240_000_000_000
rows=[]


class PeakBudget(BoundedBudget):
    peak=0

    def reserve(self,**kwargs):
        super().reserve(**kwargs)
        self.peak=max(self.peak,self.usage.cpu_bytes)


for index,item in enumerate(document['trials'][0]['program']['assets'],1):
    asset=Asset.model_validate(item)
    assert asset.color_override.transfer=='linear'
    source=ProtectedWindowsSource(Path(document['asset_root'])/asset.logical_path)
    try:
        with source.independent_reader() as stream:
            sha=hashlib.file_digest(stream,'sha256').hexdigest()
            size=stream.tell()
        assert sha==provenance[asset.asset_id]['source_sha256']
        prepared=PreparedAsset(asset.asset_id,asset.logical_path,asset.profile,sha,size,source,None)
        budget=PeakBudget(cpu_limit=limits.max_asset_cpu_bytes,gpu_limit=limits.max_asset_gpu_bytes,deadline_ns=deadline)
        image,info=validate_image_source(asset,prepared,budget=budget,owner='validation',output_count=4,max_document_bytes=limits.max_document_bytes)
        assert budget.usage.cpu_bytes==budget.usage.gpu_bytes==0
        assert (info.width,info.height)==(3840,2000)
        row=dict(asset_id=asset.asset_id,path=asset.logical_path,source_sha256=sha,
                 cpu_peak_reserved=budget.peak,width=info.width,height=info.height,dtype=info.dtype,status='validated')
        rows.append(row)
        with (OUT/'validation-events.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(row)+'\n')
    finally:
        source.close_after_consumers()
    if index%25==0:
        print(f'Full protected decode/conversion/output validation: {index}/600; elapsed {time.perf_counter()-started:.1f}s',flush=True)

result=dict(protocol_sha256=hashlib.sha256(raw).hexdigest(),images=rows,seconds=time.perf_counter()-started,
    cpu_limit=limits.max_asset_cpu_bytes,gpu_limit=limits.max_asset_gpu_bytes)
(OUT/'validation-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('All600 source validations pass; maximum source reservation',max(r['cpu_peak_reserved'] for r in rows),flush=True)
