"""Generate local authoring samples; these are not calibrated scientific stimuli."""

from __future__ import annotations

import argparse
import json
import math
import random
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
    """Generate external authoring descriptors and nine deterministic RGB8 samples."""
    repository = Path(__file__).resolve().parents[1]
    if output.resolve().is_relative_to(repository):
        raise ValueError("Authoring samples must be generated outside the repository")
    for name in ("checkerboard", "noise", "sine_grating"):
        target = output / "textures" / f"{name}.texture.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "cephvr_asset_type": "texture_design",
                    "kind": "texture",
                    "pattern": "image",
                    "preview_file": f"{name}.png",
                    "params": {
                        "texture_path": f"{name}.png",
                        "tile_width_mm": 40,
                        "tile_height_mm": 40,
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
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
    manifest = {
        "purpose": "Dummy media for local protocol authoring; not calibrated scientific stimuli.",
        "images": [name for name in samples if name.startswith("images/")],
        "textures": [
            f"textures/{name}.texture.json"
            for name in ("checkerboard", "sine_grating", "noise")
        ],
        "texture_tile_mm": [40, 40],
        "usage": "Choose Image for images/*.png; choose Texture for textures/*.texture.json. Group repetitions repeat the full sequence.",
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
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
        required=True,
        help="External asset directory (outside this repository)",
    )
    args = parser.parse_args()
    print(f"Generated {generate(args.output)} local sample images in {args.output}.")
