"""Bounded asynchronous GPU clipping evidence (V21, output-range contract)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cephvr.visual_stimulus.rendering.types import DiagnosticSnapshot

DIAGNOSTIC_SLOTS = 16
DIAGNOSTIC_WORDS = 4
DIAGNOSTIC_BYTES = DIAGNOSTIC_WORDS * 4
_STAGES = ((0, "alpha"), (1, "linear_output"), (2, "device_code"))
_NONFINITE_BIT = 1 << 3


def reservation_bytes(output_count: int) -> int:
    if output_count < 0:
        raise ValueError("diagnostic output count cannot be negative")
    return output_count * DIAGNOSTIC_SLOTS * DIAGNOSTIC_BYTES


def decode_flags(flags: tuple[int, int, int, int]) -> tuple[str, ...]:
    if len(flags) != DIAGNOSTIC_WORDS or any(value < 0 for value in flags):
        raise ValueError("diagnostic flags must contain four unsigned words")
    if flags[3] & _NONFINITE_BIT:
        raise RuntimeError("GPU clipping diagnostic observed a nonfinite color value")
    return tuple(name for index, name in _STAGES if flags[index] & 1)


@dataclass(slots=True)
class _Slot:
    buffer: Any
    sync: Any | None = None
    group_id: int = -1
    output_id: str = ""
    epoch_index: int = -1
    evaluation_host_ns: int = -1


class DiagnosticRing:
    """A per-context SSBO ring; read only after a zero-timeout fence poll signals."""

    def __init__(self, context: Any, retain: Any) -> None:
        self._slots: list[_Slot] = []
        self._active: _Slot | None = None
        for _ in range(DIAGNOSTIC_SLOTS):
            buffer = retain(context.buffer(reserve=DIAGNOSTIC_BYTES))
            self._slots.append(_Slot(buffer))

    @property
    def pending(self) -> bool:
        return any(slot.sync is not None for slot in self._slots)

    def begin(
        self, group_id: int, output_id: str, epoch_index: int, evaluation_host_ns: int
    ) -> None:
        from OpenGL import GL

        slot = next((item for item in self._slots if item.sync is None), None)
        if slot is None:
            raise RuntimeError("required clipping diagnostic ring is full")
        slot.buffer.write(bytes(DIAGNOSTIC_BYTES))
        GL.glBindBufferBase(GL.GL_SHADER_STORAGE_BUFFER, 3, slot.buffer.glo)
        slot.group_id = group_id
        slot.output_id = output_id
        slot.epoch_index = epoch_index
        slot.evaluation_host_ns = evaluation_host_ns
        # The active slot is also the one with no fence and matching metadata.
        self._active = slot

    def end(self) -> None:
        from OpenGL import GL

        slot = self._active
        if slot is None:
            raise RuntimeError("diagnostic ring end has no active render group")
        GL.glMemoryBarrier(
            GL.GL_SHADER_STORAGE_BARRIER_BIT | GL.GL_BUFFER_UPDATE_BARRIER_BIT
        )
        slot.sync = GL.glFenceSync(GL.GL_SYNC_GPU_COMMANDS_COMPLETE, 0)
        if not slot.sync:
            slot.sync = None
            self._active = None
            raise RuntimeError("GPU diagnostic fence creation failed")
        GL.glFlush()
        self._active = None

    def poll(self) -> tuple[DiagnosticSnapshot, ...]:
        from OpenGL import GL

        completed: list[DiagnosticSnapshot] = []
        pending = sorted(
            (slot for slot in self._slots if slot.sync is not None),
            key=lambda slot: slot.group_id,
        )
        for slot in pending:
            assert slot.sync is not None
            status = GL.glClientWaitSync(slot.sync, 0, 0)
            if status == GL.GL_WAIT_FAILED:
                raise RuntimeError("GPU diagnostic fence wait failed")
            if status not in (GL.GL_ALREADY_SIGNALED, GL.GL_CONDITION_SATISFIED):
                break
            words = slot.buffer.read(DIAGNOSTIC_BYTES)
            flags = (
                int.from_bytes(words[0:4], "little"),
                int.from_bytes(words[4:8], "little"),
                int.from_bytes(words[8:12], "little"),
                int.from_bytes(words[12:16], "little"),
            )
            GL.glDeleteSync(slot.sync)
            slot.sync = None
            stages = decode_flags(flags)
            completed.append(
                DiagnosticSnapshot(
                    slot.group_id,
                    slot.output_id,
                    slot.epoch_index,
                    slot.evaluation_host_ns,
                    stages,
                )
            )
        return tuple(completed)

    def release(self) -> None:
        from OpenGL import GL

        for slot in self._slots:
            if slot.sync is not None:
                GL.glDeleteSync(slot.sync)
                slot.sync = None
        self._slots.clear()
