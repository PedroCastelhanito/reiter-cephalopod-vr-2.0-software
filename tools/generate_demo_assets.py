"""Generate local authoring samples; these are not calibrated scientific stimuli."""

from __future__ import annotations

import argparse
import math
import random
import shutil
import struct
import zlib
from collections.abc import Callable
from pathlib import Path

Pixel = tuple[int, int, int] | int


def _png(pixel: Callable[[int, int], Pixel]) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack("!I", len(data))
            + kind
            + data
            + struct.pack("!I", zlib.crc32(kind + data))
        )

    rows = bytearray()
    for y in range(256):
        rows.append(0)
        for x in range(256):
            value = pixel(x, y)
            rows.extend((value,) * 3 if isinstance(value, int) else value)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack("!2I5B", 256, 256, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def generate(output: Path) -> int:
    """Copy source descriptors and generate nine deterministic RGB8 samples."""
    templates = Path(__file__).resolve().parents[1] / "demo_assets"
    for source in templates.rglob("*.json"):
        target = output / source.relative_to(templates)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target.resolve():
            shutil.copyfile(source, target)
    noise = random.Random(0)
    colors = ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0))
    samples: dict[str, Callable[[int, int], Pixel]] = {
        "images/01_gray_50.png": lambda x, y: 128,
        "images/02_white.png": lambda x, y: 255,
        "images/03_black.png": lambda x, y: 0,
        "images/04_gradient.png": lambda x, y: x,
        "images/05_circle.png": lambda x, y: (
            255 if (x - 128) ** 2 + (y - 128) ** 2 <= 64**2 else 0
        ),
        "images/06_color_quadrants.png": lambda x, y: colors[(y // 128) * 2 + x // 128],
        "textures/checkerboard.png": lambda x, y: ((x // 32 + y // 32) % 2) * 255,
        "textures/noise.png": lambda x, y: noise.randrange(256),
        "textures/sine_grating.png": lambda x, y: round(
            127.5 * (1 + math.sin(2 * math.pi * x / 32))
        ),
    }
    for name, pixel in samples.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_png(pixel))
    return len(samples)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "demo_assets",
    )
    args = parser.parse_args()
    print(f"Generated {generate(args.output)} local sample images in {args.output}.")
