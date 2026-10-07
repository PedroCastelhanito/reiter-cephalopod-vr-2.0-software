"""Entry-point modules every managed launch needs, shared by launcher and supervisor."""

from __future__ import annotations

import importlib.util

REQUIRED_MODULES = {
    "acquisition": "cephvr.acquisition.main",
    "visual_stimulus": "cephvr.visual_stimulus.main",
    "tracking": "cephvr.tracking.main",
    "gui": "cephvr.gui.main",
}


def missing_roles() -> list[str]:
    """Roles whose entry-point module cannot be found; callers raise their own error."""
    missing = []
    for role, module in REQUIRED_MODULES.items():
        try:
            present = importlib.util.find_spec(module) is not None
        except ModuleNotFoundError:
            present = False
        if not present:
            missing.append(role)
    return missing
