"""Keep local HighGUI windows above, and minimized with, their Qt owner."""

import ctypes
import ctypes.util
import platform
from typing import Any, cast


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class _Size(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


class _Rect(ctypes.Structure):
    _fields_ = [("origin", _Point), ("size", _Size)]


class CocoaPreviewOwner:
    def __init__(self, title: str, owner_view: int) -> None:
        library = ctypes.util.find_library("objc")
        if library is None:
            raise RuntimeError("Objective-C runtime is unavailable")
        self.api = ctypes.CDLL(library)
        self.api.objc_getClass.argtypes = [ctypes.c_char_p]
        self.api.objc_getClass.restype = ctypes.c_void_p
        self.api.sel_registerName.argtypes = [ctypes.c_char_p]
        self.api.sel_registerName.restype = ctypes.c_void_p
        self.parent = self._send(ctypes.c_void_p, owner_view, "window")
        application = self._send(
            ctypes.c_void_p,
            self.api.objc_getClass(b"NSApplication"),
            "sharedApplication",
        )
        windows = self._send(ctypes.c_void_p, application, "windows")
        self.child = 0
        for index in range(self._send(ctypes.c_ulong, windows, "count")):
            native = self._send(
                ctypes.c_void_p,
                windows,
                "objectAtIndex:",
                index,
                types=(ctypes.c_ulong,),
            )
            name = self._send(ctypes.c_void_p, native, "title")
            if self._send(ctypes.c_char_p, name, "UTF8String").decode() == title:
                self.child = native
                break
        if not self.parent or not self.child or self.parent == self.child:
            raise RuntimeError("Local preview/GUI window identity is unavailable")
        self._send(ctypes.c_void_p, self.parent, "retain")
        self._send(ctypes.c_void_p, self.child, "retain")
        self.minimized = False
        try:
            self._send(
                None,
                self.parent,
                "addChildWindow:ordered:",
                self.child,
                1,
                types=(ctypes.c_void_p, ctypes.c_long),
            )
            self.sync()
        except BaseException:
            self.close()
            raise

    def _send(
        self,
        result: Any,
        receiver: int,
        selector: str,
        *args: Any,
        types: tuple[Any, ...] = (),
    ) -> Any:
        sel = self.api.sel_registerName(selector.encode())
        call = ctypes.CFUNCTYPE(result, ctypes.c_void_p, ctypes.c_void_p, *types)(
            ("objc_msgSend", self.api)
        )
        return call(receiver, sel, *args)

    def sync(self, minimized: bool | None = None) -> bool:
        if minimized is None:
            minimized = bool(self._send(ctypes.c_bool, self.parent, "isMiniaturized"))
        if minimized != self.minimized:
            self._send(
                None,
                self.child,
                "orderOut:" if minimized else "orderFront:",
                None,
                types=(ctypes.c_void_p,),
            )
            self.minimized = minimized
        return minimized

    def retarget(self, handle: int) -> None:
        parent = self._send(ctypes.c_void_p, handle, "window")
        if not parent or parent == self.child:
            raise RuntimeError("Preview workspace window is unavailable")
        if parent == self.parent:
            return
        self._send(None, parent, "retain")
        self._send(
            None,
            self.parent,
            "removeChildWindow:",
            self.child,
            types=(ctypes.c_void_p,),
        )
        self._send(None, self.parent, "release")
        self.parent = parent
        self._send(
            None,
            parent,
            "addChildWindow:ordered:",
            self.child,
            1,
            types=(ctypes.c_void_p, ctypes.c_long),
        )

    def _frame(self, window: int) -> _Rect:
        if platform.machine() == "x86_64":
            result = _Rect()
            call = ctypes.CFUNCTYPE(
                None, ctypes.POINTER(_Rect), ctypes.c_void_p, ctypes.c_void_p
            )(("objc_msgSend_stret", self.api))
            call(ctypes.byref(result), window, self.api.sel_registerName(b"frame"))
            return result
        return cast(_Rect, self._send(_Rect, window, "frame"))

    def placement_revision(self) -> int | None:
        return None

    def geometry(self) -> tuple[int, int, int, int]:
        child, parent = self._frame(self.child), self._frame(self.parent)
        return (
            round(child.origin.x - parent.origin.x),
            round(
                parent.origin.y
                + parent.size.height
                - child.origin.y
                - child.size.height
            ),
            round(child.size.width),
            round(child.size.height),
        )

    def close(self) -> None:
        if self.child:
            self._send(
                None,
                self.parent,
                "removeChildWindow:",
                self.child,
                types=(ctypes.c_void_p,),
            )
            self._send(None, self.child, "release")
            self._send(None, self.parent, "release")
            self.child = 0
