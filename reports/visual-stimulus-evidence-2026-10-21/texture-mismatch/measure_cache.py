"""Paced production image-cache probe with real protected PNGs and four hidden GL contexts.
No projector swaps, cameras, scientific run, or output recording are started.
"""
import argparse
import gc
import threading
import bisect
import hashlib
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace as NS

_dll_handles = [os.add_dll_directory(str(Path(r'C:\Users\ReiterU_PC\miniforge3\envs\CephVR') / suffix)) for suffix in ('', 'DLLs', 'Library/bin')]
import glfw
import moderngl
from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.rendering import image_gpu
from cephvr.visual_stimulus.rendering.image_residency import ImageResidency
from cephvr.visual_stimulus.rendering.types import InstanceSnapshot
from cephvr.visual_stimulus.resources.budget import BoundedBudget
from cephvr.visual_stimulus.resources.image_schedule import ImageSchedule
from cephvr.visual_stimulus.resources.prepare import prepare_resources
from cephvr.visual_stimulus.resources.prepared_heap import PreparedHeap

parser=argparse.ArgumentParser()
parser.add_argument('label')
parser.add_argument('--seconds',type=float,default=60)
parser.add_argument('--chunks',type=int,default=4)
parser.add_argument('--prepared-heap',action='store_true')
args=parser.parse_args()
image_gpu.UPLOAD_CHUNKS_PER_TURN=args.chunks
folder=Path(__file__).parent
root=Path(r'C:\Data\projects\reiter-cephalopod-vr\cephvr-data\20261020_ephys-pilot\SP0003-145623\protocol-data')
asset_root=Path(r'C:\Users\ReiterU_PC\Desktop\Pedro\media')
# Same 1 GiB budget, conservatively reserving retained scene/review allocations.
budget=BoundedBudget(cpu_limit=1<<30,gpu_limit=1<<30)
budget.reserve(owner='probe-fixed-scenes-and-review',cpu_bytes=0,gpu_bytes=551_476_536)
artifacts=[]
bundles={}
windows=[]
cache=None
heap=PreparedHeap()
results=[]
stage_events=[]
gc_events=[]
gc_started={}
def gc_timing(phase,info):
    generation=info['generation']
    if phase=='start':gc_started[generation]=time.perf_counter()
    else:
        ms=(time.perf_counter()-gc_started.pop(generation))*1000
        if ms>5:gc_events.append(dict(generation=generation,ms=ms,epoch=probe_epoch,seconds=probe_elapsed,thread=threading.get_ident()))
gc.callbacks.append(gc_timing)

probe_epoch=-1
probe_elapsed=-1
def timed_method(owner,name):
    original=getattr(owner,name)
    def call(*args,**kwargs):
        started=time.perf_counter()
        try:return original(*args,**kwargs)
        finally:
            ms=(time.perf_counter()-started)*1000
            if ms>5:stage_events.append(dict(method=name,ms=ms,epoch=probe_epoch,seconds=probe_elapsed))
    setattr(owner,name,call)

