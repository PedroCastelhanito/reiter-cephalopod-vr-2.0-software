"""Bounded per-monitor OpenGL identity probe; no cameras or recording."""
import os
from pathlib import Path
_dll_handles = [os.add_dll_directory(str(Path('C:/Users/ReiterU_PC/miniforge3/envs/CephVR') / suffix)) for suffix in ('', 'DLLs', 'Library/bin')]
import ctypes
import json
import sys
import glfw
import moderngl

print('executable', sys.executable, flush=True)
assert glfw.init()
windows = []
try:
    monitors = sorted([m for m in glfw.get_monitors() if glfw.get_win32_adapter(m).split('\\')[-1] in ('DISPLAY1','DISPLAY2','DISPLAY3','DISPLAY4')], key=lambda m: {'DISPLAY2':0,'DISPLAY1':1,'DISPLAY4':2,'DISPLAY3':3}[glfw.get_win32_adapter(m).split('\\')[-1]])
    if '--place-bootstrap' in sys.argv:
        from ctypes import wintypes
        user = ctypes.WinDLL('user32',use_last_error=True)
        kernel = ctypes.WinDLL('kernel32',use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
        user.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
        user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
        helpers=[]
        def collect(hwnd, ignored):
            name=ctypes.create_unicode_buffer(256)
            user.GetClassNameW(hwnd,name,len(name))
            if name.value == 'GLFW3 Helper': helpers.append(hwnd)
            return True
        user.EnumThreadWindows(kernel.GetCurrentThreadId(),callback_type(collect),0)
        assert len(helpers)==1,helpers
        x,y=glfw.get_monitor_pos(monitors[0])
        assert user.SetWindowPos(helpers[0],None,x,y,0,0,0x0015)
        print('bootstrap placed',x,y,flush=True)
    if '--amd-first' in sys.argv:
        glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
        warm = glfw.create_window(32,32,'GPU warmup',None,None)
        glfw.make_context_current(warm)
        moderngl.init_context()
        ctx=moderngl.get_context()
        print('warmup', ctx.info['GL_RENDERER'],flush=True)
        ctx.release()
        glfw.destroy_window(warm)
    for monitor in monitors:
        glfw.default_window_hints()
        glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
        glfw.window_hint(glfw.AUTO_ICONIFY, glfw.FALSE)
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 4)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        mode = glfw.get_video_mode(monitor)
        window = glfw.create_window(mode.size.width, mode.size.height, 'CephVR GPU identity probe', monitor, windows[0] if windows else None)
        assert window
        windows.append(window)
        glfw.make_context_current(window)
        get_string = ctypes.WINFUNCTYPE(ctypes.c_char_p, ctypes.c_uint)(glfw.get_proc_address('glGetString'))
        raw = {'vendor': get_string(0x1F00).decode(), 'renderer': get_string(0x1F01).decode()}
        moderngl.init_context()
        context = moderngl.get_context()
        print(json.dumps({'adapter': glfw.get_win32_adapter(monitor), 'raw': raw, 'modern': {k:context.info[k] for k in ('GL_VENDOR','GL_RENDERER')}}), flush=True)
        context.release()
finally:
    for window in reversed(windows):
        glfw.destroy_window(window)
    glfw.terminate()
