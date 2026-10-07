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
    finally:
        source.close_after_consumers()
    source.close_after_consumers()
    with pytest.raises(ProtectedSourceError, match="closed"):
        source.independent_reader()
    path.write_bytes(b"released")
    assert path.read_bytes() == b"released"
