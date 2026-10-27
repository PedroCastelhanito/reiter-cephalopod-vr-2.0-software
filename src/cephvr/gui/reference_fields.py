"""Present existing family editors as reference-table cells, without copying values."""

from collections.abc import Iterable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from cephvr.gui.arena_movement import ArenaMovement
from cephvr.gui.components import equal_row_height, label
from cephvr.gui.epoch_motion import EpochMotion
from cephvr.gui.grating_appearance import GratingAppearance
from cephvr.gui.grating_motion import GratingMotion
from cephvr.gui.image_parameters import ImageParameters
from cephvr.gui.looming_size import LoomingSize
from cephvr.gui.motion_source import MotionSource
from cephvr.gui.sparse_noise_layer import CAPTIONS
from cephvr.gui.stimulus_columns import stimulus_columns
from cephvr.gui.stimulus_form import ValueEditor
from cephvr.gui.stimulus_parameters import StimulusParameters


def chain_tab_order(controls: Iterable[QWidget]) -> None:
    """Make Tab follow the on-screen order instead of widget creation order."""
    controls = list(controls)
    if not controls:
        return
    window = controls[0].window()
    focusable = [
        widget
        for control in controls
        for widget in (control, *control.findChildren(QWidget))
        # Skip popups (their own windows) and proxied sub-widgets such as spin editors.
        if widget.window() is window
        and widget.focusPolicy() & Qt.FocusPolicy.TabFocus
        and widget.focusProxy() is None
    ]
    for first, second in zip(focusable, focusable[1:], strict=False):
        QWidget.setTabOrder(first, second)


def beside(first: QWidget, second: QWidget, caption: str) -> QWidget:
    """One cell holding two controls side by side; the first takes the spare width."""
    first.setAccessibleName(caption)
    cell = QWidget()
    layout = QHBoxLayout(cell)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    layout.addWidget(first, 1)
    layout.addWidget(second)
    return cell


