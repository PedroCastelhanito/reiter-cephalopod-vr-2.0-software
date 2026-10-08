"""Windows process creation with creation-time Job assignment (E08)."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path


class WindowsLaunchError(RuntimeError):
    pass


class ProcessGoneError(WindowsLaunchError):
    """The PID no longer names a process (ERROR_INVALID_PARAMETER on open)."""


CREATE_SUSPENDED = 0x00000004
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
STARTF_USESTDHANDLES = 0x00000100
PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002
PROC_THREAD_ATTRIBUTE_JOB_LIST = 0x0002000D
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
JOB_OBJECT_BASIC_PROCESS_ID_LIST = 3
JOB_OBJECT_ASSIGN_PROCESS = 0x0001
JOB_OBJECT_QUERY = 0x0004
JOB_OBJECT_TERMINATE = 0x0008
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
SYNCHRONIZE = 0x00100000
STILL_ACTIVE = 259
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 0x102
WAIT_FAILED = 0xFFFFFFFF
ERROR_INVALID_PARAMETER = 87
_INSPECTION_PASSES = 3


class _STARTUPINFO(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _STARTUPINFOEX(ctypes.Structure):
    _fields_ = [("StartupInfo", _STARTUPINFO), ("lpAttributeList", ctypes.c_void_p)]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_uint64)
        for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


@dataclass
class SuspendedProcess:
    pid: int
    creation_time_100ns: int
    executable: str
    process_handle: int
    thread_handle: int


class WindowsJobs:
    """Own exact process/job handles; no subprocess or post-create assignment path."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise WindowsLaunchError("native contained launch requires Windows")
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.jobs: dict[str, int] = {}
        self.processes: dict[tuple[int, int], SuspendedProcess] = {}
        self._bind()

    def _bind(self) -> None:
        api = self.api
        api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        api.CreateJobObjectW.restype = wintypes.HANDLE
        api.OpenJobObjectW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        api.OpenJobObjectW.restype = wintypes.HANDLE
        api.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        api.SetInformationJobObject.restype = wintypes.BOOL
        api.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        api.QueryInformationJobObject.restype = wintypes.BOOL
        api.InitializeProcThreadAttributeList.argtypes = [
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        api.InitializeProcThreadAttributeList.restype = wintypes.BOOL
        api.UpdateProcThreadAttribute.argtypes = [
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        api.UpdateProcThreadAttribute.restype = wintypes.BOOL
        api.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
        api.CreateProcessW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.LPWSTR,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.LPCWSTR,
            ctypes.POINTER(_STARTUPINFOEX),
            ctypes.POINTER(_PROCESS_INFORMATION),
        ]
        api.CreateProcessW.restype = wintypes.BOOL
        api.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_FILETIME),
            ctypes.POINTER(_FILETIME),
            ctypes.POINTER(_FILETIME),
            ctypes.POINTER(_FILETIME),
        ]
        api.GetProcessTimes.restype = wintypes.BOOL
        api.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        api.QueryFullProcessImageNameW.restype = wintypes.BOOL
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.GetExitCodeProcess.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        api.GetExitCodeProcess.restype = wintypes.BOOL
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.WaitForSingleObject.restype = wintypes.DWORD
        api.ResumeThread.argtypes = [wintypes.HANDLE]
        api.ResumeThread.restype = wintypes.DWORD
        api.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        api.TerminateProcess.restype = wintypes.BOOL
        api.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        api.TerminateJobObject.restype = wintypes.BOOL
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        api.CloseHandle.restype = wintypes.BOOL

    def _last_error(self) -> int:
        return ctypes.get_last_error()

    def _check(self, ok: object, label: str) -> None:
        if not ok:
            raise WindowsLaunchError(f"{label} failed: WinError {self._last_error()}")

    def create_launch_job(self, name: str) -> None:
        if name in self.jobs:
            raise WindowsLaunchError("launch job already exists")
        handle = self.api.CreateJobObjectW(None, name)
        self._check(handle, "CreateJobObjectW")
        if ctypes.get_last_error() == 183:
            self.api.CloseHandle(handle)
            raise WindowsLaunchError("launch job name already existed")
        self.jobs[name] = handle

    def open_launch_job(self, name: str) -> None:
        """The launching owner retains this existing planned job until child exit."""
        if name in self.jobs:
            return
        handle = self.api.OpenJobObjectW(
            JOB_OBJECT_ASSIGN_PROCESS | JOB_OBJECT_QUERY | JOB_OBJECT_TERMINATE,
            False,
            name,
        )
        self._check(handle, "OpenJobObjectW")
        self.jobs[name] = handle

    def create_application_job(self) -> str:
        name = f"application-{os.getpid()}"
        handle = self.api.CreateJobObjectW(None, None)
        self._check(handle, "CreateJobObjectW")
        limits = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        try:
            self._check(
                self.api.SetInformationJobObject(
                    handle,
                    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                    ctypes.byref(limits),
                    ctypes.sizeof(limits),
                ),
                "SetInformationJobObject",
            )
        except BaseException:
            self.api.CloseHandle(handle)
            raise
        self.jobs[name] = handle
        return name

    def launch_suspended(
        self,
        executable: str,
        arguments: list[str],
        job_names: list[str],
        inherited_handles: tuple[int, ...] = (),
        *,
        stdin_handle: int | None = None,
        stdout_handle: int | None = None,
        stderr_handle: int | None = None,
    ) -> SuspendedProcess:
        if not Path(executable).is_absolute() or not Path(executable).is_file():
            raise WindowsLaunchError("explicit installed executable path is required")
        if not job_names or any(name not in self.jobs for name in job_names):
            raise WindowsLaunchError("creation-time containment job is required")
        standard_handles = (stdin_handle, stdout_handle, stderr_handle)
        if any(handle is not None for handle in standard_handles):
            if any(handle is None for handle in standard_handles):
                raise WindowsLaunchError("all three standard handles must be supplied")
            declared = set(inherited_handles)
            if not set(standard_handles).issubset(declared):
                raise WindowsLaunchError(
                    "standard handles must be in the exact inherit list"
                )
        count = 1 + bool(inherited_handles)
        size = ctypes.c_size_t()
        self.api.InitializeProcThreadAttributeList(None, count, 0, ctypes.byref(size))
        if not size.value:
            raise WindowsLaunchError("creation-time job-list attributes unsupported")
        buffer = ctypes.create_string_buffer(size.value)
        attr = ctypes.cast(buffer, ctypes.c_void_p)
        self._check(
            self.api.InitializeProcThreadAttributeList(
                attr, count, 0, ctypes.byref(size)
            ),
            "InitializeProcThreadAttributeList",
        )
        job_array = (wintypes.HANDLE * len(job_names))(
            *(self.jobs[name] for name in job_names)
        )
        handle_array = (wintypes.HANDLE * len(inherited_handles))(*inherited_handles)
        try:
            self._check(
                self.api.UpdateProcThreadAttribute(
                    attr,
                    0,
                    PROC_THREAD_ATTRIBUTE_JOB_LIST,
                    ctypes.cast(job_array, ctypes.c_void_p),
                    ctypes.sizeof(job_array),
                    None,
                    None,
                ),
                "UpdateProcThreadAttribute(JOB_LIST)",
            )
            if inherited_handles:
                self._check(
                    self.api.UpdateProcThreadAttribute(
                        attr,
                        0,
                        PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                        ctypes.cast(handle_array, ctypes.c_void_p),
                        ctypes.sizeof(handle_array),
                        None,
                        None,
                    ),
                    "UpdateProcThreadAttribute(HANDLE_LIST)",
                )
            startup = _STARTUPINFOEX()
            startup.StartupInfo.cb = ctypes.sizeof(startup)
            startup.lpAttributeList = attr
            if all(handle is not None for handle in standard_handles):
                startup.StartupInfo.dwFlags |= STARTF_USESTDHANDLES
                startup.StartupInfo.hStdInput = stdin_handle
                startup.StartupInfo.hStdOutput = stdout_handle
                startup.StartupInfo.hStdError = stderr_handle
            info = _PROCESS_INFORMATION()
            command = ctypes.create_unicode_buffer(
                subprocess.list2cmdline([executable, *arguments])
            )
            self._check(
                self.api.CreateProcessW(
                    executable,
                    command,
                    None,
                    None,
                    bool(inherited_handles),
                    CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT,
                    None,
                    None,
                    ctypes.byref(startup),
                    ctypes.byref(info),
                ),
                "CreateProcessW",
            )
            try:
                created = self._creation_time(info.hProcess)
                result = SuspendedProcess(
                    info.dwProcessId,
                    created,
                    str(Path(executable).resolve()),
                    info.hProcess,
                    info.hThread,
                )
                self.processes[(result.pid, created)] = result
                return result
            except BaseException:
                self.api.TerminateProcess(info.hProcess, 1)
                self.api.CloseHandle(info.hThread)
                self.api.CloseHandle(info.hProcess)
                raise
        finally:
            self.api.DeleteProcThreadAttributeList(attr)

    def _creation_time(self, handle: int) -> int:
        creation, exit_time, kernel, user = (_FILETIME() for _ in range(4))
        self._check(
            self.api.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ),
            "GetProcessTimes",
        )
        return int((creation.dwHighDateTime << 32) | creation.dwLowDateTime)

    def _open_exact(self, pid: int, creation_time_100ns: int) -> tuple[int, bool]:
        retained = self.processes.get((pid, creation_time_100ns))
        if retained:
            return retained.process_handle, False
        handle = self.api.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE | PROCESS_TERMINATE,
            False,
            pid,
        )
        if not handle:
            if self._last_error() == ERROR_INVALID_PARAMETER:
                raise ProcessGoneError(f"PID {pid} has exited")
            raise WindowsLaunchError(f"cannot open PID {pid} for verification")
        try:
            actual_creation = self._creation_time(handle)
        except BaseException:
            self.api.CloseHandle(handle)
            raise
        if actual_creation != creation_time_100ns:
            self.api.CloseHandle(handle)
            raise WindowsLaunchError("PID creation time differs")
        return handle, True

    def inspect_launch_job(self, name: str) -> list[tuple[int, int, str]]:
        """Members whose exact identity two consecutive enumerations agree on.

        A member can exit between PID enumeration and OpenProcess; that is absence,
        not an inspection failure. Retry transient query errors within the same
        pass bound; an error on the final pass remains unconfirmed and raises.
        """
        if name not in self.jobs:
            raise WindowsLaunchError("unknown retained job")
        previous: list[tuple[int, int, str]] | None = None
        for attempt in range(_INSPECTION_PASSES):
            try:
                current = self._enumerate_job(name)
            except WindowsLaunchError:
                if attempt == _INSPECTION_PASSES - 1:
                    raise
                previous = None
                continue
            if current == previous:
                return current
            previous = current
        assert previous is not None
        return previous

    def _enumerate_job(self, name: str) -> list[tuple[int, int, str]]:
        capacity = 8
        while True:
            size = 8 + ctypes.sizeof(ctypes.c_size_t) * capacity
            buf = ctypes.create_string_buffer(size)
            if self.api.QueryInformationJobObject(
                self.jobs[name], JOB_OBJECT_BASIC_PROCESS_ID_LIST, buf, size, None
            ):
                break
            if self._last_error() != 234 or capacity >= 4096:
                raise WindowsLaunchError(
                    f"job enumeration failed: {self._last_error()}"
                )
            capacity *= 2
        count = int.from_bytes(buf.raw[4:8], "little")
        offset = 8
        result = []
        for _ in range(count):
            pid = int.from_bytes(
                buf.raw[offset : offset + ctypes.sizeof(ctypes.c_size_t)], "little"
            )
            offset += ctypes.sizeof(ctypes.c_size_t)
            handle = self.api.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid
            )
            if not handle:
                if self._last_error() == ERROR_INVALID_PARAMETER:
                    continue  # exited since enumeration
                self._check(handle, "OpenProcess")
            try:
                member = self._member(handle, pid)
            finally:
                self.api.CloseHandle(handle)
            if member is not None:
                result.append(member)
        return result

    def _member(self, handle: int, pid: int) -> tuple[int, int, str] | None:
        """Identity of an open process, or None when it has exited meanwhile."""
        try:
            created = self._creation_time(handle)
            path_buf = ctypes.create_unicode_buffer(32768)
            path_size = wintypes.DWORD(len(path_buf))
            self._check(
                self.api.QueryFullProcessImageNameW(
                    handle, 0, path_buf, ctypes.byref(path_size)
                ),
                f"QueryFullProcessImageNameW for PID {pid}",
            )
        except WindowsLaunchError:
            # Image teardown may precede the exact process handle's exit signal.
            if self._exited(handle, timeout_ms=1):
                return None
            raise
        return pid, created, str(Path(path_buf.value).resolve())

    def _exited(self, handle: int, *, timeout_ms: int = 0) -> bool:
        return bool(self.api.WaitForSingleObject(handle, timeout_ms) == WAIT_OBJECT_0)

    def process_running(self, pid: int, creation_time_100ns: int) -> bool:
        try:
            handle, temporary = self._open_exact(pid, creation_time_100ns)
        except ProcessGoneError:
            return False
        try:
            observation = self.api.WaitForSingleObject(handle, 0)
            if observation == WAIT_TIMEOUT:
                return True
            if observation == WAIT_OBJECT_0:
                return False
            raise WindowsLaunchError(
                f"WaitForSingleObject failed: {ctypes.get_last_error()}"
            )
        finally:
            if temporary:
                self.api.CloseHandle(handle)

    def wait_process_exit(
        self, pid: int, creation_time_100ns: int, timeout_ms: int
    ) -> bool:
        """Wait once on the exact process object; never poll or trust PID reuse."""
        if timeout_ms < 0 or timeout_ms > 0xFFFFFFFE:
            raise WindowsLaunchError("process wait timeout exceeds Win32 bounds")
        handle, temporary = self._open_exact(pid, creation_time_100ns)
        try:
            observation = self.api.WaitForSingleObject(handle, timeout_ms)
            if observation == WAIT_OBJECT_0:
                return True
            if observation == WAIT_TIMEOUT:
                return False
            raise WindowsLaunchError(
                f"WaitForSingleObject failed: {ctypes.get_last_error()}"
            )
        finally:
            if temporary:
                self.api.CloseHandle(handle)

    def retain_exact(
        self, pid: int, creation_time_100ns: int, executable: str
    ) -> SuspendedProcess:
        handle, temporary = self._open_exact(pid, creation_time_100ns)
        if not temporary:
            return self.processes[(pid, creation_time_100ns)]
        path_buf = ctypes.create_unicode_buffer(32768)
        path_size = wintypes.DWORD(len(path_buf))
        try:
            self._check(
                self.api.QueryFullProcessImageNameW(
                    handle, 0, path_buf, ctypes.byref(path_size)
                ),
                "QueryFullProcessImageNameW",
            )
            if os.path.normcase(os.path.abspath(path_buf.value)) != os.path.normcase(
                os.path.abspath(executable)
            ):
                raise WindowsLaunchError(
                    "registered executable differs from process image"
                )
            result = SuspendedProcess(pid, creation_time_100ns, executable, handle, 0)
            self.processes[(pid, creation_time_100ns)] = result
            return result
        except BaseException:
            self.api.CloseHandle(handle)
            raise

    def resume(self, child: SuspendedProcess) -> None:
        if self.api.ResumeThread(child.thread_handle) == 0xFFFFFFFF:
            raise WindowsLaunchError(f"ResumeThread failed: {ctypes.get_last_error()}")
        self.api.CloseHandle(child.thread_handle)
        child.thread_handle = 0

    def terminate_exact(self, pid: int, creation_time_100ns: int) -> None:
        """Terminate the exact process; one that already exited counts as absent."""
        try:
            handle, temporary = self._open_exact(pid, creation_time_100ns)
        except ProcessGoneError:
            return
        try:
            if not self.api.TerminateProcess(handle, 1) and not self._exited(handle):
                self._check(False, "TerminateProcess")
        finally:
            if temporary:
                self.api.CloseHandle(handle)

    def terminate_job(self, name: str) -> None:
        self._check(
            self.api.TerminateJobObject(self.jobs[name], 1), "TerminateJobObject"
        )

    def close_launch_job(self, name: str) -> None:
        handle = self.jobs.get(name)
        if handle is None:
            return
        self._check(self.api.CloseHandle(handle), "CloseHandle(launch job)")
        self.jobs.pop(name, None)

    def release_process(self, pid: int, creation_time_100ns: int) -> None:
        key = (pid, creation_time_100ns)
        process = self.processes.get(key)
        if process is not None:
            if process.thread_handle:
                self._check(
                    self.api.CloseHandle(process.thread_handle),
                    "CloseHandle(process thread)",
                )
                process.thread_handle = 0
            self._check(
                self.api.CloseHandle(process.process_handle), "CloseHandle(process)"
            )
            self.processes.pop(key, None)
