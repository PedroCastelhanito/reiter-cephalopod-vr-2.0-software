"""Compare production uint32 pixel scaling with the uint64 reference."""

from __future__ import annotations

import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from cephvr.shared.pixels.scaling import scale_full_range_into


class Image:
    def __init__(self, pixels: np.ndarray) -> None:
        self.pixels = pixels

    def GetBuffer(self) -> np.ndarray:
        return self.pixels


def scale(source: np.ndarray, scratch: np.ndarray, source_bits: int, target_bits: int):
    source_container = source.dtype.itemsize * 8
    target_container = 8 if target_bits == 8 else 16
    output = bytearray(source.size * (target_container // 8))
    arguments = (
        np,
        Image(source),
        memoryview(output),
        source_bits,
        source_container,
        target_bits,
        target_container,
        scratch,
    )

    def run() -> None:
        scale_full_range_into(*arguments)

    return output, run


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    source_paths = (
        "src/cephvr/shared/pixels/scaling.py",
        "src/cephvr/shared/pixels/preparer.py",
    )
    equality = []
    for source_bits in (8, 10, 12, 16):
        source_container = 8 if source_bits == 8 else 16
        source = np.arange(
            1 << source_container, dtype=np.uint8 if source_container == 8 else "<u2"
        )
        for target_bits in (8, 10, 16):
            outputs = []
            for dtype in (np.uint64, np.uint32):
                output, run = scale(
                    source, np.empty(source.size, dtype=dtype), source_bits, target_bits
                )
                run()
                outputs.append(output)
            if outputs[0] != outputs[1]:
                raise AssertionError((source_bits, target_bits))
            equality.append(
                {
                    "source_bits": source_bits,
                    "target_bits": target_bits,
                    "input_values": source.size,
                    "output_sha256": hashlib.sha256(outputs[0]).hexdigest(),
                }
            )
    timings = []
    for shape, source_bits, target_bits in (
        ((1080, 1920), 16, 8),
        ((1080, 1920), 12, 10),
        ((1024, 1280, 3), 12, 16),
        ((480, 640), 8, 16),
    ):
        size = int(np.prod(shape))
        source = np.arange(size, dtype=np.uint8 if source_bits == 8 else "<u2")
        operations = {}
        entry = {"shape": shape, "source_bits": source_bits, "target_bits": target_bits}
        for dtype in (np.uint64, np.uint32):
            scratch = np.empty(size, dtype=dtype)
            output, run = scale(source, scratch, source_bits, target_bits)
            for _ in range(4):
                run()
            name = np.dtype(dtype).name
            operations[name] = (output, run)
            entry[name] = {"scratch_bytes": scratch.nbytes, "samples_ms": []}
        for round_index in range(10):
            order = ("uint64", "uint32") if round_index % 2 == 0 else ("uint32", "uint64")
            for name in order:
                started = time.perf_counter_ns()
                for _ in range(16):
                    operations[name][1]()
                entry[name]["samples_ms"].append(
                    (time.perf_counter_ns() - started) / 16 / 1e6
                )
        if operations["uint64"][0] != operations["uint32"][0]:
            raise AssertionError(shape)
        for name in operations:
            entry[name]["median_ms"] = statistics.median(entry[name]["samples_ms"])
        entry["median_time_reduction_percent"] = 100 * (
            1 - entry["uint32"]["median_ms"] / entry["uint64"]["median_ms"]
        )
        timings.append(entry)
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "source_sha256": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in source_paths
        },
        "python": sys.version,
        "numpy": np.__version__,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "maximum_intermediate": 65535 * 65535 + 32767,
        "uint32_maximum": int(np.iinfo(np.uint32).max),
        "warmup_calls_per_dtype": 4,
        "timed_rounds": 10,
        "calls_per_round": 16,
        "order": "alternate reference/production order each round",
        "exhaustive_equality": equality,
        "timings": timings,
        "limitations": "CPU synthetic scaling only; no SDK, camera, GPU, native viewer, recording or rig workload.",
    }
    Path(__file__).with_name("result.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