try:
    for path in sorted(root.glob('*stimulus_LOG.json')):
        artifact=PreparedTrial.model_validate_json(path.read_text())
        epochs=tuple(e for e in artifact.epochs if e.start_ns < args.seconds*1e9)
        artifact=artifact.model_copy(update={'epochs':epochs})
        used={s.asset_id for e in epochs for s in e.settings}
        program=artifact.source
        print('source_type',type(program).__name__,flush=True)
        assets=tuple(a for a in program.assets if a.asset_id in used)
        bundle=prepare_resources(NS(assets=assets,sequence=(),instances=()),asset_root,budget,
            announce=lambda *_:None,snapshot_limit_bytes=1<<30,video_index_limit_bytes=1000,
            glb_element_limit=1000,max_document_bytes=16<<20,defer_images=True,
            owner_prefix=f'probe-{artifact.identity.trial_id}')
        artifacts.append(artifact)
        bundles[artifact.identity.trial_id]=bundle
        print('prepared',len(assets),'images',flush=True)
    schedule=ImageSchedule.build(tuple(artifacts),bundles,budget)
    assert glfw.init()
    glfw.window_hint(glfw.VISIBLE,glfw.FALSE)
    outputs={}
    for output in artifacts[0].display.active_outputs:
        window=glfw.create_window(16,16,'CephVR image-cache probe',None,None)
        assert window
        windows.append(window)
        glfw.make_context_current(window)
        ctx=moderngl.create_context(require=430)
        assert '5060' in ctx.info['GL_RENDERER'],ctx.info['GL_RENDERER']
        outputs[output.output_id]=NS(context=ctx,activate=lambda w=window:glfw.make_context_current(w))
    cache=ImageResidency(schedule,budget,announce=lambda *_:None)
    gpu=image_gpu.ImageGpu(outputs)
    for method in ('upload','fence','ready','release'):timed_method(gpu,method)
    timed_method(cache,'_replan')
    cache.attach(gpu,{},lambda *_:None)
    cache.prepare(time.perf_counter_ns()+120_000_000_000)
    if args.prepared_heap:heap.prepare(lambda:None)
    print('cache ready',budget.usage,flush=True)
    for artifact in artifacts:
        trial=artifact.identity.trial_id
        cache.begin(trial)
        snapshots=[tuple(InstanceSnapshot(s.instance_id,s.kind,True,(),s) for s in e.settings) for e in artifact.epochs]
        starts=[e.start_ns/1e9 for e in artifact.epochs]
        t0=time.perf_counter();frame=0;counts=dict(texture_groups=0,held_groups=0,mixed_groups=0)
        times=[];first=None;onset_holds=[];seen=set();peak=0;slow_selects=[]
        stage_events.clear();gc_events.clear()
        while True:
            elapsed=time.perf_counter()-t0
            if elapsed>=args.seconds:break
            epoch=bisect.bisect_right(starts,elapsed)-1
            probe_epoch=epoch;probe_elapsed=elapsed
            started=time.perf_counter();thread_started=time.thread_time()
            selected=cache.select(trial,epoch,snapshots[epoch])
            times.append((time.perf_counter()-started)*1000)
            if times[-1]>8:slow_selects.append(dict(epoch=epoch,seconds=elapsed,ms=times[-1],thread_cpu_ms=(time.thread_time()-thread_started)*1000))
            peak=max(peak,budget.usage.gpu_bytes)
            imgs=[s.image_selection for s in selected if s.image_selection]
            if imgs:
                counts['texture_groups']+=1
                held=any(x.disposition!='current' for x in imgs)
                mixed=len({x.asset_id.rsplit('_',1)[0] for x in imgs})>1
                counts['held_groups']+=held;counts['mixed_groups']+=mixed
                if epoch not in seen:
                    seen.add(epoch)
                    if held:onset_holds.append(epoch)
                if held and first is None:first=dict(seconds=elapsed,epoch=epoch,images=[dict(instance=x.instance_id,requested=x.requested_asset_id,actual=x.asset_id) for x in imgs])
            frame+=1
            target=t0+frame/60
            if target<time.perf_counter():frame=int((time.perf_counter()-t0)*60)+1;target=t0+frame/60
            time.sleep(max(0,target-time.perf_counter()))
        cache.finish(trial)
        times.sort()
        result=dict(trial=trial,seconds=args.seconds,counts=counts,presentations=len(seen),onset_hold_epochs=onset_holds,first_hold=first,service_ms=dict(p50=times[len(times)//2],p99=times[int(len(times)*.99)],maximum=max(times)),peak_reserved_gpu_bytes=peak,slow_selects=slow_selects,slow_stages=list(stage_events),gc_events=list(gc_events),main_thread=threading.get_ident())
        results.append(result)
        print(json.dumps({k:v for k,v in result.items() if k not in ('slow_selects','slow_stages','gc_events')}),flush=True)
    (folder/(args.label+'.json')).write_text(json.dumps(dict(prepared_heap=args.prepared_heap,chunks_per_turn=args.chunks,renderer=ctx.info['GL_RENDERER'],method=__doc__,trials=results,upload_source_sha256=hashlib.sha256(Path('src/cephvr/visual_stimulus/rendering/image_gpu.py').read_bytes()).hexdigest()),indent=2)+'\n')
finally:
    heap.release()
    if cache is not None:
        assert cache.close(time.perf_counter_ns()+10_000_000_000)
        deadline=time.monotonic()+10
        while cache.release_gpu():
            assert time.monotonic()<deadline
            time.sleep(.001)
    for b in bundles.values():assert b.asset_set.close()==()
    for window in reversed(windows):glfw.destroy_window(window)
    glfw.terminate()
