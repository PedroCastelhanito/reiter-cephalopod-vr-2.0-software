import ctypes
u=ctypes.windll.user32
cb=ctypes.WINFUNCTYPE(ctypes.c_bool,ctypes.c_void_p,ctypes.c_void_p)
u.GetWindowTextW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_int]
u.GetWindowThreadProcessId.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
u.IsWindowVisible.argtypes=[ctypes.c_void_p]
u.PostMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]
@cb
def f(h,p):
    t=ctypes.create_unicode_buffer(512)
    u.GetWindowTextW(h,t,512)
    if t.value.startswith('CephVR native proof'):
        pid=ctypes.c_ulong()
        u.GetWindowThreadProcessId(h,ctypes.byref(pid))
        print(pid.value,t.value,u.IsWindowVisible(h),flush=True)
        u.PostMessageW(h,0x0010,0,0)
    return True
u.EnumWindows(f,0)
