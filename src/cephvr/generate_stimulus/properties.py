"""Focused native property controls for the active design, with typed values."""

import json
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any, get_args

from pydantic import BaseModel
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
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
    label,
)
from cephvr.gui.theme import SIZES
from cephvr.visual_stimulus.config.models.schema_common import SurfaceId

from .fields import ARRAY_HINT, HINTS, humanize, label_for, number_spec, submodel
from .markers import clear_field, mark_field

FACES = get_args(SurfaceId)
CHOICES = {
    "alpha_mode": ["OPAQUE", "MASK"],
    "shape": ["rectangular", "circular", "torus", "two_choice", "cross"],
    "pattern": ["none", "rock", "ridges", "waves"],
    "origin_screen": list(FACES),
    "target_screen": list(FACES),
    "unit": ["s", "ms", "us", "ns"],
}
COLORS = {"color", "color_a", "color_b"}
HIDDEN = {
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
}
WIDE = COLORS | {"texture", "texture_path", "model", "seed"}


def flush_edits(root: QWidget | None) -> None:
    """Commit text that is still being typed, as if focus had left each control."""
    if root is None:
        return
    for spin in root.findChildren(QAbstractSpinBox):
        spin.interpretText()
    for edit in root.findChildren(QLineEdit):
        if edit.isModified() and not isinstance(edit.parentWidget(), QAbstractSpinBox):
            edit.editingFinished.emit()


def _on_finished(edit: QLineEdit, commit: Callable[[], None]) -> None:
    def finished() -> None:
        edit.setModified(False)
        commit()

    edit.editingFinished.connect(finished)


def property_form(
    data: dict[str, Any],
    changed: Callable[[], None],
    rebuild: Callable[[], None],
    *,
    title: str = "",
    directory: Path | None = None,
    hidden: frozenset[str] = frozenset(),
    schema: type[BaseModel] | None = None,
    path: str = "",
) -> QWidget:
    """Controls for `data`; `schema` supplies limits and `path` locates error marks."""
    panel = Card(title) if title else QWidget()
    form = panel.body if isinstance(panel, Card) else QVBoxLayout(panel)
    form.setSpacing(SIZES.body_gap)
    panel.setProperty("formPath", path)
    banner = label("", "error", wrap=True)
    banner.setObjectName("FormError")
    banner.hide()
    form.addWidget(banner)
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
        data.items(), key=lambda item: item[0] in COLORS | {"background_linear"}
    ):
        if key in hidden or key in HIDDEN:
            continue
        name = label_for(key)
        child_path = f"{path}.{key}" if path else key
        if isinstance(value, dict):
            add_control(
                property_form(
                    value,
                    changed,
                    rebuild,
                    title=name,
                    directory=directory,
                    schema=submodel(schema, key),
                    path=child_path,
                )
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
                        schema=submodel(schema, key),
                        path=f"{child_path}.{index}",
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
        hint = HINTS.get(key, "")
        if key in COLORS and isinstance(value, (list, tuple)):
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
                spin.setAccessibleName(f"{name} {'RGBA'[index]}")

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
            edit.setAccessibleName(name)
            browse = button("Browse…")

            def commit_path(edit: QLineEdit = edit, setter: Any = set_value) -> None:
                setter(edit.text())

            _on_finished(edit, commit_path)

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
                        mark_field(
                            edit, "Choose a file inside the asset/recipe directory"
                        )
                        return
                    clear_field(edit)
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
            box.setAccessibleName(name)
            box.toggled.connect(set_value)
            control = box
        elif key in CHOICES:
            selection = combo(tuple(humanize(choice) for choice in CHOICES[key]))
            for row_index, choice in enumerate(CHOICES[key]):
                selection.setItemData(row_index, choice)
            selection.setCurrentIndex(max(0, selection.findData(str(value))))
            selection.setAccessibleName(name)
            selection.currentIndexChanged.connect(
                lambda index, box=selection, setter=set_value: setter(
                    box.itemData(index)
                )
            )
            control = selection
        elif key == "seed":
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit(str(value))
            edit.setAccessibleName(name)
            randomize = button("New seed")

            def seed_changed(
                edit: QLineEdit = edit, set_value: Callable[..., Any] = set_value
            ) -> None:
                try:
                    seed = int(edit.text())
                    if not 0 <= seed <= 2**64 - 1:
                        raise ValueError()
                except ValueError:
                    mark_field(
                        edit, "Seed must be an integer from 0 to 18446744073709551615"
                    )
                    set_value(edit.text())
                    return
                clear_field(edit)
                set_value(seed)

            _on_finished(edit, seed_changed)

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
            spec = number_spec(schema, key, value)
            spin = decimal_field(0)
            spin.setDecimals(spec.decimals)
            spin.setRange(spec.minimum, spec.maximum)
            spin.setSingleStep(spec.step)
            spin.setValue(value)
            spin.setKeyboardTracking(False)
            spin.setAccessibleName(name)
            spin.valueChanged.connect(
                lambda v, setter=set_value, integer=spec.integer: setter(
                    int(v) if integer else v
                )
            )
            control = spin
        else:
            edit = QLineEdit(
                json.dumps(value) if isinstance(value, (list, tuple)) else str(value)
            )
            edit.setAccessibleName(name)
            array = isinstance(value, (list, tuple))

            def commit(
                edit: QLineEdit = edit,
                setter: Callable[..., Any] = set_value,
                array: bool = array,
            ) -> None:
                try:
                    parsed = json.loads(edit.text()) if array else edit.text()
                    if array and not isinstance(parsed, list):
                        raise ValueError("Expected a JSON list")
                except (ValueError, json.JSONDecodeError):
                    mark_field(edit, "Enter a JSON list, for example [0, 1]")
                    setter(edit.text())
                    return
                clear_field(edit)
                setter(parsed)

            _on_finished(edit, commit)
            control = edit
            hint = ARRAY_HINT if array else hint
        control.setObjectName(key)
        wrapped = field(name, control, hint=hint)
        wrapped.setProperty("fieldPath", child_path)
        note = label("", "error", wrap=True)
        note.setObjectName("FieldError")
        note.hide()
        layout_of_field = wrapped.layout()
        assert layout_of_field is not None
        layout_of_field.addWidget(note)
        add_control(wrapped, wide=key in WIDE or isinstance(value, (list, tuple)))
    return panel
