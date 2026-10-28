"""Compare full and rebased crop sampling on the actual renderer GPU."""
import os, sys, json, struct
from pathlib import Path
_dlls=[os.add_dll_directory(str(p)) for p in (Path(sys.base_prefix),Path(sys.base_prefix)/'DLLs',Path(sys.base_prefix)/'Library/bin') if p.is_dir()]
import numpy as np
import imagecodecs, glfw, moderngl
from cephvr.visual_stimulus.config.models.artifact_models import GeometricProfile
from cephvr.visual_stimulus.config.models.display_profile import parse_display_json
from cephvr.visual_stimulus.rendering.image_fold import calibrated_fold_map
from cephvr.visual_stimulus.rendering.image_fit import valid_image_pixels
from cephvr.visual_stimulus.rendering.shaders import _QUAD_VERTEX, _LAYER_FRAGMENT
OUT=Path(__file__).parent
s=json.loads((OUT/'observed-terminal.json').read_text())['configuration_values']['current']
root=Path(s['asset_root'])
b=next(x for x in s['backends'] if x['backend_name']=='visual_stimulus')
d=parse_display_json(b['visual_stimulus']['display']['profile_json'],max_bytes=16777216)
profiles=[GeometricProfile.model_validate_json((root/m.geometric_profile.logical_path).read_text()) for m in d.active_mappings]
p=json.loads(s['trials'][0]['stimulus']['program']['program_json'])
rgb=imagecodecs.png_decode((root/p['assets'][0]['logical_path']).read_bytes())
rgba=np.ones((*rgb.shape[:2],4),np.float32); rgba[...,:3]=rgb; rgba[...,:3]/=255
assert glfw.init(); glfw.window_hint(glfw.VISIBLE,glfw.FALSE)
w=glfw.create_window(32,32,'Crop equivalence',None,None); glfw.make_context_current(w)
ctx=moderngl.create_context(require=430)
assert '5060' in ctx.info['GL_RENDERER']
prog=ctx.program(vertex_shader=_QUAD_VERTEX,fragment_shader=_LAYER_FRAGMENT.replace("uniform vec2 image_target_pixels;", "uniform vec2 image_target_pixels; uniform vec2 crop_offset;").replace("image_uv = vec2(pixel.x / size.x, 1.0 - pixel.y / size.y);", "precise vec2 original_uv = vec2(pixel.x / 3840.0, 1.0 - pixel.y / 2000.0); precise vec2 original_pixel = original_uv * vec2(3840.0,2000.0); image_uv = (original_pixel - crop_offset) / size;").replace("any(greaterThanEqual(pixel, size))", "any(greaterThanEqual(pixel, vec2(3840.0,2000.0)))"))
vbo=ctx.buffer(np.array([-1,-1,0,0,1,-1,1,0,-1,1,0,1,1,1,1,1],np.float32).tobytes())
vao=ctx.vertex_array(prog,[(vbo,'2f 2f','in_position','in_uv')])
flags=ctx.buffer(reserve=16); flags.bind_to_storage_buffer(3)
prog['mode'].value=8; prog['opacity'].value=1; prog['image_tex'].value=0
full=ctx.texture((3840,2000),4,rgba[::-1].tobytes(),dtype='f4'); full.repeat_x=full.repeat_y=False
rows=[]
for profile in profiles:
    fold=calibrated_fold_map(d.geometry,profiles,profile)
    x,y,ux,uy,vx,vy=fold
    corners=np.array([[x,y],[x+ux,y+uy],[x+vx,y+vy],[x+ux+vx,y+uy+vy]])
    lo=np.maximum(0,np.floor(corners.min(axis=0)).astype(int)-1); hi=np.minimum([3840,2000],np.ceil(corners.max(axis=0)).astype(int)+1)
    x0,y0=lo; x1,y1=hi
    crop=ctx.texture((int(x1-x0),int(y1-y0)),4,rgba[y0:y1,x0:x1][::-1].tobytes(),dtype='f4'); crop.repeat_x=crop.repeat_y=False
    target=ctx.texture(valid_image_pixels(profile),4,dtype='f4'); fbo=ctx.framebuffer([target]); fbo.use()
    outputs=[]
    for tex,mapping in ((full,fold),(crop,(x-x0,y-y0,ux,uy,vx,vy))):
        prog['image_fold_map'].write(struct.pack('6f',*fold)); prog['crop_offset'].value=(0,0) if tex is full else (int(x0),int(2000-y1)); tex.use(); vao.render(moderngl.TRIANGLE_STRIP)
        outputs.append(np.frombuffer(fbo.read(components=4,dtype='f4'),np.float32).copy())
    delta=np.abs(outputs[0]-outputs[1]); rows.append(dict(face=profile.surface_id,max_error=float(delta.max()),different_components=int(np.count_nonzero(delta)),components=len(delta)))
    fbo.release(); target.release(); crop.release()
print(json.dumps(rows,indent=2),flush=True)
(OUT/'crop-equivalence-probe.json').write_text(json.dumps(rows,indent=2))
full.release(); vao.release(); vbo.release(); flags.release(); prog.release(); ctx.release(); glfw.make_context_current(None); glfw.destroy_window(w); glfw.terminate()

