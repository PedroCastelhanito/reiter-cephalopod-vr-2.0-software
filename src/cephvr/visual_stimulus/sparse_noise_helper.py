"""Sparse-noise generator helper: a contained child of the rendering worker (V04).

Launched per trial through the shared contained launcher with stdin/stdout pipes;
stdin EOF is its stop request. Generation is the unchanged seeded v2 generator.
"""

from __future__ import annotations

import sys
import threading
from typing import BinaryIO

from cephvr.visual_stimulus.resources.sparse_noise_stream import (
    pattern_frame,
    requests,
)
from cephvr.visual_stimulus.resources.sparse_noise_wire import (
    decode_credit,
    decode_job,
    frame_header,
)


class _Stopped(Exception):
    pass


class _Credit:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._limit = 0
        self._eof = False

    def read(self, stream: BinaryIO) -> None:
        try:
            for line in stream:
                limit = decode_credit(line)
                with self._condition:
                    self._limit = max(self._limit, limit)
                    self._condition.notify_all()
        finally:
            with self._condition:
                self._eof = True
                self._condition.notify_all()

    def wait(self, sequence: int) -> None:
        with self._condition:
            while sequence >= self._limit and not self._eof:
                self._condition.wait()
            if self._eof:
                raise _Stopped

    def check(self) -> None:
        if self._eof:  # Prompt stop between cell batches; no lock needed for a flag.
            raise _Stopped


def run(stdin: BinaryIO, stdout: BinaryIO) -> int:
    layers = decode_job(stdin.readline())
    credit = _Credit()
    reader = threading.Thread(
        target=credit.read, args=(stdin,), name="sparse-noise-credit", daemon=True
    )
    reader.start()
    try:
        for request in requests(layers):
            credit.wait(request.sequence)
            texels, digest = pattern_frame(
                layers[request.layer], request.pattern, check=credit.check
            )
            stdout.write(frame_header(request.sequence, len(texels), digest))
            stdout.write(texels)
            stdout.flush()
        credit.wait(1 << 63)  # Every request sent: idle until the owner stops us.
    except (_Stopped, BrokenPipeError):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.stdin.buffer, sys.stdout.buffer))
