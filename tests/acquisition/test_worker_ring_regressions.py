"""Prepared Windows-native ring regressions; execution is reserved for E15 rig."""

from __future__ import annotations

import sys
from typing import cast
from uuid import uuid4

import pytest

from cephvr.acquisition.buffers import ring_attachment
from cephvr.acquisition.buffers.layout import (
    HEADER_BYTES,
    allocation_size,
    write_header,
)
from cephvr.acquisition.buffers.records import FrameRecord
from cephvr.acquisition.buffers.ring import (
    FLAG_INPUT_SEALED,
    FLAG_RETIRED,
    PartialRingOwnership,
    RingAllocationError,
    RingError,
    SharedRing,
    _store_expected,
)
from cephvr.acquisition.camera.types import PixelLayout
from cephvr.acquisition.v1 import camera_pb2
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows import atomics
from cephvr.platform.windows.events import AutoResetEvent
from cephvr.platform.windows.mappings import SharedMapping
from cephvr.shared.pixels.types import NativePixelFormat

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="ring tests require documented Win32 atomics"
)


class _Event:
    def set(self) -> None:
        pass

    def close(self) -> None:
        pass


class _Mapping:
    def __init__(self, size: int) -> None:
        self.buffer = memoryview(bytearray(size))

    def close(self) -> None:
        pass


def _ring() -> tuple[SharedRing, PixelLayout]:
    pixel_layout = PixelLayout(
        width=1,
        height=1,
        pixel_format=NativePixelFormat(
            "Mono8", 1, 8, "mono", "unpacked", "byte", "lsb"
        ),
        row_stride_bytes=1,
        image_payload_bytes=1,
    )
    owner = control.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    producer = control.ProcessIdentity(
        role="acquisition_tracking_worker", generation=str(uuid4())
    )
    consumer = control.ProcessIdentity(role="tracking", generation=str(uuid4()))
    allocation = uuid4()
    session_id = str(uuid4())
    descriptor = acq.FrameBufferDescriptor(
        allocation_id=str(allocation),
        owner=owner,
        producer=producer,
        consumer=consumer,
        camera=camera_pb2.CAMERA_ROLE_TRACKING,
        kind=acq.FRAME_BUFFER_KIND_TRACKING,
        layout_version=2,
        capacity_frames=1,
        shared_memory_name=f"Local\\cephvr-{allocation}-frames",
        configuration_revision=1,
        allocation_bytes=allocation_size(1, 1),
    )
    descriptor.session.session_id = session_id
    descriptor.image.width = 1
    descriptor.image.height = 1
    descriptor.image.pixel_format = "Mono8"
    descriptor.image.row_stride_bytes = 1
    descriptor.image.image_payload_bytes = 1
    attachment = acq.FrameBufferAttachment(buffer=descriptor)
    attachment.sync.transfer_id = str(uuid4())
    attachment.sync.target.CopyFrom(producer)
    attachment.sync.event_name = f"Local\\cephvr-{allocation}-event"
    mapping = _Mapping(descriptor.allocation_bytes)
    ring = SharedRing(
        attachment,
        pixel_layout,
        mapping,  # type: ignore[arg-type]
        _Event(),  # type: ignore[arg-type]
        owner=True,
        producer=True,
        consumer=True,
    )
    write_header(
        mapping.buffer,
        descriptor.kind,
        descriptor.capacity_frames,
        uuid4(),
        allocation,
        FLAG_INPUT_SEALED,
        0,
        0,
    )
    return ring, pixel_layout


def test_ring_publish_read_lap_reset_and_retirement_are_run_bound() -> None:
    ring, _layout = _ring()
    first_run, next_run = uuid4(), uuid4()
    ring.reset_quiescent(first_run, prior_completion_confirmed=True)
    ring.open_admission(first_run)
    record = FrameRecord(0, 100, None, None, True, None)
    ring.publish(record, memoryview(b"a"))
    target = bytearray(1)
    result = ring.read_into(0, target, expected_run_id=first_run)
    assert result.status == "frame" and target == b"a"

    ring.publish(FrameRecord(1, 101, None, None, True, None), memoryview(b"b"))
    assert ring.read_into(0, target, expected_run_id=first_run).status == "lapped"
    with pytest.raises(RingError, match="stale or different run"):
        ring.read_into(1, target, expected_run_id=next_run)

    ring.seal()
    ring.reset_quiescent(next_run, prior_completion_confirmed=True)
    assert ring.published_count == 0
    ring.open_admission(next_run)
    ring.publish(FrameRecord(0, 200, None, None, True, None), memoryview(b"c"))
    assert ring.read_into(0, target, expected_run_id=next_run).status == "frame"
    ring.retire("prepared retirement evidence")
    assert ring.read_into(0, target, expected_run_id=next_run).status == "retired"
    ring.close()


