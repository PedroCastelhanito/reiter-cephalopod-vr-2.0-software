"""Isolated candidate benchmark. No production edits or projector windows."""
import json, time, hashlib
from pathlib import Path
import os, sys
_dlls=[os.add_dll_directory(str(p)) for p in (Path(sys.base_prefix),Path(sys.base_prefix)/'DLLs',Path(sys.base_prefix)/'Library/bin') if p.is_dir()]
import numpy as np
import imagecodecs
import glfw
import moderngl
from cephvr.visual_stimulus.config.models.artifact_models import GeometricProfile
from cephvr.visual_stimulus.config.models.display_profile import parse_display_json
from cephvr.visual_stimulus.rendering.image_fold import calibrated_fold_map

OUT=Path(__file__).parent/'options'
OUT.mkdir(exist_ok=True)
snap=json.loads((OUT.parent/'observed-terminal.json').read_text())
conf=snap['configuration_values']['current']
root=Path(conf['asset_root'])
backend=next(x for x in conf['backends'] if x['backend_name']=='visual_stimulus')
display=parse_display_json(backend['visual_stimulus']['display']['profile_json'],max_bytes=16777216)
profiles=[GeometricProfile.model_validate_json((root/m.geometric_profile.logical_path).read_text()) for m in display.active_mappings]
program=json.loads(conf['trials'][0]['stimulus']['program']['program_json'])
assets=program['assets']
rects=[]
for p in profiles:
    x,y,ux,uy,vx,vy=calibrated_fold_map(display.geometry,profiles,p)
    corners=np.array([[x,y],[x+ux,y+uy],[x+vx,y+vy],[x+ux+vx,y+uy+vy]])
    lo=np.maximum(0,np.floor(corners.min(axis=0)).astype(int)-1)
    hi=np.minimum([3840,2000],np.ceil(corners.max(axis=0)).astype(int)+1)
    rects.append((int(lo[0]),int(lo[1]),int(hi[0]),int(hi[1])))
print('source footprint with one-texel halo',rects,flush=True)
def stats(a):
    return dict(median_ms=float(np.median(a)*1000),p95_ms=float(np.percentile(a,95)*1000),max_ms=float(max(a)*1000),n=len(a))
def variants(rgb):
    gray=np.ascontiguousarray(rgb[...,0])
    rgba=np.ones((*rgb.shape[:2],4),np.float32); rgba[...,:3]=rgb; rgba[...,:3]/=255
    crops=[gray[y0:y1,x0:x1].copy() for x0,y0,x1,y1 in rects]
    fcrops=[rgba[y0:y1,x0:x1].copy() for x0,y0,x1,y1 in rects]
    return {'full_rgba32f':[rgba]*4,'crop_rgba32f':fcrops,'crop_r32f':[a.astype(np.float32)/255 for a in crops],'full_r8':[gray]*4,'crop_r8':crops}
cpu={k:[] for k in ['png_read_decode','pack_crop_r8','prepared_crop_read']}
provenance=[]
for i in np.linspace(0,len(assets)-1,24,dtype=int):
    path=root/assets[i]['logical_path']
    t=time.perf_counter(); raw=path.read_bytes(); rgb=imagecodecs.png_decode(raw); cpu['png_read_decode'].append(time.perf_counter()-t)
    assert rgb.dtype==np.uint8 and np.array_equal(rgb[...,0],rgb[...,1]) and np.array_equal(rgb[...,0],rgb[...,2])
    provenance.append(dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest()))
    t=time.perf_counter(); crops=[np.ascontiguousarray(rgb[y0:y1,x0:x1,0]).tobytes() for x0,y0,x1,y1 in rects]; cpu['pack_crop_r8'].append(time.perf_counter()-t)
    cache=OUT/'candidate.raw'; cache.write_bytes(b''.join(crops))
    t=time.perf_counter(); cached=cache.read_bytes(); cpu['prepared_crop_read'].append(time.perf_counter()-t)
    assert cached==b''.join(crops)
data=variants(rgb)
assert glfw.init()
glfw.window_hint(glfw.VISIBLE,glfw.FALSE)
windows=[]; contexts=[]
try:
    for _ in range(4):
        window=glfw.create_window(32,32,'CephVR isolated upload benchmark',None,None)
        assert window
        windows.append(window); glfw.make_context_current(window)
        contexts.append(moderngl.create_context(require=330))
    gpu=contexts[0].info['GL_RENDERER']
    print('GPU',gpu,flush=True)
    assert '5060' in gpu, 'Do not label a benchmark on another adapter as rig renderer evidence'
    results={}
    for name,arrays in data.items():
        for pbo in ([False,True] if name=='crop_r8' else [False]):
            textures=[]; buffers=[]; payloads=[a.tobytes() for a in arrays]
            for j,a in enumerate(arrays):
                glfw.make_context_current(windows[j]); ctx=contexts[j]
                textures.append(ctx.texture((a.shape[1],a.shape[0]),1 if a.ndim==2 else 4,dtype='f1' if a.dtype==np.uint8 else 'f4'))
                buffers.append(ctx.buffer(reserve=a.nbytes) if pbo else None)
            samples=[]
            for repeat in range(35):
                t=time.perf_counter()
                for j,tex in enumerate(textures):
                    glfw.make_context_current(windows[j])
                    if pbo:
                        buffers[j].write(payloads[j]); tex.write(buffers[j],alignment=1)
                    else: tex.write(payloads[j],alignment=1)
                for j,ctx in enumerate(contexts):
                    glfw.make_context_current(windows[j]); ctx.finish()
                elapsed=time.perf_counter()-t
                if repeat>=5: samples.append(elapsed)
            for j,tex in enumerate(textures):
                glfw.make_context_current(windows[j]); assert tex.read(alignment=1)==payloads[j]
                tex.release()
                if buffers[j]: buffers[j].release()
            results[name+('_pbo' if pbo else '')]=dict(bytes_per_change=sum(a.nbytes for a in arrays),**stats(samples))
            print(name,pbo,results[name+('_pbo' if pbo else '')],flush=True)
    result=dict(gpu=gpu,rectangles=rects,cpu={k:stats(v) for k,v in cpu.items()},upload=results,sources=provenance,
        limits='Warm-cache isolated four-context completed uploads with preallocated textures; no vsync, drawing, concurrent cameras, or optical timing. PBO measured without overlap. Only24 source images checked grayscale.')
    (OUT/'results.json').write_text(json.dumps(result,indent=2))
finally:
    for j,ctx in enumerate(contexts):
        glfw.make_context_current(windows[j]); ctx.release()
    for w in windows: glfw.destroy_window(w)
    glfw.terminate()
