"""Focused native property controls for the active design, with typed values."""

import json
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import (
    Card,
    button,
    combo,
    decimal_field,
    equal_row_height,
    field,
)
from cephvr.gui.theme import SIZES

CHOICES = {
    "alpha_mode": ["OPAQUE", "MASK"],
    "shape": ["rectangular", "circular", "torus", "two_choice", "cross"],
    "pattern": ["none", "rock", "ridges", "waves"],
    "origin_screen": ["front", "left", "right", "bottom"],
    "target_screen": ["front", "left", "right", "bottom"],
    "unit": ["s", "ms", "us", "ns"],
}


def property_form(
    data: dict[str, Any],
    changed: Callable[[], None],
    rebuild: Callable[[], None],
    *,
    title: str = "",
    directory: Path | None = None,
    hidden: frozenset[str] = frozenset(),
) -> QWidget:
    panel = Card(title) if title else QWidget()
    form = panel.body if isinstance(panel, Card) else QVBoxLayout(panel)
    form.setSpacing(SIZES.body_gap)
    grid = QGridLayout()
    grid.setHorizontalSpacing(SIZES.field_x_gap)
    grid.setVerticalSpacing(SIZES.body_gap)
    grid.setColumnStretch(0, 1)
    grid.setColumnStretch(1, 1)
    form.addLayout(grid)
    position = 0

    def add_control(widget: QWidget, *, wide: bool = True) -> None:
        nonlocal position
        if wide:
            position += position % 2
        grid.addWidget(
            widget,
            position // 2,
            position % 2,
            1,
            2 if wide else 1,
            Qt.AlignmentFlag.AlignTop,
        )
        position += 2 if wide else 1

    for key, value in sorted(
        data.items(),
        key=lambda item: (
            item[0] in {"color", "color_a", "color_b", "background_linear"}
        ),
    ):
        if key in hidden:
            continue
        if key in {
            "tile_local",
            "texture_resolution",
            "format_version",
            "kind",
            "cephvr_asset_type",
            "tile_height_mm",
            "tile_width_mm",
            "phase_cycles",
            "fit_cycles_to_tile",
            "tile_size_mm",
            "features_per_tile",
        }:
            continue
        label = (
            key.replace("_mm", " (mm)")
            .replace("_per_cm2", " (/cm²)")
            .replace("_deg", " (°)")
            .replace("_", " ")
            .capitalize()
        )
        if isinstance(value, dict):
            add_control(
                property_form(value, changed, rebuild, title=label, directory=directory)
            )
            continue
        if key == "scatters":
            group = Card("Objects")
            group.setProperty("nestedCard", True)
            rows = group.body
            for index, item in enumerate(value):
                rows.addWidget(
                    property_form(
                        item,
                        changed,
                        rebuild,
                        title=f"Layer {index + 1}",
                        directory=directory,
                    )
                )
                remove = button(f"Remove layer {index + 1}")

                def remove_layer(checked: bool = False, index: int = index) -> None:
                    del data["scatters"][index]
                    changed()
                    rebuild()

                remove.clicked.connect(remove_layer)
                rows.addWidget(remove)
            add = button("Add object layer")

            def add_layer() -> None:
                from .models import Scatter

                data["scatters"].append(Scatter(model="").model_dump())
                changed()
                rebuild()

            add.clicked.connect(add_layer)
            rows.addWidget(add)
            add_control(group)
            continue

        def set_value(new: Any, key: str = key) -> None:
            data[key] = new
            changed()

        control: QWidget
        if key in {"color", "color_a", "color_b"} and isinstance(value, (list, tuple)):
            row = QWidget()
            channels = QGridLayout(row)
            channels.setContentsMargins(0, 0, 0, 0)
            for index, channel in enumerate(value):
                spin = decimal_field(0)
                spin.setDecimals(3)
                spin.setRange(0, 1)
                spin.setSingleStep(0.05)
                spin.setPrefix("RGBA"[index] + " ")
                spin.setValue(channel)
                spin.setKeyboardTracking(False)

                def change_channel(
                    number: float, index: int = index, key: str = key
                ) -> None:
                    values = list(data[key])
                    values[index] = number
                    data[key] = values
                    changed()

                spin.valueChanged.connect(change_channel)
                spin.setMinimumWidth(0)
                channels.addWidget(spin, 0, index)
                channels.setColumnStretch(index, 1)
            control = row
        elif key in {"texture", "texture_path", "model"}:
            row = QWidget()
            paths = QHBoxLayout(row)
            paths.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit(str(value))
            browse = button("Browse…")
            edit.editingFinished.connect(
                lambda edit=edit, setter=set_value: setter(edit.text())
            )

            def browse_file(
                checked: bool = False,
                edit: QLineEdit = edit,
                setter: Callable[..., Any] = set_value,
                key: str = key,
            ) -> None:
                root = (directory or Path.cwd()).resolve()
                filters = (
                    "Static GLB (*.glb)"
                    if key == "model"
                    else "Images (*.png *.jpg *.jpeg *.tif *.tiff)"
                    if key == "texture_path"
                    else "Textures (*.json *.png *.jpg *.jpeg)"
                )
                filename, _ = QFileDialog.getOpenFileName(
                    panel, "Select asset", str(root), filters
                )
                if filename:
                    try:
                        relative = Path(filename).resolve().relative_to(root).as_posix()
                    except ValueError:
                        edit.setToolTip(
                            "Choose a file inside the asset/recipe directory"
                        )
                        edit.setStyleSheet("border: 1px solid #c44")
                        return
                    edit.setStyleSheet("")
                    edit.setText(relative)
                    setter(relative)

            browse.clicked.connect(browse_file)
            paths.addWidget(edit, 1)
            paths.addWidget(browse)
            equal_row_height(edit, browse)
            control = row
        elif isinstance(value, bool):
            box = QCheckBox()
            box.setChecked(value)
            box.toggled.connect(set_value)
            control = box
        elif key in CHOICES:
            selection = combo(tuple(CHOICES[key]))
            selection.setCurrentText(str(value))
            selection.currentTextChanged.connect(set_value)
            control = selection
        elif key == "seed":
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit(str(value))
            randomize = button("New seed")

            def seed_changed(
                edit: QLineEdit = edit, set_value: Callable[..., Any] = set_value
            ) -> None:
                try:
                    seed = int(edit.text())
                    if not 0 <= seed <= 2**64 - 1:
                        raise ValueError()
                except ValueError:
                    edit.setToolTip(
                        "Seed must be an integer from 0 to 18446744073709551615"
                    )
                    edit.setStyleSheet("border: 1px solid #c44")
                    set_value(edit.text())
                    return
                edit.setStyleSheet("")
                set_value(seed)

            edit.editingFinished.connect(seed_changed)

            def new_seed(
                checked: bool = False,
                edit: QLineEdit = edit,
                commit: Callable[..., Any] = seed_changed,
            ) -> None:
                edit.setText(str(secrets.randbits(64)))
                commit()

            randomize.clicked.connect(new_seed)
            layout.addWidget(edit)
            layout.addWidget(randomize)
            equal_row_height(edit, randomize)
            control = row
        elif isinstance(value, (int, float)):
            spin = decimal_field(0)
            integer = isinstance(value, int) and key not in (
                "active_probability",
                "min_active_cell_distance_mm",
            )
            spin.setDecimals(0 if integer else 3)
            spin.setRange(-1e9, 1e9)
            if key == "active_probability":
                spin.setRange(0, 1)
                spin.setSingleStep(0.05)
                spin.setToolTip(
                    "Independent activation probability per eligible cell and pattern (0–1)."
                )
            elif key == "min_active_cell_distance_mm":
                spin.setRange(0, 1e9)
                spin.setToolTip(
                    "Minimum center-to-center distance in mm. A new eligible layout is generated for each pattern; 0 allows all cells."
                )
            spin.setValue(value)
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(
                lambda v, setter=set_value, integer=integer: setter(
                    int(v) if integer else v
                )
            )
            control = spin
        else:
            edit = QLineEdit(
                json.dumps(value) if isinstance(value, (list, tuple)) else str(value)
            )

            def commit(
                edit: QLineEdit = edit,
                setter: Callable[..., Any] = set_value,
                array: bool = isinstance(value, (list, tuple)),
            ) -> None:
                try:
                    parsed = json.loads(edit.text()) if array else edit.text()
                    if array and not isinstance(parsed, list):
                        raise ValueError("Expected a JSON list")
                except (ValueError, json.JSONDecodeError):
                    edit.setStyleSheet("border: 1px solid #c44")
                    setter(edit.text())
                    return
                edit.setStyleSheet("")
                setter(parsed)

            edit.editingFinished.connect(commit)
            control = edit
            if isinstance(value, (list, tuple)):
                edit.setToolTip(
                    "Values in brackets; colors are linear channels from 0 to 1"
                )
        control.setObjectName(key)
        add_control(
            field(label, control),
            wide=key
            in {
                "color",
                "color_a",
                "color_b",
                "texture",
                "texture_path",
                "model",
                "seed",
            }
            or isinstance(value, (list, tuple)),
        )
    return panel