def reference_fields(editor: StimulusParameters) -> list[tuple[str, QWidget]]:
    """Move primary controls into cells; the original forms still read/validate them."""
    result: list[tuple[str, QWidget]] = []
    editor.more.hide()
    for i in range(editor.primary.count()):
        item = editor.primary.itemAt(i)
        if item is not None and (widget := item.widget()) is not None:
            widget.hide()
    for row in editor.file_rows:
        row.hide()
    if editor.asset_forms:
        asset = QWidget()
        layout = QHBoxLayout(asset)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        path = next(iter(editor.asset_forms.values()))
        browse = editor.file_rows[0].findChild(QPushButton)
        assert browse is not None
        browse.setText("…")
        browse.setToolTip("Choose asset")
        browse.setAccessibleName("Choose stimulus asset")
        equal_row_height(path, browse)
        browse.setFixedWidth(browse.height())
        layout.addWidget(path, 1)
        layout.addWidget(browse)
        result.append(("Asset", asset))
    else:
        result.append(("Asset", label("—")))
    arena = next((f for f in editor.forms if isinstance(f, ArenaMovement)), None)
    looming = next((f for f in editor.forms if isinstance(f, LoomingSize)), None)
    motion = next((f for f in editor.forms if isinstance(f, EpochMotion)), None)
    image = next((f for f in editor.forms if isinstance(f, ImageParameters)), None)
    playback = next(
        (
            f
            for f in editor.forms
            if isinstance(f, ValueEditor) and "initial_playback" in f.children_by_key
        ),
        None,
    )
    color = next(
        (
            f
            for f in editor.forms
            if isinstance(f, ValueEditor) and "mean_linear_rgb" in f.children_by_key
        ),
        None,
    )
    if editor.sparse_layer is not None:
        sparse = editor.sparse_layer
        sparse.form.hide()
        result = [
            (caption, sparse.form.children_by_key[key])
            for key, caption in CAPTIONS.items()
        ]
        # Keep the seed's "New seed" inline with its cell.
        for index, (caption, control) in enumerate(result):
            if caption == "Seed":
                result[index] = (caption, beside(control, sparse.new_seed, caption))
        for caption, control in result:
            control.setAccessibleName(caption)
            editor.external_controls.append(control)
        return result
    if color is not None:
        color_control = color.children_by_key["mean_linear_rgb"]
        editor.external_controls.append(color_control)
        return [("Color (linear RGB)", color_control)]
    grating = next((f for f in editor.forms if isinstance(f, GratingMotion)), None)
    if grating is not None:
        appearance = next(
            (form for form in editor.forms if isinstance(form, GratingAppearance)), None
        )
        if appearance is not None:
            result = [
                ("Spatial period (mm)", appearance.period),
                ("Sharpness (0–1)", appearance.sharpness),
                ("Color A (linear RGB)", appearance.color_a),
                ("Color B (linear RGB)", appearance.color_b),
            ]
        result.extend(
            (("Orientation (°)", grating.orientation), ("Speed (mm/s)", grating.speed))
        )
    elif image is not None:
        result.extend(
            (
                ("Fit", image.fit),
                ("Move speed", image.motion.speed),
                ("Direction", image.motion.direction),
            )
        )
        for image_control in (
            image.motion.speed,
            image.motion.direction,
            image.motion.angular,
        ):
            image_control.setEnabled(not image.motion.custom.isChecked())
        image.motion.custom.toggled.connect(image.update_controls)
        image.update_controls()
    elif arena is not None:
        if editor.tracking_available:
            result.extend(arena.cells)
    elif looming is not None:
        unit = "mm" if "mm" in editor.units.text() else "°"
        result.extend(
            (
                (f"Start ({unit})", looming.start),
                (f"End ({unit})", looming.end),
                ("Growth (s)", looming.duration),
            )
        )
        for _, control in result[1:]:
            control.setEnabled(not looming.custom.isChecked())
            looming.custom.toggled.connect(control.setDisabled)
    elif playback is not None:
        seconds = playback.children_by_key["initial_playback"].children_by_key[
            "seconds"
        ]
        result.extend(
            (
                ("Start (s)", seconds),
                ("At end", playback.children_by_key["end_behavior"]),
                ("", label("")),
            )
        )
    elif motion is not None:
        unit = "mm/s" if "mm" in editor.units.text() else "°/s"
        # Hide the old angular field wrapper after moving its editor into the row.
        parent = motion.angular.parentWidget()
        if parent is not None:
            parent.hide()
        result.extend(
            (
                (f"Speed ({unit})", motion.speed),
                ("Direction (°)", motion.direction),
                ("Rotation (°/s)", motion.angular),
            )
        )
        for _, control in result[1:]:
            control.setEnabled(
                not motion.custom.isChecked() and editor.linked_to.currentData() is None
            )
        motion.custom.toggled.connect(editor.update_link_controls)
    else:
        result.extend(("", label("—")) for _ in range(3))
    program = editor.program
    if program is not None and editor.layer_index >= 0:
        from cephvr.gui.program_editing import node_at
        from cephvr.visual_stimulus.config.models.program_model import Epoch

        node = node_at(program, editor.node_index)
        assert isinstance(node, Epoch)
        captions = (
            ()
            if grating is not None
            else stimulus_columns(node.settings[editor.layer_index])
        )
        result = [
            result[0],
            *[
                (captions[i][0] if i < len(captions) else title, control)
                for i, (title, control) in enumerate(result[1:])
            ],
        ]
    if (
        (motion is not None or grating is not None)
        and editor.fades is not None
        # Binding during a session lock must not hide a supported control on unlock.
        and editor.linked_to.isEnabledTo(editor)
        and program is not None
    ):
        editor.motion_source = MotionSource(editor.linked_to)
        editor.motion_source.currentIndexChanged.connect(editor.mark_changed)
        result[1:1] = [
            ("Motion source", editor.motion_source),
            ("Linked to", editor.linked_to),
        ]
    for title, control in result:
        control.setMinimumWidth(0)
        if title != "Asset":
            control.setAccessibleName(title)
            control.setToolTip(control.toolTip() or title or "No stimulus")
        editor.external_controls.append(control)
    return result
