"""Keep HighGUI's eagerly shown frame hidden until its owner has arranged it."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


class _WindowPos(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("after", wintypes.HWND),
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("cx", ctypes.c_int),
        ("cy", ctypes.c_int),
        ("flags", wintypes.UINT),
    ]


class _CreateStruct(ctypes.Structure):
    _fields_ = [
        ("parameter", ctypes.c_void_p),
        ("instance", wintypes.HINSTANCE),
        ("menu", wintypes.HMENU),
        ("parent", wintypes.HWND),
        ("cy", ctypes.c_int),
        ("cx", ctypes.c_int),
        ("y", ctypes.c_int),
        ("x", ctypes.c_int),
        ("style", wintypes.LONG),
        ("name", wintypes.LPCWSTR),
        ("class_name", ctypes.c_void_p),
        ("extended_style", wintypes.DWORD),
    ]


class _CbtCreate(ctypes.Structure):
    _fields_ = [("creation", ctypes.POINTER(_CreateStruct)), ("after", wintypes.HWND)]


class StagedPreviewWindow:
    """Intercept only this thread's exact preview frame; never affect other windows."""

    def __init__(self, title: str) -> None:
        self.title = title
        self.hwnd = 0
        self.hook = 0
        self.subclassed = False
        self.failure = ""

    def __enter__(self) -> StagedPreviewWindow:
        if sys.platform != "win32":
            return self
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.controls = ctypes.WinDLL("comctl32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        hook_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t
        )
        subclass_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            wintypes.HWND,
            wintypes.UINT,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
            ctypes.c_size_t,
            ctypes.c_size_t,
        )
        self.hook_callback = hook_type(self._created)
        self.subclass_callback = subclass_type(self._message)
        self.user.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            hook_type,
            wintypes.HINSTANCE,
            wintypes.DWORD,
        ]
        self.user.SetWindowsHookExW.restype = wintypes.HANDLE
        self.user.CallNextHookEx.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        ]
        self.user.CallNextHookEx.restype = ctypes.c_ssize_t
        self.user.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
        self.user.GetClassNameW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        self.user.GetWindowTextW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        self.user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self.controls.SetWindowSubclass.argtypes = [
            wintypes.HWND,
            subclass_type,
            ctypes.c_size_t,
            ctypes.c_size_t,
        ]
        self.controls.RemoveWindowSubclass.argtypes = [
            wintypes.HWND,
            subclass_type,
            ctypes.c_size_t,
        ]
        self.controls.DefSubclassProc.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        ]
        self.controls.DefSubclassProc.restype = ctypes.c_ssize_t
        self.hook = self.user.SetWindowsHookExW(
            5, self.hook_callback, None, kernel.GetCurrentThreadId()
        )
        if not self.hook:
            raise ctypes.WinError(ctypes.get_last_error())
        return self

    def _created(self, code: int, hwnd: int, parameter: int) -> int:
        if code == 3:  # HCBT_CREATEWND, before HighGUI's first ShowWindow.
            name = ctypes.create_unicode_buffer(64)
            self.user.GetClassNameW(hwnd, name, len(name))
            creation = ctypes.cast(
                parameter, ctypes.POINTER(_CbtCreate)
            ).contents.creation.contents
            if name.value == "Main HighGUI class" and creation.name == self.title:
                self.hwnd = hwnd
                self.subclassed = bool(
                    self.controls.SetWindowSubclass(
                        hwnd, self.subclass_callback, id(self), 0
                    )
                )
                if not self.subclassed:
                    self.failure = "Cannot stage the preview window before showing it"
                    return 1
        return int(self.user.CallNextHookEx(self.hook, code, hwnd, parameter))

    def _message(
        self, hwnd: int, message: int, wparam: int, lparam: int, *_: int
    ) -> int:
        if message == 0x0046:  # WM_WINDOWPOSCHANGING
            position = ctypes.cast(lparam, ctypes.POINTER(_WindowPos)).contents
            position.flags &= ~0x0040  # Suppress SWP_SHOWWINDOW until explicitly ready.
        return int(self.controls.DefSubclassProc(hwnd, message, wparam, lparam))

    def show(self, visible: bool = True) -> None:
        if sys.platform != "win32":
            return
        if self.failure or not self.hwnd:
            raise RuntimeError(
                self.failure or "HighGUI preview creation was not intercepted"
            )
        self._detach()
        if visible:
            self.user.ShowWindow(self.hwnd, 4)  # SW_SHOWNOACTIVATE

    def _detach(self) -> None:
        if self.subclassed:
            if not self.controls.RemoveWindowSubclass(
                self.hwnd, self.subclass_callback, id(self)
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            self.subclassed = False

    def __exit__(self, *_: object) -> None:
        if sys.platform == "win32":
            try:
                self._detach()
            finally:
                if self.hook and not self.user.UnhookWindowsHookEx(self.hook):
                    raise ctypes.WinError(ctypes.get_last_error())
                self.hook = 0
