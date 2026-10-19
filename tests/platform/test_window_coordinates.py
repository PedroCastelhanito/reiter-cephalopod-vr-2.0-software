"""Portable exact-owner and display lifecycle checks with isolated Win32 calls."""

import os
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cephvr.platform.windows import preview_owner


@pytest.fixture
def native(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = SimpleNamespace(
        pid=os.getpid() + 1000,
        child_pid=os.getpid(),
        creation=99,
        minimized=False,
        visible=True,
        shows=[],
        exited=False,
        owner_valid=True,
        close_ok=True,
        owner_rect=[100, 200, 900, 800],
        child_rect=[400, 500, 220, 248],
        owners=[],
        moves=[],
        closed=[],
    )

    def process_id(hwnd: int, result: object) -> int:
        result._obj.value = state.pid if hwnd in (101, 103) else state.child_pid
        return 1

    def rect(hwnd: int, output: object) -> bool:
        x, y, width, height = (
            state.owner_rect if hwnd in (101, 103) else state.child_rect
        )
        value = output._obj
        value.left, value.top, value.right, value.bottom = x, y, x + width, y + height
        return True

    def creation(_handle: int, *times: object) -> bool:
        times[0]._obj.dwLowDateTime = state.creation
        return True

    def set_owner(child: int, _index: int, owner: int) -> int:
        state.owners.append((child, owner))
        return 0

    def move(
        child: int, after: int, x: int, y: int, _w: int, _h: int, flags: int
    ) -> bool:
        state.moves.append((child, after, x, y, flags))
        if not flags & 2:
            state.child_rect[:2] = [x, y]
        return True

    def close(handle: int) -> bool:
        state.closed.append(handle)
        return state.close_ok

    user = SimpleNamespace(
        FindWindowW=lambda *_: 102,
        IsWindow=lambda hwnd: hwnd == 102 or (hwnd in (101, 103) and state.owner_valid),
        IsIconic=lambda _: state.minimized,
        IsWindowVisible=lambda _: state.visible,
        ShowWindow=lambda hwnd, mode: state.shows.append((hwnd, mode)),
        GetAncestor=lambda hwnd, _: hwnd,
        GetWindowThreadProcessId=process_id,
        GetWindowRect=rect,
        SetWindowLongPtrW=set_owner,
        SetWindowPos=move,
    )
    kernel = SimpleNamespace(
        OpenProcess=lambda *_: 555,
        GetProcessTimes=creation,
        WaitForSingleObject=lambda *_: 0 if state.exited else 258,
        CloseHandle=close,
    )
    monkeypatch.setattr(preview_owner, "_apis", lambda: (user, kernel))
    monkeypatch.setattr(
        preview_owner.ctypes, "set_last_error", lambda _: None, raising=False
    )
    monkeypatch.setattr(
        preview_owner.ctypes, "get_last_error", lambda: 0, raising=False
    )
    monkeypatch.setattr(
        preview_owner.ctypes,
        "WinError",
        lambda *_: OSError("native error"),
        raising=False,
    )
    return state


def test_preview_owner_follows_translation_and_minimize_without_activation(
    native: SimpleNamespace,
) -> None:
    owner = preview_owner.WindowsPreviewOwner("preview", 101, native.pid, 99)
    try:
        assert native.owners == [(102, 101)]
        assert native.moves[0][1] == -2
        native.owner_rect[:2] = [130, 240]
        assert not owner.sync()
        assert native.child_rect[:2] == [430, 540]
        native.minimized = True
        native.owner_rect[:2] = [-32000, -32000]
        assert owner.sync()
        assert native.child_rect[:2] == [430, 540]
        native.minimized = False
        native.owner_rect[:2] = [160, 260]
        assert not owner.sync()
        assert native.child_rect[:2] == [460, 560]
        assert all(move[-1] & 0x10 for move in native.moves)
    finally:
        owner.close()
    assert native.owners[-1] == (102, 0)
    assert native.closed == [555]


@pytest.mark.parametrize("mismatch", ["pid", "creation", "preview"])
def test_preview_owner_rejects_foreign_and_recycled_identity(
    native: SimpleNamespace, mismatch: str
) -> None:
    expected_pid, expected_creation = native.pid, 99
    if mismatch == "pid":
        expected_pid += 1
    elif mismatch == "creation":
        expected_creation += 1
    else:
        native.child_pid += 1
    with pytest.raises(RuntimeError, match="mismatch|not owned"):
        preview_owner.WindowsPreviewOwner(
            "preview", 101, expected_pid, expected_creation
        )
    assert not native.owners
    assert native.closed == ([] if mismatch == "pid" else [555])


@pytest.mark.parametrize("lost", ["exited", "window", "pid"])
def test_preview_owner_does_not_retarget_lost_gui(
    native: SimpleNamespace, lost: str
) -> None:
    owner = preview_owner.WindowsPreviewOwner("preview", 101, native.pid, 99)
    if lost == "exited":
        native.exited = True
    elif lost == "window":
        native.owner_valid = False
    else:
        native.pid += 1
    with pytest.raises(RuntimeError):
        owner.sync()
    owner.close()
    assert native.closed == [555]


def test_preview_owner_reports_unconfirmed_handle_cleanup(
    native: SimpleNamespace,
) -> None:
    owner = preview_owner.WindowsPreviewOwner("preview", 101, native.pid, 99)
    native.close_ok = False
    with pytest.raises(OSError):
        owner.close()
    assert owner.process == 555
    native.close_ok = True
    owner.close()
    assert owner.process == 0


@pytest.mark.windows
def test_preview_owner_native_minimize_restore_and_move() -> None:
    if sys.platform != "win32":
        pytest.skip("native preview ownership requires Windows")
    import ctypes
    from ctypes import wintypes

    user, kernel = preview_owner._apis()
    user.CreateWindowExW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        ctypes.c_void_p,
    ]
    user.CreateWindowExW.restype = wintypes.HWND
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user.DestroyWindow.argtypes = [wintypes.HWND]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetWindow.restype = wintypes.HWND
    kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel.GetModuleHandleW.restype = wintypes.HMODULE
    instance = kernel.GetModuleHandleW(None)
    title = f"CephVR isolated preview owner {uuid4()}"
    gui = child = 0
    link = None
    try:
        gui = user.CreateWindowExW(
            0,
            "STATIC",
            title + " GUI",
            0x00CF0000,
            50,
            50,
            500,
            500,
            0,
            0,
            instance,
            None,
        )
        child = user.CreateWindowExW(
            0, "STATIC", title, 0x00CF0000, 100, 100, 200, 240, 0, 0, instance, None
        )
        assert gui and child
        user.ShowWindow(gui, 5)
        user.ShowWindow(child, 5)
        link = preview_owner.WindowsPreviewOwner(
            title, *preview_owner.gui_window_identity(gui)
        )
        assert user.GetWindow(child, 4) == gui
        assert not link.sync()
        before = link._rect(child)
        gui_before = link._rect(gui)
        assert user.SetWindowPos(
            gui, 0, gui_before.left + 50, gui_before.top + 20, 0, 0, 0x0015
        )
        assert not link.sync()
        after = link._rect(child)
        assert (after.left - before.left, after.top - before.top) == (50, 20)
        user.ShowWindow(gui, 6)
        assert link.sync()
        assert not user.IsWindowVisible(child)
        user.ShowWindow(gui, 9)
        assert not link.sync()
        assert user.IsWindowVisible(child)
    finally:
        if link is not None:
            link.close()
        if child:
            user.DestroyWindow(child)
        if gui:
            user.DestroyWindow(gui)


