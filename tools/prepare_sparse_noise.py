"""Prepare a sparse-noise recipe and calibrated display as a loadable program bundle."""

import argparse
import tomllib
from pathlib import Path

from cephvr.visual_stimulus.config.models.display_profile import parse_display_json
from cephvr.visual_stimulus.config.models.sparse_noise import parse_sparse_noise_json
from cephvr.visual_stimulus.resources.sparse_noise import prepare_sparse_noise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--display", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "config/backends/visual_stimulus_config.toml",
    )
    args = parser.parse_args()
    with args.config.open("rb") as source:
        limits = tomllib.load(source)["resources"]
    document_limit = limits["max_document_bytes"]
    if type(document_limit) is not int or document_limit <= 0:
        parser.error("max_document_bytes must be a positive integer")

    def read(path: Path) -> str:
        with path.open("rb") as source:
            data = source.read(document_limit + 1)
        if len(data) > document_limit:
            raise ValueError(f"document exceeds byte budget: {path}")
        return data.decode("utf-8")

    recipe = parse_sparse_noise_json(read(args.recipe), max_bytes=document_limit)
    display = parse_display_json(read(args.display), max_bytes=document_limit)
    path = prepare_sparse_noise(
        recipe,
        display,
        args.output,
        max_cells=limits["max_asset_cpu_bytes"] // 192,
        max_patterns=limits["max_expanded_epochs"],
        max_document_bytes=document_limit,
    )
    print(
        f"Prepared {path}. Use its directory as the asset root; normal Setup is required."
    )


if __name__ == "__main__":
    main()
