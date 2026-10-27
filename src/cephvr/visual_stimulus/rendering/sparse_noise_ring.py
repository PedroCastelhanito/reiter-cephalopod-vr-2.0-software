"""GL-owned textures for one trial's streamed sparse-noise patterns (V04).

The helper produces requests in the shared time order; this owner uploads each
frame as an RGBA8 texture for the outputs showing that screen, grants credit as
displayed patterns retire, and selects the due pattern or holds the previous one.
"""

from __future__ import annotations

import itertools
import time
from collections import deque
from collections.abc import Callable, Iterator, Mapping
from dataclasses import replace
from typing import Any, Protocol

from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.resources.sparse_noise import GENERATOR
from cephvr.visual_stimulus.resources.sparse_noise_stream import (
    PatternRequest,
    SparseLayer,
    requests,
    trial_layers,
)
from cephvr.visual_stimulus.resources.sparse_noise_wire import encode_credit, encode_job

from .types import ImageSnapshot, InstanceSnapshot


class SparseNoiseError(RuntimeError):
    pass


class PatternFeed(Protocol):
    """One helper's pipes: ordered frames in, JOB/CREDIT lines out."""

    def send(self, data: bytes, *, deadline_ns: int) -> None: ...
    def take(self) -> list[tuple[int, bytes, bytes]]: ...
    @property
    def failure(self) -> BaseException | None: ...


def concurrent_layers(layers: tuple[SparseLayer, ...]) -> int:
    counts: dict[int, int] = {}
    for layer in layers:
        counts[layer.epoch_index] = counts.get(layer.epoch_index, 0) + 1
    return max(counts.values(), default=0)


def ring_gpu_bytes(
    artifact: PreparedTrial, lookahead: int, layers: tuple[SparseLayer, ...]
) -> int:
    """Upper bound for admission: every in-flight request at the largest grid."""
    if not layers:
        return 0
    outputs = len(artifact.display.active_outputs)
    window = lookahead * concurrent_layers(layers)
    return (window + len(layers)) * max(x.texel_bytes for x in layers) * outputs


