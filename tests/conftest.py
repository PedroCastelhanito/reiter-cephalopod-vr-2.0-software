"""Shared generated assets for GUI authoring and Visual Stimulus decoding tests."""

from pathlib import Path
from runpy import run_path

import pytest


@pytest.fixture(scope="session")
def demo_assets(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("demo-assets")
    generator = run_path(
        str(Path(__file__).resolve().parents[1] / "tools/generate_demo_assets.py")
    )
    generator["generate"](output)
    return output
