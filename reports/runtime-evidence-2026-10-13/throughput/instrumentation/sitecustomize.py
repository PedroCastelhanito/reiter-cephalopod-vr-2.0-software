"""Diagnostic-only stage timers injected into the managed renderer process."""
import atexit
import functools
import json
import os
from pathlib import Path
import statistics
import sys
import threading
import time

if 'cephvr.visual_stimulus.worker.main' in sys.argv:
    # Diagnostics run before python_entry registers the same prepared DLL paths.
    manifest = json.loads((Path(sys.executable).parent / 'cephvr-python.runtime.json').read_text())
    handles = [os.add_dll_directory(path) for path in manifest['dll_directories']]
    from cephvr.visual_stimulus.rendering.engine import RendererEngine
    from cephvr.visual_stimulus.rendering.native import ModernGLPort
    from cephvr.visual_stimulus.rendering.scene import ModernGLSceneRenderer
    from cephvr.visual_stimulus.rendering.capture import ReviewCapture
    from cephvr.visual_stimulus.rendering.capture import _VERTEX, _FRAGMENT, struct_quad
    from cephvr.visual_stimulus.recording.capture_runtime import RecordingCaptureRuntime
    from cephvr.visual_stimulus.worker.trials import TrialExecution
    import glfw
    from OpenGL import GL
    samples = {}
    active = None
    def timed(obj, method, label):
        original = getattr(obj, method)
        @functools.wraps(original)
        def call(*args, **kwargs):
            if active is None or threading.current_thread().name != 'cephvr-visual-stimulus-gl-owner':
                return original(*args, **kwargs)
            start = time.perf_counter_ns()
            try:
                return original(*args, **kwargs)
            finally:
                values = samples.setdefault(active, {}).setdefault(label, [])
                if len(values) < 200000:
                    values.append((time.perf_counter_ns()-start)/1e6)
        setattr(obj, method, call)
    for obj, method, label in (
        (RendererEngine,'render_tick','engine_tick'),
        (ModernGLSceneRenderer,'render_group','scene_draw'),
        (ModernGLPort,'present','present'),
        (ModernGLPort,'poll_diagnostics','diagnostics_poll'),
        (ReviewCapture,'capture','capture_submit'),
        (ReviewCapture,'poll','capture_poll'),
        (RecordingCaptureRuntime,'before_render','recording_before'),
        (RecordingCaptureRuntime,'rendered','recording_rendered'),
        (glfw,'make_context_current','context_switch'),
        (glfw,'poll_events','events'),
        (glfw,'swap_buffers','swap'),
        (GL,'glGetBufferSubData','pbo_copy'),
        (GL,'glReadPixels','pbo_read_submit'),
        (TrialExecution,'advance','trial_advance'),
    ):
        timed(obj, method, label)
    begin = RendererEngine.begin_trial
    stop = RendererEngine.stop_trial
    def start(self, trial_id, start_ns):
        global active
        active = trial_id
        return begin(self, trial_id, start_ns)
    def save():
        destination = Path(os.environ['CEPHVR_STAGE_OUTPUT'])
        data = {}
        for trial, stages in samples.items():
            data[trial] = {k:{'count':len(v),'total_ms':sum(v),'mean_ms':statistics.mean(v),'median_ms':statistics.median(v),'p95_ms':sorted(v)[int((len(v)-1)*.95)],'max_ms':max(v)} for k,v in stages.items() if v}
        destination.write_text(json.dumps({'method':'temporary stage wrappers; nested inclusive timings; bounded in-memory samples','argv':sys.argv,'trials':data},indent=2),encoding='utf-8')
    def end(self, *args, **kwargs):
        global active
        result = stop(self, *args, **kwargs)
        active = None
        save()
        return result
    RendererEngine.begin_trial = start
    RendererEngine.stop_trial = end
    atexit.register(save)
    if os.environ.get('CEPHVR_COMPARE_QUANTIZATION'):
        import struct
        import hashlib
        import moderngl
        ensure = ReviewCapture._ensure_compositor
        compared = False
        def compare(self, context, width, height, pixel_format):
            global compared
            ensure(self, context, width, height, pixel_format)
            if compared:
                return
            compared = True
            resources = []
            try:
                # Exercise all 256 code levels plus fractional sampled colors.
                colors = [(i/255, ((i*37)%256)/255, ((i*83)%256)/255, 1) for i in range(256)]
                colors += [(i/511, .3333, .7531, 1) for i in range(512)]
                data = b''.join(struct.pack('4f',*c) for c in colors)
                source = context.texture((len(colors),1),4,data,dtype='f4')
                resources.append(source)
                program = context.program(vertex_shader=_VERTEX,fragment_shader=_FRAGMENT)
                resources.append(program)
                quad = context.buffer(struct_quad())
                resources.append(quad)
                array = context.vertex_array(program,[(quad,'2f 2f','in_position','in_uv')])
                resources.append(array)
                outputs = []
                GL.glBindBuffer(GL.GL_PIXEL_PACK_BUFFER,0)
                for dtype in ('f4','f1'):
                    texture = context.texture((len(colors),1),4,dtype=dtype)
                    resources.append(texture)
                    framebuffer = context.framebuffer(color_attachments=(texture,))
                    resources.append(framebuffer)
                    framebuffer.use()
                    context.viewport=(0,0,len(colors),1)
                    context.disable(moderngl.BLEND)
                    program['source_tex'].value=0
                    source.use(0)
                    array.render(mode=moderngl.TRIANGLE_STRIP)
                    outputs.append(framebuffer.read(components=4,dtype='f1',alignment=1))
                Path(os.environ['CEPHVR_COMPARE_QUANTIZATION']).write_text(json.dumps({'method':'same native compositor shader; RGBA32F versus RGBA8 framebuffer followed by byte read; 256 code levels and512 fractional samples','equal':outputs[0]==outputs[1],'bytes':len(outputs[0]),'max_byte_difference':max(abs(a-b) for a,b in zip(*outputs)),'hashes':[hashlib.sha256(p).hexdigest() for p in outputs]},indent=2),encoding='utf-8')
            finally:
                for resource in reversed(resources):
                    resource.release()
        ReviewCapture._ensure_compositor=compare
