"""Present existing family editors as reference-table cells, without copying values."""

from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from cephvr.gui.arena_movement import ArenaMovement
from cephvr.gui.components import equal_row_height, label
from cephvr.gui.epoch_motion import EpochMotion
from cephvr.gui.looming_size import LoomingSize
from cephvr.gui.stimulus_form import ValueEditor
from cephvr.gui.stimulus_parameters import StimulusParameters


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
    playback = next(
        (
            f
            for f in editor.forms
            if isinstance(f, ValueEditor) and "initial_playback" in f.children_by_key
        ),
        None,
    )
    if arena is not None:
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
            control.setEnabled(not motion.custom.isChecked())
            motion.custom.toggled.connect(control.setDisabled)
    else:
        result.extend(("", label("—")) for _ in range(3))
    for title, control in result:
        control.setMinimumWidth(0)
        if title != "Asset":
            control.setAccessibleName(title)
            control.setToolTip(title or "No stimulus")
        editor.external_controls.append(control)
    return result
