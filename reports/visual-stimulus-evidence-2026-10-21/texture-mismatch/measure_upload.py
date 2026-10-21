"""Read-only source/hidden four-context GPU probe; no projector swaps or cameras."""
import hashlib
import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import os
_dll_handles = [os.add_dll_directory(str(Path(r'C:\Users\ReiterU_PC\miniforge3\envs\CephVR') / suffix)) for suffix in ('', 'DLLs', 'Library/bin')]
import glfw
import moderngl
from cephvr.visual_stimulus.config.models.program_model import Asset
from cephvr.visual_stimulus.resources.assets import PreparedAsset
from cephvr.visual_stimulus.resources.budget import BoundedBudget
from cephvr.visual_stimulus.resources.image_source import validate_image_source
from cephvr.visual_stimulus.rendering.image_gpu import ImageGpu

folder = Path(__file__).parent
protocol = json.loads(Path(r'C:\Users\ReiterU_PC\Desktop\Pedro\primate_cuttlebase_20min.json').read_text())
root = Path(protocol['asset_root'])
budget = BoundedBudget(cpu_limit=1<<30, gpu_limit=1<<30)
windows=[]
outputs={}
results=[]
assert glfw.init()
try:
    glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
    for name in ('front','left','right','bottom'):
        window=glfw.create_window(16,16,'CephVR loading probe',None,None)
        assert window
        windows.append(window)
        glfw.make_context_current(window)
        ctx=moderngl.create_context(require=430)
        outputs[name]=SimpleNamespace(context=ctx,activate=lambda w=window:glfw.make_context_current(w))
    renderer=ctx.info['GL_RENDERER']
    print('renderer',renderer,flush=True)
    assert '5060' in renderer,renderer
    gpu=ImageGpu(outputs)
    for row in protocol['trials'][0]['program']['assets'][:4]:
        asset=Asset.model_validate(row)
        raw=(root/asset.logical_path).read_bytes()
        prepared=PreparedAsset(asset.asset_id,asset.logical_path,asset.profile,hashlib.sha256(raw).hexdigest(),len(raw),None,raw)
        source,_=validate_image_source(asset,prepared,budget=budget,owner=asset.asset_id,output_count=1,max_document_bytes=16<<20)
        source=replace(source,output_ids=(asset.asset_id.rsplit('_',1)[1],))
        loads=[]
        for _ in range(5):
            started=time.perf_counter();pixels=source.load(lambda:None);loads.append((time.perf_counter()-started)*1000)
        turns=[]
        textures=[]
        fences=[]
        try:
            complete=False
            while not complete:
                started=time.perf_counter();complete=gpu.upload(source,pixels,textures);turns.append((time.perf_counter()-started)*1000)
            gpu.fence(textures,fences)
            while not gpu.ready(fences):time.sleep(.001)
            texture=next(t for t in textures if t is not None)
            outputs[source.output_ids[0]].activate()
            assert texture.read(alignment=1)==pixels
        finally:gpu.release(textures,fences)
        results.append(dict(asset=asset.logical_path,width=source.width,height=source.height,bytes=len(pixels),decode_ms=loads,upload_turn_ms=turns,turns=len(turns),pixel_readback_exact=True))
        print(results[-1],flush=True)
    result=dict(renderer=renderer,method='Current production decoder and ImageGpu; immutable encoded snapshots; four hidden contexts, no swaps/rendering/recording; unpaced transfer timings; exact GPU readback.',sources=results,upload_sha256=hashlib.sha256(Path('src/cephvr/visual_stimulus/rendering/image_gpu.py').read_bytes()).hexdigest())
    (folder/(sys.argv[1]+'.json')).write_text(json.dumps(result,indent=2)+'\n')
finally:
    for window in reversed(windows):glfw.destroy_window(window)
    glfw.terminate()
