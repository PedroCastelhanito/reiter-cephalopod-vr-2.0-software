"""Read-only file identity and process token flags; never reads credentials."""

import ctypes
import json
import os
import sys
from ctypes import wintypes as w
from pathlib import Path

kernel = ctypes.WinDLL("kernel32", use_last_error=True)
advapi = ctypes.WinDLL("advapi32", use_last_error=True)
kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
kernel.OpenProcess.restype = w.HANDLE
kernel.CloseHandle.argtypes = [w.HANDLE]
kernel.GetCurrentProcess.restype = w.HANDLE
advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
advapi.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(w.LPWSTR)]
kernel.LocalFree.argtypes = [ctypes.c_void_p]
kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
kernel.CreateFileW.restype = w.HANDLE
kernel.GetFinalPathNameByHandleW.argtypes = [w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD]


def token_info(pid):
    process = kernel.OpenProcess(0x1000, False, pid)
    if not process:
        return {"pid": pid, "process_error": ctypes.get_last_error()}
    token = w.HANDLE()
    try:
        if not advapi.OpenProcessToken(process, 8, ctypes.byref(token)):
            return {"pid": pid, "token_error": ctypes.get_last_error()}
        result = {"pid": pid}
        for name, kind in (("elevated", 20), ("virtualization_enabled", 24), ("appcontainer", 29)):
            value, size = w.DWORD(), w.DWORD()
            ok = advapi.GetTokenInformation(token, kind, ctypes.byref(value), 4, ctypes.byref(size))
            result[name] = value.value if ok else {"error": ctypes.get_last_error()}
        for name, kind in (("user_sid", 1), ("integrity_sid", 25)):
            size = w.DWORD()
            advapi.GetTokenInformation(token, kind, None, 0, ctypes.byref(size))
            buffer = ctypes.create_string_buffer(size.value)
            if not advapi.GetTokenInformation(token, kind, buffer, size, ctypes.byref(size)):
                result[name] = {"error": ctypes.get_last_error()}
                continue
            sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
            text = w.LPWSTR()
            if advapi.ConvertSidToStringSidW(sid, ctypes.byref(text)):
                result[name] = text.value
                kernel.LocalFree(text)
        return result
    finally:
        if token:
            kernel.CloseHandle(token)
        kernel.CloseHandle(process)


class FileInfo(ctypes.Structure):
    _fields_ = [("attributes", w.DWORD), ("created", w.FILETIME),
                ("accessed", w.FILETIME), ("written", w.FILETIME),
                ("volume", w.DWORD), ("size_high", w.DWORD), ("size_low", w.DWORD),
                ("links", w.DWORD), ("index_high", w.DWORD), ("index_low", w.DWORD)]


kernel.GetFileInformationByHandle.argtypes = [w.HANDLE, ctypes.POINTER(FileInfo)]


def file_info(path):
    result = {"requested": str(path), "exists": path.exists()}
    handle = kernel.CreateFileW(str(path), 0, 7, None, 3, 0x02000000, None)
    if handle == ctypes.c_void_p(-1).value:
        result["open_error"] = ctypes.get_last_error()
        return result
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        count = kernel.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
        result["final_path"] = buffer.value if count else {"error": ctypes.get_last_error()}
        info = FileInfo()
        if kernel.GetFileInformationByHandle(handle, ctypes.byref(info)):
            result.update(volume_serial=f"{info.volume:08X}", file_id=(info.index_high << 32) | info.index_low)
        return result
    finally:
        kernel.CloseHandle(handle)


root = Path(r"C:\Users\ReiterU_PC\AppData\Local\CephVR2\runtime")
print(json.dumps({"exe": sys.executable, "computer": os.environ.get("COMPUTERNAME"),
                  "localappdata": os.environ.get("LOCALAPPDATA"),
                  "tokens": [token_info(pid) for pid in [os.getpid(), *map(int, sys.argv[1:])]],
                  "files": [file_info(root), file_info(root / "launcher.json")]}, indent=2))
