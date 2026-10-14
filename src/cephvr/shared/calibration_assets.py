"""Fixed repository asset root for sessionless projector diagnostics (V01/G01)."""

import hashlib
import os
import tempfile
from pathlib import Path


def calibration_asset_root() -> Path:
    """Resolve the calibration bundle independently of Protocol Assets."""
    root = Path(__file__).resolve().parents[3] / "assets"
    if not (root / "calibration").is_dir():
        raise ValueError("Repository calibration assets are unavailable")
    return root.resolve(strict=True)


def calibration_runtime_root(view: str) -> Path:
    """Keep each step's generated mappings and protected copy in user runtime data."""
    if view not in ("reference_bars", "frame_grid"):
        raise ValueError("Unknown calibration step")
    repository = Path(__file__).resolve().parents[3]
    identity = hashlib.sha256(str(repository).casefold().encode()).hexdigest()[:16]
    local_data = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
    return local_data / "CephVR" / "calibration" / identity / view
