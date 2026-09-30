"""Mapping attachment preserves exact size and open-only handle ownership."""

from __future__ import annotations

import mmap
import sys
from typing import Any
from unittest.mock import Mock

import pytest

from cephvr.platform.windows import mappings

PAGE = mmap.PAGESIZE


class _FakeShared:
    def __init__(self, size: int, events: list[str]) -> None:
        self.size = size
        self.name = "n"
        self.buf = memoryview(bytearray(size))
        self._events = events

    def close(self) -> None:
        self._events.append("shared_close")


def _setup(
    monkeypatch: pytest.MonkeyPatch, size: int, guard: int = 5
) -> tuple[Mock, list[str]]:
    events: list[str] = []
    kernel = Mock()
    kernel.OpenFileMappingW.side_effect = lambda *a: events.append("open") or guard
    kernel.CloseHandle.side_effect = lambda h: events.append(f"close{h}") or True
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(mappings.ctypes, "get_last_error", lambda: 2, raising=False)
    monkeypatch.setattr(mappings, "_kernel32", lambda: kernel)

    def shared(**_kw: Any) -> _FakeShared:
        events.append("shared_open")
        return _FakeShared(size, events)

    monkeypatch.setattr(mappings, "SharedMemory", shared)
    return kernel, events


def test_attach_holds_open_only_handle_across_shared_memory_attach(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _kernel, events = _setup(monkeypatch, PAGE)
    mapping = mappings.SharedMapping.attach("Local\\cephvr-x", 100)
    assert events == ["open", "shared_open", "close5"]
    assert len(mapping.buffer) == 100


def test_attach_missing_name_never_reaches_shared_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _kernel, events = _setup(monkeypatch, PAGE, guard=0)
    with pytest.raises(mappings.MappingError):
        mappings.SharedMapping.attach("Local\\cephvr-x", 100)
    assert events == ["open"]


def test_attach_requires_page_exact_size_and_closes_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _kernel, events = _setup(monkeypatch, 2 * PAGE)  # oversize or fresh mapping
    with pytest.raises(mappings.MappingError):
        mappings.SharedMapping.attach("Local\\cephvr-x", 100)
    assert events[-1] == "close5" and "shared_close" in events


def test_exact_page_multiple_matches_without_rounding_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup(monkeypatch, PAGE)
    mappings.SharedMapping.attach("Local\\cephvr-x", PAGE)
