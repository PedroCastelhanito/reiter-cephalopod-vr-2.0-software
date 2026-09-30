"""Preallocated integer full-range quantization used by preview and recording (A10)."""

from __future__ import annotations

from typing import Any


def scale_full_range_into(
    numpy: Any,
    image: Any,
    output: memoryview,
    source_bits: int,
    source_container_bits: int,
    target_bits: int,
    target_container_bits: int,
    scratch: Any,
) -> None:
    """Scale declared MSB-aligned input directly into caller storage with nearest rounding."""
    source = numpy.frombuffer(
        image.GetBuffer(),
        dtype="<u2" if source_container_bits == 16 else numpy.uint8,
    )
    source_max = (1 << source_bits) - 1
    source_shift = source_container_bits - source_bits
    denominator = source_max << source_shift
    target_max = (1 << target_bits) - 1
    target_shift = target_container_bits - target_bits
    if source.size != scratch.size or output.nbytes != source.size * (
        target_container_bits // 8
    ):
        raise ValueError("pixel scaling buffers differ from resolved representation")
    # Widen before arithmetic: ufunc resolution otherwise may multiply in the
    # narrower source dtype and only cast the already-overflowed result to uint64.
    numpy.copyto(scratch, source, casting="unsafe")
    numpy.multiply(scratch, target_max, out=scratch)
    numpy.add(scratch, denominator // 2, out=scratch)
    numpy.floor_divide(scratch, denominator, out=scratch)
    if target_shift:
        numpy.left_shift(scratch, target_shift, out=scratch)
    target = numpy.frombuffer(
        output,
        dtype="<u2" if target_container_bits == 16 else numpy.uint8,
    )
    numpy.copyto(target, scratch, casting="unsafe")
