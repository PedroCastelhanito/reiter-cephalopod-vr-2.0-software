"""Entry-point modules every managed launch needs, shared by launcher and supervisor."""

from __future__ import annotations

import importlib.util
from collections.abc import Mapping

REQUIRED_MODULES = {
    "acquisition": "cephvr.acquisition.main",
    "visual_stimulus": "cephvr.visual_stimulus.main",
    "tracking": "cephvr.tracking.main",
    "gui": "cephvr.gui.startup",
}


def no_tracking_from_bootstrap(document: Mapping[str, object]) -> bool:
    """Only an explicit protected boolean permits omitting the Tracking process."""
    value = document.get("no_tracking", False)
    if type(value) is not bool:
        raise ValueError("bootstrap no_tracking must be a boolean")
    return value


def managed_modules(*, no_tracking: bool = False) -> dict[str, str]:
    """The two supported process sets; camera roles are independent of these roles."""
    return {
        role: module
        for role, module in REQUIRED_MODULES.items()
        if not (no_tracking and role == "tracking")
    }


def missing_roles(*, no_tracking: bool = False) -> list[str]:
    """Roles whose entry-point module cannot be found; callers raise their own error."""
    missing = []
    for role, module in managed_modules(no_tracking=no_tracking).items():
        try:
            present = importlib.util.find_spec(module) is not None
        except ModuleNotFoundError:
            present = False
        if not present:
            missing.append(role)
    return missing
