"""Windows-only ownership checks; no GPU, camera or experiment hardware is used."""

from __future__ import annotations

import sys

import pytest

from cephvr.platform.windows.protected_source import (
    ProtectedSourceError,
    ProtectedWindowsSource,
)

pytestmark = [
    pytest.mark.windows,
    pytest.mark.skipif(
        sys.platform != "win32", reason="requires Windows file sharing semantics"
    ),
]


def test_protected_source_denies_mutation_until_all_reader_owners_close(tmp_path):
    path = tmp_path / "asset.bin"
    path.write_bytes(b"0123456789")
    source = ProtectedWindowsSource(path)
    try:
        with (
            source.independent_reader() as first,
            source.independent_reader() as second,
        ):
            assert first.read(2) == b"01"
            assert second.read(4) == b"0123"
            assert first.read(2) == b"23"
            with pytest.raises(OSError):
                path.write_bytes(b"replaced")
            with pytest.raises(OSError):
                path.rename(tmp_path / "moved.bin")
            assert source.identity == ProtectedWindowsSource._file_identity(
                source._handle
            )
        for _ in range(32):
            with source.independent_reader() as reader:
                assert reader.read() == b"0123456789"
            assert reader.closed
    finally:
        source.close_after_consumers()
    source.close_after_consumers()
    with pytest.raises(ProtectedSourceError, match="closed"):
        source.independent_reader()
    path.write_bytes(b"released")
    assert path.read_bytes() == b"released"


def test_protected_source_identity_reuses_native_abi_type(monkeypatch):
    import ctypes
    from types import SimpleNamespace

    observed = []

    class Information:
        succeeded = True

        def __call__(self, handle, info):
            observed.append(self.argtypes[1])
            info._obj.volume = handle
            info._obj.index_high = handle + 1
            info._obj.index_low = handle + 2
            return self.succeeded

    information = Information()
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *args, **kwargs: SimpleNamespace(GetFileInformationByHandle=information),
    )
    for handle in range(256):
        assert ProtectedWindowsSource._file_identity(handle) == (
            handle,
            handle + 1,
            handle + 2,
        )
    assert len(set(observed)) == 1
    information.succeeded = False
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 6)
    with pytest.raises(OSError) as error:
        ProtectedWindowsSource._file_identity(1)
    assert error.value.winerror == 6
