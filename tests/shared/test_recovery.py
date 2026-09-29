"""Startup evidence must remain private, exact and generation-bound."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from cephvr.shared.recovery import (
    ApplicationExitReceipt,
    RecoveryStore,
    RecoveryStoreError,
    UnfinishedSessionPointer,
)


def _id() -> str:
    return str(uuid.uuid4())


def test_pointer_and_receipt_are_exact_and_immutable(tmp_path: Path) -> None:
    store = RecoveryStore(tmp_path / "runtime")
    pointer = UnfinishedSessionPointer(str(tmp_path / "session"), _id(), _id(), _id())
    store.write_pointer(pointer)
    store.write_pointer(pointer)
    assert store.read_pointer() == pointer
    with pytest.raises(RecoveryStoreError, match="another unfinished"):
        store.write_pointer(
            UnfinishedSessionPointer(str(tmp_path / "other"), _id(), _id(), _id())
        )
    receipt = ApplicationExitReceipt(
        pointer.controller_generation, pointer.supervisor_generation, 101, True
    )
    store.write_exit_receipt(receipt)
    store.write_exit_receipt(receipt)
    assert store.read_exit_receipt(pointer.controller_generation) == receipt
    assert store.read_exit_receipt(_id()) is None
    with pytest.raises(RecoveryStoreError, match="changed"):
        store.write_exit_receipt(
            ApplicationExitReceipt(
                pointer.controller_generation, pointer.supervisor_generation, 102, True
            )
        )
    with pytest.raises(RecoveryStoreError, match="changed"):
        store.clear_pointer(
            UnfinishedSessionPointer(str(tmp_path / "wrong"), _id(), _id(), _id())
        )
    store.clear_pointer(pointer)
    assert store.read_pointer() is None


def test_unverified_exit_and_unsafe_pointer_cannot_authorize_recovery(
    tmp_path: Path,
) -> None:
    store = RecoveryStore(tmp_path / "runtime")
    with pytest.raises(ValueError, match="not verified"):
        ApplicationExitReceipt(_id(), _id(), 1, False)
    try:
        store.pointer_path.symlink_to(tmp_path / "outside")
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows account lacks symlink creation privilege")
        raise
    with pytest.raises(RecoveryStoreError, match="owner-only"):
        store.read_pointer()


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode verification")
def test_world_readable_record_is_rejected(tmp_path: Path) -> None:
    store = RecoveryStore(tmp_path / "runtime")
    store.pointer_path.write_text("{}")
    store.pointer_path.chmod(0o644)
    with pytest.raises(RecoveryStoreError, match="owner-only"):
        store.read_pointer()


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode fixture")
def test_duplicate_recovery_fields_cannot_select_an_identity(tmp_path: Path) -> None:
    store = RecoveryStore(tmp_path / "runtime")
    store.pointer_path.write_bytes(
        b'{"session_directory":"/tmp/a","session_directory":"/tmp/b"}'
    )
    store.pointer_path.chmod(0o600)
    with pytest.raises(RecoveryStoreError, match="repeats a field"):
        store.read_pointer()
