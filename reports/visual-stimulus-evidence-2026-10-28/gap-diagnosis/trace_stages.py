"""Temporary diagnostic wrappers; buffered timing only, dumped outside playback."""
import atexit
import functools
import gc
import json
import os
import threading
import time
from collections import deque
from pathlib import Path


def install():
    import glfw
    import moderngl
    from cephvr.visual_stimulus.rendering.engine import RendererEngine
    from cephvr.visual_stimulus.rendering.native import ModernGLPort, _OutputContext
    from cephvr.visual_stimulus.rendering.scene import ModernGLSceneRenderer
    from cephvr.visual_stimulus.rendering.sparse_noise_ring import SparseNoiseRing
    from cephvr.visual_stimulus.worker.sparse_noise import NativeSparseNoise, SparseNoiseProcess
    from cephvr.visual_stimulus.worker.lifecycle import LifecycleDriver
    from cephvr.visual_stimulus.recording.native import NativeRecording
    rows=deque(maxlen=100000)
    root=Path(__file__).parent
    sequence=0
    def dump():
        nonlocal sequence
        sequence+=1
        (root/f'trace-{os.getpid()}-{sequence}.json').write_text(json.dumps(list(rows)))
        rows.clear()
    def wrap(owner,name,threshold=500_000):
        original=getattr(owner,name)
        @functools.wraps(original)
        def measured(*a,**k):
            start=time.perf_counter_ns(); cpu=time.thread_time_ns()
            try: return original(*a,**k)
            finally:
                end=time.perf_counter_ns()
                if end-start>=threshold:
                    rows.append((getattr(owner,'__name__',str(owner))+'.'+name,start,end,time.thread_time_ns()-cpu,threading.get_ident()))
        setattr(owner,name,measured)
    for owner,names in [
        (RendererEngine,('render_tick','_scene_state')),
        (ModernGLPort,('render','present','service_display','select_sparse_noise','capture_review_composite','poll_review_capture')),
        (ModernGLSceneRenderer,('render_group','_draw_scene_layers','_apply_output','_bind_warp_profile')),
        (SparseNoiseRing,('prefill','service','select','_upload','_grant')),
        (SparseNoiseProcess,('send',)),
        (NativeSparseNoise,('prepare','finish')),
        (LifecycleDriver,('advance',)),
        (NativeRecording,('before_render','rendered')),
        (moderngl.Context,('finish','copy_framebuffer','texture')),
        (moderngl.Texture,('write',)),(moderngl.VertexArray,('render',)),
        (glfw,('swap_buffers','poll_events','make_context_current')),
    ]:
        for name in names:
            if hasattr(owner,name): wrap(owner,name)
    gcstart={}
    def collection(phase,info):
        key=threading.get_ident()
        if phase=='start': gcstart[key]=time.perf_counter_ns()
        else: rows.append(('gc'+str(info['generation']),gcstart.pop(key,0),time.perf_counter_ns(),0,key))
    gc.callbacks.append(collection)
    original=NativeSparseNoise.finish
    @functools.wraps(original)
    def finish(*a,**k):
        try: return original(*a,**k)
        finally: dump()
    NativeSparseNoise.finish=finish
    atexit.register(dump)