class SparseNoiseRing:
    def __init__(
        self,
        artifact: PreparedTrial,
        feed: PatternFeed,
        outputs: Mapping[str, Any],
        *,
        lookahead: int,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        if lookahead <= 0:
            raise ValueError("sparse-noise lookahead must be positive")
        self.artifact, self.feed, self.outputs = artifact, feed, outputs
        self.clock_ns = clock_ns
        self.layers = trial_layers(artifact)
        # Lookahead counts patterns per concurrently presented layer.
        self.window = lookahead * concurrent_layers(self.layers)
        self.total = sum(layer.shown for layer in self.layers)
        self._pending: Iterator[PatternRequest] = requests(self.layers)
        self._expected: deque[PatternRequest] = deque()
        self._index = {
            (layer.epoch_index, layer.instance_id): i
            for i, layer in enumerate(self.layers)
        }
        order = [o.output_id for o in artifact.display.active_outputs]
        self._output_index = {name: i for i, name in enumerate(order)}
        self._layer_outputs = tuple(
            tuple(
                sorted(
                    self._output_index[m.output_id]
                    for m in artifact.display.active_mappings
                    if m.surface_id == layer.grid.surface_id
                )
            )
            for layer in self.layers
        )
        self._resident: dict[tuple[int, int], list[Any]] = {}
        self._digests: dict[tuple[int, int], str] = {}
        self._pool: dict[tuple[int, int, int], list[Any]] = {}
        self._bound: dict[int, int] = {}
        self._last: dict[str, tuple[int, int | None]] = {}
        self._blank: dict[int, Any] = {}
        self._epoch = -1
        self._received = self._released = self._credit = 0

    @property
    def received(self) -> int:
        return self._received

    def start(self, deadline_ns: int) -> None:
        self.feed.send(encode_job(self.layers), deadline_ns=deadline_ns)
        self._grant(deadline_ns)

    def prefill(self, deadline_ns: int, *, sleep_s: float = 0.001) -> None:
        """Block until the first lookahead window is resident, before Ready."""
        target = min(self.window, self.total)
        while self._received < target:
            self.service()
            if self._received >= target:
                break
            if self.clock_ns() >= deadline_ns:
                raise TimeoutError(
                    f"sparse-noise prefill reached {self._received}/{target} patterns"
                )
            time.sleep(sleep_s)

    def service(self) -> None:
        failure = self.feed.failure
        if failure is not None:
            raise SparseNoiseError(f"sparse-noise generator failed: {failure}")
        for sequence, texels, digest in self.feed.take():
            request = self._expected.popleft() if self._expected else None
            if request is None or request.sequence != sequence:
                raise SparseNoiseError("sparse-noise frame arrived out of order")
            layer = self.layers[request.layer]
            if len(texels) != layer.texel_bytes:
                raise SparseNoiseError("sparse-noise frame size differs from its grid")
            self._received += 1
            bound = self._bound.get(request.layer, -1)
            if layer.epoch_index < self._epoch or request.pattern < bound:
                self._released += 1  # Arrived after it was due; never shown.
                continue
            key = (request.layer, request.pattern)
            self._resident[key] = self._upload(request.layer, texels)
            self._digests[key] = digest.hex()

    def select(
        self,
        epoch_index: int,
        local_ns: int,
        snapshots: tuple[InstanceSnapshot, ...],
        *,
        deadline_ns: int,
    ) -> tuple[InstanceSnapshot, ...]:
        self.service()
        if epoch_index != self._epoch:
            for key in [
                k for k in self._resident if self.layers[k[0]].epoch_index < epoch_index
            ]:
                self._retire(key)
            self._epoch = epoch_index
        selected = []
        for snapshot in snapshots:
            settings = snapshot.settings
            if settings is None or settings.kind != "sparse_noise":
                selected.append(snapshot)
                continue
            layer = self._index.get((epoch_index, snapshot.instance_id))
            if layer is None:
                raise SparseNoiseError(
                    "sparse-noise layer is not in the prepared trial"
                )
            requested = settings.pattern_at(local_ns)
            # Show the newest resident pattern already due. Retiring older ones
            # always frees credit, so a lagging helper can never stall the window.
            due = [k[1] for k in self._resident if k[0] == layer and k[1] <= requested]
            if due:
                newest = max(due)
                for pattern in due:
                    if pattern != newest:
                        self._retire((layer, pattern))
                self._bound[layer] = newest
            actual = self._bound.get(layer)
            textures = (
                tuple(self._resident[(layer, actual)])
                if actual is not None
                else tuple(
                    self._blank_texture(i) for i in range(len(self._output_index))
                )
            )
            previous = self._last.get(snapshot.instance_id)
            self._last[snapshot.instance_id] = (layer, actual)
            repeated = previous == (layer, actual)
            # The first frame showing a pattern carries its generated-cell hash.
            digest = (
                None if actual is None or repeated else self._digests[(layer, actual)]
            )
            selection = ImageSnapshot(
                snapshot.instance_id,
                snapshot.instance_id,
                requested,
                snapshot.instance_id,
                actual,
                "background_hold"
                if actual is None
                else "current"
                if actual == requested
                else "residency_hold",
                repeated,
                digest,
                GENERATOR if digest is not None else None,
            )
            selected.append(
                replace(snapshot, image_selection=selection, sparse_textures=textures)
            )
        self._grant(deadline_ns)
        return tuple(selected)

    def release(self) -> None:
        """Release every texture; the caller confirms the helper separately."""
        for key in tuple(self._resident):
            self._retire(key)
        for (_, _, output), textures in self._pool.items():
            self._activate(output)
            for texture in textures:
                texture.release()
        self._pool.clear()
        for output, texture in self._blank.items():
            self._activate(output)
            texture.release()
        self._blank.clear()

    def _requests(self, count: int) -> list[PatternRequest]:
        return list(itertools.islice(self._pending, max(0, count)))

    def _grant(self, deadline_ns: int) -> None:
        limit = min(self.total, self._released + self.window)
        if limit > self._credit:
            self._expected.extend(self._requests(limit - self._credit))
            self._credit = limit
            self.feed.send(encode_credit(limit), deadline_ns=deadline_ns)

    def _upload(self, layer: int, texels: bytes) -> list[Any]:
        grid = self.layers[layer].grid
        textures: list[Any] = [None] * len(self._output_index)
        for output in self._layer_outputs[layer]:
            pool = self._pool.setdefault((grid.columns, grid.rows, output), [])
            self._activate(output)
            if pool:
                texture = pool.pop()
            else:
                context = tuple(self.outputs.values())[output].context
                texture = context.texture((grid.columns, grid.rows), 4, dtype="f1")
                texture.filter = (0x2600, 0x2600)  # GL_NEAREST: one texel per cell.
                texture.repeat_x = texture.repeat_y = False
            texture.write(texels, alignment=1)
            textures[output] = texture
        return textures

    def _retire(self, key: tuple[int, int]) -> None:
        grid = self.layers[key[0]].grid
        for output, texture in enumerate(self._resident.pop(key)):
            if texture is not None:
                self._pool.setdefault((grid.columns, grid.rows, output), []).append(
                    texture
                )
        self._digests.pop(key, None)
        self._released += 1
        if self._bound.get(key[0]) == key[1]:
            del self._bound[key[0]]

    def _blank_texture(self, output: int) -> Any:
        if output not in self._blank:
            self._activate(output)
            context = tuple(self.outputs.values())[output].context
            self._blank[output] = context.texture((1, 1), 4, bytes(4), dtype="f1")
        return self._blank[output]

    def _activate(self, output: int) -> None:
        tuple(self.outputs.values())[output].activate()