@pytest.mark.parametrize(
    "change", [(12, 0, 0, 0), (0, 12, 0, 0), (0, 0, 30, 0), (0, 0, 0, 30)]
)
def test_preview_geometry_guard_preserves_operator_move_or_resize(change):
    from cephvr.shared.preview_geometry import PreviewGeometryGuard

    guard = PreviewGeometryGuard()
    original = (100, 200, 300, 330)
    guard.arranged(original)
    assert guard.observe(original)
    changed = tuple(a + b for a, b in zip(original, change, strict=True))
    assert not guard.observe(changed)
    # Returning it to the old coordinates does not silently re-enable auto layout.
    assert not guard.observe(original)
    reopened = PreviewGeometryGuard()
    reopened.arranged(original)
    assert reopened.observe(original)


def test_preview_owner_retargets_same_process_workspace_and_hides(
    native: SimpleNamespace,
) -> None:
    owner = preview_owner.WindowsPreviewOwner("preview", 101, native.pid, 99)
    try:
        owner.retarget(103)
        assert owner.hwnd == 103 and native.owners[-1] == (102, 103)
        native.visible = False
        assert owner.sync() and native.shows[-1] == (102, 0)
        native.visible = True
        assert not owner.sync() and native.shows[-1] == (102, 4)
        with pytest.raises(RuntimeError):
            owner.retarget(102)
        assert owner.hwnd == 103
    finally:
        owner.close()


def test_blank_preview_caption_keeps_handle_placement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ctypes

    from cephvr.platform.windows import window_coordinates as coordinates

    titles = {"preview": 77}
    calls: list[tuple[object, ...]] = []

    def process_id(_hwnd: int, result: object) -> int:
        result._obj.value = os.getpid()
        return 1

    def rect(_hwnd: int, output: object) -> bool:
        value = output._obj
        value.left, value.top, value.right, value.bottom = 90, 80, 400, 380
        return True

    user = SimpleNamespace(
        FindWindowW=lambda _class, title: titles.get(title, 0),
        GetWindowThreadProcessId=process_id,
        GetWindowRect=rect,
        SetWindowTextW=lambda hwnd, text: calls.append(("text", hwnd, text)) or True,
        SetWindowPos=lambda hwnd, after, x, y, *_: (
            calls.append(("pos", hwnd, x, y)) or True
        ),
    )
    monkeypatch.setattr(
        coordinates.ctypes, "WinDLL", lambda *_, **__: user, raising=False
    )
    monkeypatch.setattr(
        coordinates, "_visible_frame", lambda _hwnd: SimpleNamespace(left=100, top=80)
    )
    monkeypatch.setattr(
        ctypes, "WinError", lambda *_: OSError("native error"), raising=False
    )
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 0, raising=False)

    handle = coordinates.preview_window_handle("preview")
    coordinates.blank_preview_caption(handle)
    del titles["preview"]  # The blanked window can no longer be found by title.
    coordinates.position_preview_frame(handle, 410, 110, topmost=False)

    assert handle == 77
    assert calls == [("text", 77, ""), ("pos", 77, 400, 110)]
    with pytest.raises(OSError):
        coordinates.preview_window_handle("preview")
