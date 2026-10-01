"""Exact bounded FeedbackEntry credits under A06/V24 (no rescue queue)."""

from __future__ import annotations

from cephvr.visual_stimulus.v1 import data_pb2 as wire


class FeedbackCredits:
    """Track one attachment/stream's outstanding entries and exact returned credits."""

    def __init__(
        self,
        *,
        attachment_generation: str,
        stream_id: str,
        capacity: int,
    ) -> None:
        if not attachment_generation or not stream_id or capacity <= 0:
            raise ValueError(
                "feedback attachment, stream and positive capacity are required"
            )
        self.attachment_generation = attachment_generation
        self.stream_id = stream_id
        self.capacity = capacity
        self._generation = 0
        self._outstanding: dict[int, str] = {}
        self._last_returned_sequence = 0

    @property
    def available(self) -> int:
        return self.capacity - len(self._outstanding)

    def capture(
        self, *, reset_generation: str, entry_sequence: int
    ) -> wire.FeedbackCredit:
        generation = _generation(reset_generation)
        if type(entry_sequence) is not int or not 0 < entry_sequence <= (1 << 64) - 1:
            raise ValueError("feedback entry sequence must be a positive uint64")
        if generation < self._generation:
            return self._credit(reset_generation, entry_sequence)
        if generation > self._generation:
            self._generation = generation
            self._outstanding.clear()
            self._last_returned_sequence = 0
        previous = self._outstanding.get(entry_sequence)
        if previous is not None:
            if previous != reset_generation:
                raise ValueError("entry sequence was reused across reset generations")
            raise ValueError("feedback entry sequence was admitted more than once")
        if not self.available:
            raise BufferError("feedback queue exceeded its prepared credit capacity")
        self._outstanding[entry_sequence] = reset_generation
        return self._credit(reset_generation, entry_sequence)

    def return_credit(self, credit: wire.FeedbackCredit) -> bool:
        """Apply one exact credit; return False for harmless identical duplicates."""
        if (
            credit.attachment_generation != self.attachment_generation
            or credit.stream_id != self.stream_id
            or not credit.HasField("entry_sequence")
        ):
            raise ValueError("feedback credit identity differs from its attachment")
        _generation(credit.reset_generation)
        if _generation(credit.reset_generation) < self._generation:
            return False
        if credit.entry_sequence <= self._last_returned_sequence:
            return False
        if self._outstanding and credit.entry_sequence != min(self._outstanding):
            raise ValueError(
                "feedback credits must retire captured entries in pipe order"
            )
        outstanding = self._outstanding.get(credit.entry_sequence)
        if outstanding != credit.reset_generation:
            raise ValueError("feedback credit names an unknown or conflicting entry")
        del self._outstanding[credit.entry_sequence]
        self._last_returned_sequence = credit.entry_sequence
        return True

    def _credit(self, generation: str, sequence: int) -> wire.FeedbackCredit:
        return wire.FeedbackCredit(
            attachment_generation=self.attachment_generation,
            stream_id=self.stream_id,
            reset_generation=generation,
            entry_sequence=sequence,
        )


def _generation(value: str) -> int:
    if (
        not value
        or not value.isascii()
        or not value.isdecimal()
        or value.startswith("0")
    ):
        raise ValueError("feedback reset generation must be canonical positive decimal")
    parsed = int(value)
    if parsed > (1 << 64) - 1:
        raise ValueError("feedback reset generation exceeds uint64")
    return parsed
