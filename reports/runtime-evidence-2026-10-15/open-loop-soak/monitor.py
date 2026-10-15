"""Read-only1s native process/system counters and continuous GPU samples."""

import argparse
import ctypes as c
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time

K = c.WinDLL("kernel32", use_last_error=True)
P = c.WinDLL("psapi", use_last_error=True)
K.CreateToolhelp32Snapshot.restype = w.HANDLE
K.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
K.OpenProcess.restype = w.HANDLE
K.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
K.CloseHandle.argtypes = [w.HANDLE]
K.GetProcessTimes.argtypes = [w.HANDLE, c.c_void_p, c.c_void_p, c.c_void_p, c.c_void_p]
K.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD)]
K.GetProcessIoCounters.argtypes = [w.HANDLE, c.c_void_p]
P.GetProcessMemoryInfo.argtypes = [w.HANDLE, c.c_void_p, w.DWORD]
K.GetSystemTimes.argtypes = [c.c_void_p, c.c_void_p, c.c_void_p]


class Entry(c.Structure):
    _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("pid", w.DWORD), ("heap", c.c_size_t), ("module", w.DWORD), ("threads", w.DWORD), ("parent", w.DWORD), ("priority", w.LONG), ("flags", w.DWORD), ("name", w.WCHAR * 260)]


class Memory(c.Structure):
    _fields_ = [("size", w.DWORD), ("faults", w.DWORD), *[(name, c.c_size_t) for name in ("peak_working_set", "working_set", "peak_paged_pool", "paged_pool", "peak_nonpaged_pool", "nonpaged_pool", "pagefile", "peak_pagefile")]]


K.Process32FirstW.argtypes = [w.HANDLE, c.POINTER(Entry)]
K.Process32NextW.argtypes = [w.HANDLE, c.POINTER(Entry)]


def processes():
    result = []
    snapshot = K.CreateToolhelp32Snapshot(2, 0)
    if snapshot == c.c_void_p(-1).value:
        raise c.WinError(c.get_last_error())
    entry = Entry(size=c.sizeof(Entry))
    try:
        more = K.Process32FirstW(snapshot, c.byref(entry))
        while more:
            if any(word in entry.name.lower() for word in ("python", "cephvr", "ffmpeg", "nvidia-smi")):
                row = dict(pid=entry.pid, parent_pid=entry.parent, name=entry.name)
                handle = K.OpenProcess(0x0410, False, entry.pid)
                if not handle:
                    row["error"] = c.get_last_error()
                else:
                    try:
                        created, exited, kernel, user = (c.c_uint64() for _ in range(4))
                        if K.GetProcessTimes(handle, c.byref(created), c.byref(exited), c.byref(kernel), c.byref(user)):
                            row.update(creation_time_100ns=created.value, kernel_time_100ns=kernel.value, user_time_100ns=user.value)
                        else:
                            row["times_unavailable"] = c.get_last_error()
                        text = c.create_unicode_buffer(32768)
                        length = w.DWORD(len(text))
                        if K.QueryFullProcessImageNameW(handle, 0, text, c.byref(length)):
                            row["image"] = text.value
                        else:
                            row["image_unavailable"] = c.get_last_error()
                        memory = Memory(size=c.sizeof(Memory))
                        if P.GetProcessMemoryInfo(handle, c.byref(memory), c.sizeof(memory)):
                            row.update(rss_bytes=memory.working_set, peak_rss_bytes=memory.peak_working_set)
                        else:
                            row["memory_unavailable"] = c.get_last_error()
                        io = (c.c_uint64 * 6)()
                        if K.GetProcessIoCounters(handle, c.byref(io)):
                            row.update(read_bytes=io[3], write_bytes=io[4], other_bytes=io[5])
                        else:
                            row["io_unavailable"] = c.get_last_error()
                    finally:
                        K.CloseHandle(handle)
                result.append(row)
            more = K.Process32NextW(snapshot, c.byref(entry))
    finally:
        K.CloseHandle(snapshot)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stop", type=Path, required=True)
    args = parser.parse_args()
    gpu = []
    gpu_lock = threading.Lock()
    command = ["nvidia-smi", "--query-gpu=timestamp,index,uuid,name,utilization.gpu,utilization.encoder,memory.used,power.draw", "--format=csv,noheader,nounits", "-l", "1"]
    child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    def read_gpu():
        for line in child.stdout:
            with gpu_lock:
                gpu.append(dict(observed_monotonic_ns=time.perf_counter_ns(), text=line.strip()))
    reader = threading.Thread(target=read_gpu, daemon=True)
    reader.start()
    with args.output.open("x", encoding="utf-8", buffering=1) as stream:
        try:
            deadline = time.perf_counter()
            while not args.stop.exists():
                begin = time.perf_counter_ns()
                idle, kernel, user = (c.c_uint64() for _ in range(3))
                system_valid = bool(K.GetSystemTimes(c.byref(idle), c.byref(kernel), c.byref(user)))
                with gpu_lock:
                    samples = gpu[:]
                    gpu.clear()
                row = dict(utc=time.time(), host_monotonic_ns=begin, cpu_count=os.cpu_count(), source="native cumulative100ns times; kernel includes idle; process CPU/RSS/IO identity-fenced; disk totals unavailable, process IO retained", processes=processes(), system=dict(valid=system_valid, idle_100ns=idle.value, kernel_100ns=kernel.value, user_100ns=user.value), storage=shutil.disk_usage(args.output)._asdict(), gpu_samples=samples, gpu_command=command)
                row["sample_duration_ns"] = time.perf_counter_ns() - begin
                stream.write(json.dumps(row, separators=(",", ":")) + "\n")
                deadline += 1
                time.sleep(max(0, deadline - time.perf_counter()))
        finally:
            # Popen retains the exact created process handle; no PID/name lookup.
            child.terminate()
            child.wait(timeout=10)


if __name__ == "__main__":
    main()
