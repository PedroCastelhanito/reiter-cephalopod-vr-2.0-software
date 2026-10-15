"""Placement preview actions, live drafts and focused control gating."""

from typing import TYPE_CHECKING, Literal, cast

from cephvr.gui.projector_geometry import FACES
from cephvr.visual_stimulus.config.calibration_placement import (
    PLACEMENT_VIEWS,
    CalibrationPlacement,
    PlacementOutput,
)
from cephvr.visual_stimulus.config.models.display_profile import (
    PhotodiodePatch,
    PixelRect,
)

if TYPE_CHECKING:
    from cephvr.gui.projectors import ProjectorsPanel


def initial_photodiode_patch(panel: "ProjectorsPanel") -> dict[str, object] | None:
    """Start black until the draft defines a complete in-bounds pulse."""
    try:
        placement = placement_snapshot(panel, "photodiode_placement")
    except (ValueError, TypeError, KeyError):
        return None
    assert placement.photodiode_patch is not None
    return placement.photodiode_patch.model_dump(include={"rect", "background_rect"})


def request_placement(panel: "ProjectorsPanel", view: str) -> None:
    state = panel.calibration
    if (
        not panel.can_review
        or not state.presentation_available
        or state.presentation_pending
    ):
        return
    if state.presentation_active:
        if state.presentation_view == view:
            panel.calibration_close_requested.emit()
        return
    path = panel.prepare_calibration(
        view=cast(Literal["photodiode_placement", "blackout_placement"], view)
    )
    if path is not None:
        panel.calibration_launch_requested.emit(str(path))


def refresh_placement_controls(panel: "ProjectorsPanel", *, editable: bool) -> None:
    state = panel.calibration
    live = (
        panel.can_review
        and state.presentation_active
        and not state.presentation_pending
        and panel.live_tuning_available
    )
    view = state.presentation_view
    placement = live and view in PLACEMENT_VIEWS
    timing = panel.timing
    timing.setEnabled(editable or placement)
    timing.mode.setEnabled(editable)
    timing.pulse.setEnabled(editable)
    timing.options.setEnabled(
        (editable and timing.pulse.isChecked())
        or (live and view == "photodiode_placement")
    )
    timing.blackouts.setEnabled(editable or (live and view == "blackout_placement"))
    for button, selected, title in (
        (
            timing.placement_button,
            "photodiode_placement",
            "Launch photodiode placement",
        ),
        (
            timing.blackouts.placement_button,
            "blackout_placement",
            "Launch blackout placement",
        ),
    ):
        # Keep Close accessible while restricting unrelated fields/diagnostic launches.
        parent = button.parentWidget()
        assert parent is not None
        parent.setEnabled(editable or (state.presentation_active and view == selected))
        button.setText(
            "Close" if state.presentation_active and view == selected else title
        )
        button.setEnabled(
            panel.can_review
            and state.presentation_available
            and not state.presentation_pending
            and (not state.presentation_active or view == selected)
        )
    timing.blackouts.table.setEnabled(
        editable or (live and view == "blackout_placement")
    )
    timing.blackouts.add_button.setEnabled(
        editable or (live and view == "blackout_placement")
    )


def placement_snapshot(panel: "ProjectorsPanel", view: str) -> CalibrationPlacement:
    zones: dict[str, list[PixelRect]] = {face: [] for face in FACES}
    if view == "blackout_placement":
        for zone in panel.timing.blackouts.snapshot():
            zones[zone["face"]].append(
                PixelRect.model_validate(
                    {key: zone[key] for key in ("x", "y", "width", "height")}
                )
            )
    face = panel.pulse_face() if view == "photodiode_placement" else None
    patch = panel.timing.patch_draft() if face is not None else None
    if view == "photodiode_placement" and (face is None or patch is None):
        raise ValueError("Select a display and complete the pulse rectangle")
    result = CalibrationPlacement(
        outputs=tuple(
            PlacementOutput(
                output_id=f"calibration_{face.lower()}",
                blackout_zones=tuple(zones[face]),
            )
            for face in FACES
        ),
        photodiode_output_id=f"calibration_{face.lower()}"
        if face is not None
        else None,
        photodiode_patch=PhotodiodePatch.model_validate(
            dict(**patch, high_linear_rgb=(1, 1, 1), low_linear_rgb=(0, 0, 0))
        )
        if patch is not None
        else None,
    )

    resolutions = {
        f"calibration_{panel.assignments[key].lower()}": size
        for key, size in panel.display_pixels.items()
        if panel.assignments.get(key) in FACES
    }
    for output in result.outputs:
        width, height = resolutions[output.output_id]
        rects = list(output.blackout_zones)
        if output.output_id == result.photodiode_output_id:
            assert result.photodiode_patch is not None
            rects.append(result.photodiode_patch.rect)
            if result.photodiode_patch.background_rect is not None:
                rects.append(result.photodiode_patch.background_rect)
        if any(
            rect.x + rect.width > width or rect.y + rect.height > height
            for rect in rects
        ):
            raise ValueError("Placement exceeds the assigned output")
    return result
