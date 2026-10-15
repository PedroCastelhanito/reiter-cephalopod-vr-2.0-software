"""Fixed repository asset root for sessionless projector diagnostics (V01/G01)."""

import hashlib
import os
import tempfile
from pathlib import Path

CALIBRATION_VIEWS = frozenset(
    {"reference_bars", "frame_grid", "photodiode_placement", "blackout_placement"}
)
CALIBRATION_REFERENCES = frozenset(
    f"calibration/{view}.glb" for view in CALIBRATION_VIEWS
)


def calibration_asset_root() -> Path:
    """Resolve the calibration bundle independently of Protocol Assets."""
    root = Path(__file__).resolve().parents[3] / "assets"
    if not (root / "calibration").is_dir():
        raise ValueError("Repository calibration assets are unavailable")
    return root.resolve(strict=True)


def calibration_runtime_root(view: str) -> Path:
    """Keep each step's generated mappings and protected copy in user runtime data."""
    if view not in CALIBRATION_VIEWS:
        raise ValueError("Unknown calibration step")
    repository = Path(__file__).resolve().parents[3]
    identity = hashlib.sha256(str(repository).casefold().encode()).hexdigest()[:16]
    local_data = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
    return local_data / "CephVR" / "calibration" / identity / view
