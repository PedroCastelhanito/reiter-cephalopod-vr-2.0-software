"""Pure helpers for the projector panel's calibration launch and edge hints."""

from collections.abc import Mapping, Sequence

from cephvr.gui.calibration_profile import (
    AssignedDisplay,
    MonitorBinding,
    automatic_margins,
)
from cephvr.gui.projector_geometry import FACES


def assigned_displays(
    keys: Sequence[str],
    rectangles: Sequence[tuple[int, int, int, int]],
    pixels: Mapping[str, tuple[int, int]],
    assignments: Mapping[str, str],
    participation: Mapping[str, bool],
    native_interfaces: frozenset[str],
) -> tuple[AssignedDisplay, ...]:
    """One launch row per discovered display.

    Desktop rectangles are Qt logical units, so physical pixels replace their size and
    the native interface (when the key is one) is the binding identity.
    """
    return tuple(
        AssignedDisplay(
            assignments.get(key, "Unassigned"),
            x,
            y,
            *pixels.get(key, (width, height)),
            participation.get(key, True),
            interface=key if key in native_interfaces else "",
        )
        for key, (x, y, width, height) in zip(keys, rectangles, strict=True)
    )


def margin_hints(
    calibration: dict[str, object] | None, pixels: Mapping[str, tuple[int, int]]
) -> dict[str, tuple[float | None, ...]]:
    """Automatic (left, right, top, bottom) margins per face; None when unknown."""
    hints: dict[str, tuple[float | None, ...]] = {}
    for face in FACES:
        hints[face] = (None,) * 4
        if calibration is None or face not in pixels:
            continue
        width, height = pixels[face]
        try:
            automatic = automatic_margins(
                calibration, face, MonitorBinding("", 0, 0, width, height, 0, 0)
            )
        except ValueError:
            automatic = None
        if automatic is not None:
            hints[face] = automatic
    return hints
