"""Per-trial sparse-noise generator helper owned by the rendering worker (V04).

The helper is a contained Python child launched through the renderer's shared
helper launcher (plan, OS/operational confirmation, resume, exact-exit cleanup),
like its FFmpeg children. It owns no output file; stdin EOF stops it.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from cephvr.platform.windows.encoder_process import WindowsEncoderProcess
from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.identity import SPARSE_NOISE_ROLE
from cephvr.visual_stimulus.rendering.sparse_noise_ring import SparseNoiseRing
from cephvr.visual_stimulus.rendering.types import ResourceReleaseReport
from cephvr.visual_stimulus.resources.sparse_noise_stream import trial_layers
from cephvr.visual_stimulus.resources.sparse_noise_wire import FrameReader

HELPER_MODULE = "cephvr.visual_stimulus.sparse_noise_helper"
# Patterns generated ahead per concurrently presented layer (E14 policy).
LOOKAHEAD_PATTERNS = 100


def obligation(trial_id: str) -> str:
    return f"sparse-noise-child:{trial_id}"


class SparseNoiseProcess(WindowsEncoderProcess):
    """The contained helper's pipes: binary pattern frames replace FFmpeg progress."""

    max_frame_bytes = 0
    _frames: deque[tuple[int, bytes, bytes]]

    def send(self, data: bytes, *, deadline_ns: int) -> None:
        self.write(data, deadline_ns=deadline_ns)

    def take(self) -> list[tuple[int, bytes, bytes]]:
        with self._lock:
            frames = list(self._frames)
            self._frames.clear()
        return frames

    @property
    def failure(self) -> BaseException | None:
        error = self.reader_error
        if error is None and self._exit_code is not None and not self._stdin_closed:
            return RuntimeError(f"helper exited early with code {self._exit_code}")
        return error

    def _read_progress(self) -> None:
        reader = FrameReader(self.max_frame_bytes)
        while True:
            try:
                chunk = self.progress_pipe.read(
                    deadline_ns=self._reader_read_deadline()
                )
            except TimeoutError:
                if self._reader_deadline_expired():
                    self._record_reader_error(
                        RuntimeError("sparse-noise stdout did not reach EOF")
                    )
                    return
                continue
            except Exception as exc:
                self._record_reader_error(exc)
                return
            if chunk is None:
                if reader.partial and not self._stdin_closed:
                    self._record_reader_error(RuntimeError("truncated pattern frame"))
                return
            try:
                frames = reader.feed(chunk)
            except ValueError as exc:
                self._record_reader_error(exc)
                return
            with self._lock:
                self._frames.extend(frames)


def sparse_process_factory(max_frame_bytes: int) -> Callable[..., SparseNoiseProcess]:
    def create(**kwargs: Any) -> SparseNoiseProcess:
        process = SparseNoiseProcess(**kwargs)
        process.max_frame_bytes = max_frame_bytes
        process._frames = deque()
        return process

    return create


class HelperLauncher(Protocol):
    process_factory: Callable[..., Any]

    def bind_operation(self, work: Any, parent_operation: Any) -> None: ...
    def launch(self, argv: list[str], *, deadline_ns: int, role: str) -> Any: ...
    def terminate_unconfirmed(self, *, deadline_ns: int) -> None: ...


class GraphicsOwner(Protocol):
    @property
    def sparse_outputs(self) -> Mapping[str, Any]: ...
    def install_sparse_noise(self, ring: SparseNoiseRing | None) -> None: ...


class NativeSparseNoise:
    """One helper and one texture ring per prepared trial that contains sparse noise."""

    def __init__(
        self,
        *,
        launcher: HelperLauncher,
        argv: Callable[[], list[str]],
        graphics: GraphicsOwner,
        lookahead: int,
    ) -> None:
        self.launcher, self.argv, self.graphics = launcher, argv, graphics
        self.lookahead = lookahead
        self._lock = threading.Lock()
        self._trial: str | None = None
        self._process: Any = None
        self._ring: SparseNoiseRing | None = None
        self._declared: set[str] = set()

    def declare(
        self,
        artifacts: tuple[PreparedTrial, ...],
        announce: Callable[[str, str | None], None],
    ) -> None:
        """Register each trial's helper obligation at Setup, before any launch."""
        for artifact in artifacts:
            key = obligation(artifact.identity.trial_id)
            if trial_layers(artifact) and key not in self._declared:
                announce(key, None)
                self._declared.add(key)

    def prepare(self, artifact: PreparedTrial, command: Any, deadline_ns: int) -> None:
        """Launch the trial's helper and fill the first lookahead window before Ready."""
        self.finish(deadline_ns)
        layers = trial_layers(artifact)
        if not layers:
            return
        self.launcher.bind_operation(command.target.work, command.parent_operation)
        self.launcher.process_factory = sparse_process_factory(
            max(layer.texel_bytes for layer in layers)
        )
        self._trial = artifact.identity.trial_id
        self._process = self.launcher.launch(
            self.argv(), deadline_ns=deadline_ns, role=SPARSE_NOISE_ROLE
        )
        ring = SparseNoiseRing(
            artifact,
            self._process,
            self.graphics.sparse_outputs,
            lookahead=self.lookahead,
        )
        self._ring = ring
        ring.start(deadline_ns)
        ring.prefill(deadline_ns)
        self.graphics.install_sparse_noise(ring)

    def finish(self, deadline_ns: int) -> None:
        """Release textures, stop the helper by stdin EOF and confirm its exact exit."""
        if self._ring is not None:
            self.graphics.install_sparse_noise(None)
            self._ring.release()
            self._ring = None
        if self._process is not None:
            self._process.close_stdin(deadline_ns=deadline_ns)
            self._process.wait(deadline_ns=deadline_ns)
            self._process = None
        self._trial = None

    def cleanup(self, deadline_ns: int) -> ResourceReleaseReport:
        outstanding = []
        try:
            if self._process is not None and self._process.failure is not None:
                self._process.terminate(deadline_ns=deadline_ns)
                self._process = None
            self.finish(deadline_ns)
            self.launcher.terminate_unconfirmed(deadline_ns=deadline_ns)
        except Exception as exc:
            outstanding.append(f"sparse-noise:{exc}")
        if outstanding:
            return ResourceReleaseReport((), tuple(outstanding))
        # No helper remains: every declared trial obligation is closed.
        released, self._declared = tuple(sorted(self._declared)), set()
        return ResourceReleaseReport(released, ())
