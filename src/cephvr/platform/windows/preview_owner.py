"""Exact GUI-window display ownership, independent of camera/process ownership."""

import ctypes
import os
from ctypes import wintypes

from cephvr.platform.windows.placement_events import PlacementEvents


def _apis() -> tuple[ctypes.CDLL, ctypes.CDLL]:
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    user.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user.FindWindowW.restype = wintypes.HWND
    user.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user.IsWindow.argtypes = user.IsIconic.argtypes = user.IsWindowVisible.argtypes = [
        wintypes.HWND
    ]
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetAncestor.restype = wintypes.HWND
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    user.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    user.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        *([ctypes.POINTER(wintypes.FILETIME)] * 4),
    ]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    return user, kernel


def _pid(user: ctypes.CDLL, hwnd: int) -> int:
    result = wintypes.DWORD()
    if not user.IsWindow(hwnd) or not user.GetWindowThreadProcessId(
        hwnd, ctypes.byref(result)
    ):
        raise RuntimeError("GUI preview owner window is unavailable")
    return result.value


def _creation(kernel: ctypes.CDLL, process: int) -> int:
    times = [wintypes.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(process, *(ctypes.byref(value) for value in times)):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(times[0].dwHighDateTime) << 32 | int(times[0].dwLowDateTime)


def gui_window_identity(hwnd: int) -> tuple[int, int, int]:
    user, kernel = _apis()
    pid = _pid(user, hwnd)
    if pid != os.getpid() or user.GetAncestor(hwnd, 2) != hwnd:
        raise RuntimeError("Preview owner is not this GUI process")
    process = kernel.OpenProcess(0x1000, False, pid)
    if not process:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return hwnd, pid, _creation(kernel, process)
    finally:
        if not kernel.CloseHandle(process):
            raise ctypes.WinError(ctypes.get_last_error())


class WindowsPreviewOwner:
    def __init__(self, title: str, hwnd: int, pid: int, creation: int) -> None:
        self.user, self.kernel = _apis()
        self.title, self.hwnd, self.pid = title, hwnd, pid
        self.process = 0
        self.child = 0
        self.bound = False
        self.origin: tuple[int, int] | None = None
        self.minimized = False
        self.suppressed = False
        self.placement_events: PlacementEvents | None = None
        try:
            if _pid(self.user, hwnd) != pid or self.user.GetAncestor(hwnd, 2) != hwnd:
                raise RuntimeError("Preview owner PID mismatch")
            self.process = self.kernel.OpenProcess(0x101000, False, pid)
            if not self.process or _creation(self.kernel, self.process) != creation:
                raise RuntimeError("Preview owner process identity mismatch")
            self.child = self.user.FindWindowW(None, title)
            if (
                not self.child
                or self.child == hwnd
                or _pid(self.user, self.child) != os.getpid()
            ):
                raise RuntimeError("Preview window is not owned by this process")
            self._set_owner(hwnd)
            self.bound = True
            # Owned windows stay above their owner without floating above other apps.
            if not self.user.SetWindowPos(self.child, -2, 0, 0, 0, 0, 0x0013):
                raise ctypes.WinError(ctypes.get_last_error())
            self.placement_events = PlacementEvents(self.child)
            self.sync()
        except BaseException:
            self.close()
            raise

    def _set_owner(self, owner: int) -> None:
        ctypes.set_last_error(0)
        previous = self.user.SetWindowLongPtrW(self.child, -8, owner)
        if not previous and ctypes.get_last_error():
            raise ctypes.WinError(ctypes.get_last_error())

    def _rect(self, hwnd: int) -> wintypes.RECT:
        rect = wintypes.RECT()
        if not self.user.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise ctypes.WinError(ctypes.get_last_error())
        return rect

    def sync(self, minimized: bool | None = None) -> bool:
        """Follow owner translation; report minimization without declaring X closure."""
        if self.kernel.WaitForSingleObject(self.process, 0) != 258:
            raise RuntimeError("Preview GUI owner process exited")
        if _pid(self.user, self.hwnd) != self.pid:
            raise RuntimeError("Preview GUI owner window identity changed")
        if minimized is None:
            root = self.user.GetAncestor(self.hwnd, 3)
            minimized = bool(
                self.user.IsIconic(self.hwnd)
                or self.user.IsIconic(root)
                or not self.user.IsWindowVisible(self.hwnd)
            )
        hidden = minimized or self.suppressed
        if self.user.IsWindow(self.child) and (
            hidden != self.minimized
            or (not hidden and not self.user.IsWindowVisible(self.child))
        ):
            self.user.ShowWindow(self.child, 0 if hidden else 4)
        self.minimized = hidden
        if not hidden:
            owner = self._rect(self.hwnd)
            origin = owner.left, owner.top
            if (
                self.origin is not None
                and origin != self.origin
                and self.user.IsWindow(self.child)
            ):
                child = self._rect(self.child)
                # Preserve any operator-adjusted offset when moving the GUI group.
                dx, dy = origin[0] - self.origin[0], origin[1] - self.origin[1]
                if not self.user.SetWindowPos(
                    self.child, 0, child.left + dx, child.top + dy, 0, 0, 0x0015
                ):
                    raise ctypes.WinError(ctypes.get_last_error())
            self.origin = origin
        return hidden

    def set_suppressed(self, suppressed: bool) -> bool:
        """Hide a live viewer without changing its native owner or placement."""
        self.suppressed = suppressed
        return self.sync()

    def retarget(self, handle: int) -> None:
        """Switch display hosts only inside the already verified live GUI process."""
        if self.kernel.WaitForSingleObject(self.process, 0) != 258:
            raise RuntimeError("Preview GUI owner process exited")
        if (
            _pid(self.user, handle) != self.pid
            or self.user.GetAncestor(handle, 2) != handle
        ):
            raise RuntimeError("Preview workspace owner PID mismatch")
        self._set_owner(handle)
        self.hwnd = handle
        self.origin = None

    def placement_revision(self) -> int:
        assert self.placement_events is not None
        return self.placement_events.revision

    def geometry(self) -> tuple[int, int, int, int]:
        """Outer frame relative to the GUI; group translation is not manual placement."""
        child, parent = self._rect(self.child), self._rect(self.hwnd)
        return (
            child.left - parent.left,
            child.top - parent.top,
            child.right - child.left,
            child.bottom - child.top,
        )

    def close(self) -> None:
        try:
            if self.placement_events is not None:
                self.placement_events.close(bool(self.user.IsWindow(self.child)))
                self.placement_events = None
            if (
                self.bound
                and self.child
                and self.user.IsWindow(self.child)
                and _pid(self.user, self.child) == os.getpid()
            ):
                try:
                    self._set_owner(0)
                except OSError:
                    # The GUI can destroy its owned HWND between the check and detach.
                    if self.user.IsWindow(self.child):
                        raise
                self.bound = False
        finally:
            if self.process:
                if not self.kernel.CloseHandle(self.process):
                    raise ctypes.WinError(ctypes.get_last_error())
                self.process = 0
