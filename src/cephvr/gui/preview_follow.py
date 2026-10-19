"""Native display-only owner links for blank Review windows."""

import sys
from typing import Protocol


class PreviewOwner(Protocol):
    def sync(self, minimized: bool | None = None) -> bool: ...
    def close(self) -> None: ...
    def retarget(self, handle: int) -> None: ...
    def geometry(self) -> tuple[int, int, int, int]: ...
    def placement_revision(self) -> int | None: ...


def bind_preview_owner(title: str, owner_handle: int) -> PreviewOwner:
    if sys.platform == "darwin":
        from cephvr.platform.macos.preview_owner import CocoaPreviewOwner

        return CocoaPreviewOwner(title, owner_handle)
    if sys.platform == "win32":
        from cephvr.platform.windows.preview_owner import (
            WindowsPreviewOwner,
            gui_window_identity,
        )

        return WindowsPreviewOwner(title, *gui_window_identity(owner_handle))
    raise RuntimeError("Linked Review previews require macOS or Windows")
