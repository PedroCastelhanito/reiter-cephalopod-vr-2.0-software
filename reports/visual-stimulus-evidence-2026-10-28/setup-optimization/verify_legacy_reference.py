"""Full-set float32 shader equivalence with production crop planning/packing/upload."""
import os, sys, json, struct, time, hashlib, ast, subprocess
from pathlib import Path
from types import SimpleNamespace as NS
from dataclasses import replace
_dlls=[os.add_dll_directory(str(p)) for p in (Path(sys.base_prefix),Path(sys.base_prefix)/'DLLs',Path(sys.base_prefix)/'Library/bin') if p.is_dir()]
from cephvr.visual_stimulus.rendering.image_bake import FoldBaker
from cephvr.visual_stimulus.rendering.evidence import clip_vertex_components
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
from cephvr.visual_stimulus.resources.image_crops import fold_crop
from cephvr.visual_stimulus.rendering.shaders import _LAYER_VERTEX, _LAYER_FRAGMENT
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
prog=ctx.program(vertex_shader=_LAYER_VERTEX,fragment_shader=_LAYER_FRAGMENT)
vbo=ctx.buffer(np.array([-1,-1,0,0,1,-1,1,0,-1,1,0,1,1,1,1,1],np.float32).tobytes())
vao=ctx.vertex_array(prog,[(vbo,'8x 2f','in_uv')])
legacy = ast.parse(subprocess.check_output(['git','show','HEAD:src/cephvr/visual_stimulus/rendering/shaders.py']).decode('utf-8'))
legacy_fragment = next(node.value.value for node in legacy.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_LAYER_FRAGMENT' for t in node.targets))
legacy_prog=ctx.program(vertex_shader=_LAYER_VERTEX,fragment_shader=legacy_fragment)
legacy_vao=ctx.vertex_array(legacy_prog,[(vbo,'8x 2f','in_uv')])
legacy_prog['image_tex'].value=0
flags=ctx.buffer(reserve=16); flags.bind_to_storage_buffer(3)
prog['mode'].value=8; prog['opacity'].value=1; prog['image_tex'].value=0
gpu=ImageGpu({p.output_id:NS(context=ctx,activate=lambda:glfw.make_context_current(w)) for p in profiles})
baker=FoldBaker(gpu.outputs)
rows=[]; started=time.perf_counter()
try:
    for i,item in enumerate(program['assets'][:int(os.environ.get('CROP_TEST_IMAGES','600'))],1):
        asset=Asset.model_validate(item); raw=(root/asset.logical_path).read_bytes()
        pixels=linear_rgba_bytes(decode_image(asset,raw))
        source=ImageSource(asset.asset_id,3840,2000,1500000000,491520000,lambda check:pixels)
        artifact=NS(display=d,geometric_calibration=profiles)
        crops=[]; offset=0
        for profile in profiles:
            crop=replace(fold_crop(artifact,profile.mapping_id,source),offset=offset)
            crops.append(crop); offset+=crop.width*crop.height*16
        planned=replace(source,output_crops=tuple(crops),gpu_bytes=offset)
        packed=baker.bake(planned,pixels,lambda:None)
        rects={c.output_id:(c.x,c.y,c.width,c.height) for c in crops}
        textures=[]
        while not gpu.upload(planned,packed,textures): pass
        full=ctx.texture((3840,2000),4,pixels,dtype='f4'); full.repeat_x=full.repeat_y=False
        differences=[]
        for j,p in enumerate(profiles):
            fold=calibrated_fold_map(d.geometry,profiles,p)
            crop=next(c for c in planned.output_crops if c.output_id==p.output_id)
            target=ctx.texture(crop.target,4,dtype='f4'); fbo=ctx.framebuffer([target]); fbo.use(); ctx.viewport=(0,0,*crop.target)
            prog['clip_vertices'].write(struct.pack('8f',*clip_vertex_components(crop.corners)))
            outputs=[]
            for tex,mode,active,array in ((full,8,legacy_prog,legacy_vao),(textures[j],12,prog,vao)):
                fbo.clear(); active['mode'].value=mode; active['opacity'].value=1
                active['clip_vertices'].write(struct.pack('8f',*clip_vertex_components(crop.corners)))
                if 'image_crop_origin' in active: active['image_crop_origin'].value=(crop.x,crop.y)
                active['image_fold_map'].write(struct.pack('6f',*fold)); tex.use(); array.render(moderngl.TRIANGLE_STRIP)
                outputs.append(fbo.read(components=4,dtype='f4'))
            assert outputs[0]==outputs[1], (asset.asset_id,p.surface_id,float(np.max(np.abs(np.frombuffer(outputs[0],np.float32)-np.frombuffer(outputs[1],np.float32)))))
            differences.append(0)
            fbo.release(); target.release()
        gpu.release(textures,[]); full.release()
        rows.append(dict(asset_id=asset.asset_id,sha256=hashlib.sha256(raw).hexdigest(),different_components=differences))
        if i%10==0 or i==1: print(f'{i}/600 exact four-output matches; {time.perf_counter()-started:.1f}s',flush=True)
    result=dict(gpu=ctx.info['GL_RENDERER'],seconds=time.perf_counter()-started,rectangles=rects,bytes_per_change=planned.gpu_bytes,images=rows,scope='actual Fold shader and RGBA32F framebuffer equality at actual surface framebuffer dimensions, including clip coverage; no downstream calibration/optical acceptance')
    (OUT/'legacy-reference-equivalence.json').write_text(json.dumps(result,indent=2))
finally:
    legacy_vao.release(); legacy_prog.release(); vao.release(); vbo.release(); flags.release(); prog.release(); ctx.release(); glfw.make_context_current(None); glfw.destroy_window(w); glfw.terminate()