def test_ring_copy_recheck_reports_torn_when_slot_generation_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ring, _layout = _ring()
    run_id = uuid4()
    ring.reset_quiescent(run_id, prior_completion_confirmed=True)
    ring.open_admission(run_id)
    ring.publish(FrameRecord(0, 100, None, None, True, None), memoryview(b"x"))
    offset = HEADER_BYTES
    original = atomics.atomic_load_u64
    generation_reads = 0

    def changing_generation(buffer: memoryview, word_offset: int) -> int:
        nonlocal generation_reads
        value = original(buffer, word_offset)
        if word_offset == offset:
            generation_reads += 1
            if generation_reads == 2:
                return value + 2
        return value

    monkeypatch.setattr(
        "cephvr.acquisition.buffers.ring.atomic_load_u64", changing_generation
    )
    result = ring.read_into(0, bytearray(1), expected_run_id=run_id)
    assert result.status == "torn"
    ring.close()


def test_ring_read_does_not_accept_copy_if_run_changes_during_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ring, _layout = _ring()
    run_id, replacement_run = uuid4(), uuid4()
    ring.reset_quiescent(run_id, prior_completion_confirmed=True)
    ring.open_admission(run_id)
    ring.publish(FrameRecord(0, 100, None, None, True, None), memoryview(b"x"))
    original = atomics.atomic_load_u64
    generation_reads = 0

    def change_run_after_copy(buffer: memoryview, word_offset: int) -> int:
        nonlocal generation_reads
        value = original(buffer, word_offset)
        if word_offset == HEADER_BYTES:
            generation_reads += 1
            if generation_reads == 2:
                buffer[24:40] = replacement_run.bytes
        return value

    monkeypatch.setattr(
        "cephvr.acquisition.buffers.ring.atomic_load_u64", change_run_after_copy
    )
    destination = bytearray(1)
    result = ring.read_into(0, destination, expected_run_id=run_id)
    assert result.status == "torn"
    assert destination == b"x"
    ring.close()


def test_ring_retirement_cannot_be_cleared_by_stale_flag_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ring, _layout = _ring()
    run_id = uuid4()
    ring.reset_quiescent(run_id, prior_completion_confirmed=True)
    injected = False

    def retire_between_read_and_cas(
        buffer: memoryview, offset: int, expected: int, replacement: int
    ) -> None:
        nonlocal injected
        if offset == 16 and not injected:
            injected = True
            retired = expected | ((FLAG_INPUT_SEALED | FLAG_RETIRED) << 32)
            assert atomics.atomic_compare_exchange_u64(
                buffer, offset, expected, retired
            )
        _store_expected(buffer, offset, expected, replacement)

    monkeypatch.setattr(
        "cephvr.acquisition.buffers.ring._store_expected", retire_between_read_and_cas
    )
    with pytest.raises(RingError, match="changed unexpectedly"):
        ring.open_admission(run_id)
    assert ring.retired
    assert ring.input_sealed
    with pytest.raises(RingError, match="irreversible"):
        ring.open_admission(run_id)
    ring.seal()
    assert ring.retired and ring.input_sealed
    ring.close()


def test_event_creation_failure_retains_unclosed_mapping_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ring, layout = _ring()
    attachment = acq.FrameBufferAttachment.FromString(
        ring._attachment.SerializeToString(deterministic=True)
    )
    owner = ring.descriptor.owner
    ring.close()

    class Mapping:
        buffer = memoryview(bytearray(attachment.buffer.allocation_bytes))
        close_attempts = 0

        def close(self) -> None:
            self.close_attempts += 1
            raise OSError("injected close failure")

    mapping = Mapping()

    def fail_event(*_args: object, **_kwargs: object) -> object:
        raise OSError("injected event creation failure")

    monkeypatch.setattr(SharedMapping, "create", lambda *_args: mapping)
    monkeypatch.setattr(AutoResetEvent, "create", fail_event)
    with pytest.raises(RingAllocationError) as failure:
        ring_attachment.create_ring(SharedRing, attachment, layout, owner)
    partial = failure.value.partial
    assert isinstance(partial, PartialRingOwnership)
    assert partial.mapping is cast(SharedMapping, mapping)
    assert partial.event is None
    assert mapping.close_attempts == 1
