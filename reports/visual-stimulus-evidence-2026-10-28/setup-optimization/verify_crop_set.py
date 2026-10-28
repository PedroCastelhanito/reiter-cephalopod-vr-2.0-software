"""Full-set float32 shader equivalence with production crop planning/packing/upload."""
import os, sys, json, struct, time, hashlib
from pathlib import Path
from types import SimpleNamespace as NS
_dlls=[os.add_dll_directory(str(p)) for p in (Path(sys.base_prefix),Path(sys.base_prefix)/'DLLs',Path(sys.base_prefix)/'Library/bin') if p.is_dir()]
import numpy as np
import glfw, moderngl
from cephvr.visual_stimulus.config.models.artifact_models import GeometricProfile
from cephvr.visual_stimulus.config.models.display_profile import parse_display_json
from cephvr.visual_stimulus.config.models.program_model import Asset
from cephvr.visual_stimulus.rendering.image_fold import calibrated_fold_map
from cephvr.visual_stimulus.rendering.image_fit import valid_image_pixels
from cephvr.visual_stimulus.rendering.image_gpu import ImageGpu
from cephvr.visual_stimulus.rendering.upload import linear_rgba_bytes
from cephvr.visual_stimulus.resources.media import decode_image
from cephvr.visual_stimulus.resources.image_source import ImageSource
from cephvr.visual_stimulus.resources.image_crops import fold_crop, cropped_source
from cephvr.visual_stimulus.rendering.shaders import _QUAD_VERTEX, _LAYER_FRAGMENT
OUT=Path(__file__).parent
s=json.loads((OUT/'observed-terminal.json').read_text())['configuration_values']['current']
root=Path(s['asset_root'])
b=next(x for x in s['backends'] if x['backend_name']=='visual_stimulus')
d=parse_display_json(b['visual_stimulus']['display']['profile_json'],max_bytes=16777216)
profiles=[GeometricProfile.model_validate_json((root/m.geometric_profile.logical_path).read_text()) for m in d.active_mappings]
program=json.loads(s['trials'][0]['stimulus']['program']['program_json'])
assert len(program['assets'])==600
assert glfw.init(); glfw.window_hint(glfw.VISIBLE,glfw.FALSE)
w=glfw.create_window(32,32,'Full-set crop equivalence',None,None); glfw.make_context_current(w)
ctx=moderngl.create_context(require=430)
assert '5060' in ctx.info['GL_RENDERER']
prog=ctx.program(vertex_shader=_QUAD_VERTEX,fragment_shader=_LAYER_FRAGMENT)
vbo=ctx.buffer(np.array([-1,-1,0,0,1,-1,1,0,-1,1,0,1,1,1,1,1],np.float32).tobytes())
vao=ctx.vertex_array(prog,[(vbo,'2f 2f','in_position','in_uv')])
flags=ctx.buffer(reserve=16); flags.bind_to_storage_buffer(3)
prog['mode'].value=8; prog['opacity'].value=1; prog['image_tex'].value=0
gpu=ImageGpu({p.output_id:NS(context=ctx,activate=lambda:glfw.make_context_current(w)) for p in profiles})
rows=[]; started=time.perf_counter()
try:
    for i,item in enumerate(program['assets'],1):
        asset=Asset.model_validate(item); raw=(root/asset.logical_path).read_bytes()
        pixels=linear_rgba_bytes(decode_image(asset,raw))
        source=ImageSource(asset.asset_id,3840,2000,1500000000,491520000,lambda check:pixels)
        artifact=NS(display=d,geometric_calibration=profiles)
        rects={p.output_id:fold_crop(artifact,p.mapping_id,source) or (0,0,3840,2000) for p in profiles}
        planned=cropped_source(source,rects); packed=planned.load(lambda:None)
        textures=[]
        while not gpu.upload(planned,packed,textures): pass
        full=ctx.texture((3840,2000),4,pixels,dtype='f4'); full.repeat_x=full.repeat_y=False
        differences=[]
        for j,p in enumerate(profiles):
            fold=calibrated_fold_map(d.geometry,profiles,p)
            crop=next(c for c in planned.output_crops if c.output_id==p.output_id)
            target=ctx.texture(valid_image_pixels(p),4,dtype='f4'); fbo=ctx.framebuffer([target]); fbo.use()
            outputs=[]
            for tex,mapping in ((full,fold),(textures[j],(fold[0]-crop.x,fold[1]-crop.y,*fold[2:]))):
                prog['image_fold_map'].write(struct.pack('6f',*mapping)); tex.use(); vao.render(moderngl.TRIANGLE_STRIP)
                outputs.append(fbo.read(components=4,dtype='f4'))
            assert outputs[0]==outputs[1], (asset.asset_id,p.surface_id,float(np.max(np.abs(np.frombuffer(outputs[0],np.float32)-np.frombuffer(outputs[1],np.float32)))))
            differences.append(0)
            fbo.release(); target.release()
        gpu.release(textures,[]); full.release()
        rows.append(dict(asset_id=asset.asset_id,sha256=hashlib.sha256(raw).hexdigest(),different_components=differences))
        if i%50==0: print(f'{i}/600 exact four-output matches; {time.perf_counter()-started:.1f}s',flush=True)
    result=dict(gpu=ctx.info['GL_RENDERER'],seconds=time.perf_counter()-started,rectangles=rects,bytes_per_change=planned.gpu_bytes,images=rows,scope='actual Fold shader and RGBA32F framebuffer equality at valid-area dimensions; no downstream calibration/optical acceptance')
    (OUT/'crop-set-equivalence.json').write_text(json.dumps(result,indent=2))
finally:
    vao.release(); vbo.release(); flags.release(); prog.release(); ctx.release(); glfw.make_context_current(None); glfw.destroy_window(w); glfw.terminate()
