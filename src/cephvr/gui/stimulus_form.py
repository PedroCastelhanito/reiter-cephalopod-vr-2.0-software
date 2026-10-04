"""Small schema-driven controls for canonical stimulus values, without JSON editing."""

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import button, combo, label

TITLES = {
    "asset_id": "Asset",
    "logical_path": "Stimulus file",
    "initial": "Initial position",
    "space": "Coordinate space / screens",
    "initial_phase_x_cycles": "Initial X phase (cycles)",
    "initial_phase_y_cycles": "Initial Y phase (cycles)",
    "phase_x": "X phase motion (cycles)",
    "phase_y": "Y phase motion (cycles)",
    "mean_linear_rgb": "Mean RGB (linear)",
    "modulation_linear_rgb": "Modulation RGB (linear)",
    "slope_per_s": "Slope / second",
    "frequency_hz": "Frequency (Hz)",
    "phase_cycles": "Phase (cycles)",
    "frame_to_rig_xyzw": "Frame rotation (quaternion XYZW)",
    "asset_to_world": "Asset → world transform",
    "fixed_height_mm": "Observer height (mm)",
    "fixed_pitch_deg": "Pitch (°)",
    "fixed_roll_deg": "Roll (°)",
    "position_mm": "Position XY (mm)",
    "yaw_deg": "Yaw (°)",
    "rotation_deg": "Rotation (°)",
    "initial_playback": "Initial playback (s)",
    "reset": "Reset retained state",
}


def title(key: str) -> str:
    return TITLES.get(key, key.replace("_", " ").capitalize())


def resolve(schema: dict[str, Any], definitions: dict[str, Any]) -> dict[str, Any]:
    return definitions[schema["$ref"].split("/")[-1]] if "$ref" in schema else schema


def initial_value(schema: dict[str, Any], definitions: dict[str, Any]) -> Any:
    schema = resolve(schema, definitions)
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    if "anyOf" in schema or "oneOf" in schema:
        return initial_value(
            (schema["anyOf"] if "anyOf" in schema else schema["oneOf"])[0], definitions
        )
    kind = schema.get("type")
    if kind == "object":
        return {
            key: initial_value(value, definitions)
            for key, value in schema["properties"].items()
        }
    if kind == "array":
        if "prefixItems" in schema:
            return [initial_value(item, definitions) for item in schema["prefixItems"]]
        return [
            initial_value(schema["items"], definitions)
            for _ in range(schema.get("minItems", 0))
        ]
    return {
        "number": 0.0,
        "integer": 1,
        "boolean": False,
        "string": "",
        "null": None,
    }.get(str(kind))


class ValueEditor(QWidget):
    """Read a candidate value; the owning model validates before any commit."""

    changed = pyqtSignal()

    def __init__(
        self, schema: dict[str, Any], value: Any, definitions: dict[str, Any]
    ) -> None:
        super().__init__()
        self.schema = resolve(schema, definitions)
        self.definitions = definitions
        self.read: Callable[[], Any]
        self.children_by_key: dict[str, ValueEditor] = {}
        self.control: QWidget | None = None
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(8)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.build(value)
        if isinstance(self.control, QLineEdit):
            self.control.textEdited.connect(self.changed)
        elif isinstance(self.control, QCheckBox):
            self.control.toggled.connect(self.changed)
        elif self.control is not None:
            self.control.currentIndexChanged.connect(self.changed)

    def build(self, value: Any) -> None:
        schema = self.schema
        if "anyOf" in schema or "oneOf" in schema:
            self.build_union(value)
        elif "const" in schema:
            self.read = lambda: schema["const"]
        elif "enum" in schema:
            control = combo(tuple(title(str(item)) for item in schema["enum"]))
            for index, item in enumerate(schema["enum"]):
                control.setItemData(index, item)
            control.setCurrentIndex(schema["enum"].index(value))
            self.control = control
            self.body.addWidget(control)
            self.read = control.currentData
        elif schema.get("type") == "object":
            form = QFormLayout()
            form.setFieldGrowthPolicy(
                QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
            )
            form.setSpacing(10)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            self.body.addLayout(form)
            for key, prop in schema["properties"].items():
                child = ValueEditor(prop, value.get(key), self.definitions)
                self.children_by_key[key] = child
                child.changed.connect(self.changed)
                if "const" not in resolve(prop, self.definitions):
                    if key == "value" and len(schema["properties"]) <= 2:
                        form.addRow(child)
                    else:
                        form.addRow(label(title(key), "label"), child)
            self.read = lambda: {
                key: child.read() for key, child in self.children_by_key.items()
            }
        elif schema.get("type") == "array":
            self.build_array(value)
        elif schema.get("type") == "boolean":
            toggle = QCheckBox()
            toggle.setChecked(value)
            self.control = toggle
            self.body.addWidget(toggle)
            self.read = toggle.isChecked
        elif schema.get("type") == "null":
            self.body.addWidget(label("None"))
            self.read = lambda: None
        else:
            editor = QLineEdit(str(value))
            editor.setMinimumWidth(0)
            self.control = editor
            self.body.addWidget(editor)
            kind = schema.get("type")
            self.read = lambda: (
                float(editor.text())
                if kind == "number"
                else int(editor.text())
                if kind == "integer"
                else editor.text()
            )

    def build_union(self, value: Any) -> None:
        variants = (
            self.schema["anyOf"] if "anyOf" in self.schema else self.schema["oneOf"]
        )
        schemas = [resolve(item, self.definitions) for item in variants]
        names = []
        selected = 0
        for index, schema in enumerate(schemas):
            tag = schema.get("properties", {}).get("kind", {}).get("const")
            names.append(title(tag or schema.get("title", schema.get("type", "Value"))))
            properties = schema.get("properties", {})
            matches_object = (
                isinstance(value, dict)
                and schema.get("type") == "object"
                and all(
                    ("const" not in prop or value.get(key) == prop["const"])
                    and ("enum" not in prop or value.get(key) in prop["enum"])
                    for key, prop in properties.items()
                )
            )
            primitive = (
                "null"
                if value is None
                else "string"
                if isinstance(value, str)
                else "number"
            )
            if matches_object or (
                not isinstance(value, dict) and schema.get("type") == primitive
            ):
                selected = index
        picker = combo(tuple(names))
        picker.setCurrentIndex(selected)
        self.control = picker
        compact = any(
            schema.get("type") in ("number", "string") for schema in schemas
        ) or any(
            schema.get("properties", {}).get("kind", {}).get("const") == "constant"
            for schema in schemas
        )
        variant_layout: QBoxLayout = self.body
        if compact:
            row = QHBoxLayout()
            self.body.addLayout(row)
            variant_layout = row
            if any(schema.get("type") in ("number", "string") for schema in schemas):
                picker.hide()
                more = button("…", hint="Use a literal value or a condition reference")
                more.setFixedWidth(30)
                menu = QMenu(more)
                for index, name in enumerate(names):
                    action = menu.addAction(name)
                    assert action is not None
                    action.triggered.connect(
                        lambda checked=False, i=index: picker.setCurrentIndex(i)
                    )
                more.setMenu(menu)
                row.addWidget(more)
            else:
                picker.setMaximumWidth(115)
                row.addWidget(picker)
        else:
            self.body.addWidget(picker)
        self.variant = ValueEditor(schemas[selected], value, self.definitions)
        self.variant.changed.connect(self.changed)
        variant_layout.addWidget(self.variant)
        cache = {selected: value}
        current = [selected]

        def choose(index: int) -> None:
            try:
                cache[current[0]] = self.variant.read()
            except ValueError:
                pass
            variant_layout.removeWidget(self.variant)
            self.variant.deleteLater()
            self.variant = ValueEditor(
                schemas[index],
                cache.get(index, initial_value(schemas[index], self.definitions)),
                self.definitions,
            )
            self.variant.changed.connect(self.changed)
            variant_layout.addWidget(self.variant)
            current[0] = index

        picker.currentIndexChanged.connect(choose)
        self.read = lambda: self.variant.read()

    def build_array(self, value: list[Any]) -> None:
        fixed = self.schema.get("prefixItems")
        entries: list[ValueEditor] = []
        rows = QVBoxLayout()
        self.body.addLayout(rows)

        def add(item: Any, index: int) -> None:
            child = ValueEditor(
                fixed[index] if fixed else self.schema["items"], item, self.definitions
            )
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(child, 1)
            entries.append(child)
            child.changed.connect(self.changed)
            if not fixed:
                remove = button("−", hint="Remove entry")
                remove.setFixedWidth(32)
                layout.addWidget(remove)

                def discard() -> None:
                    entries.remove(child)
                    rows.removeWidget(row)
                    row.deleteLater()
                    self.changed.emit()

                remove.clicked.connect(discard)
            rows.addWidget(row)
            self.changed.emit()

        for index, item in enumerate(value):
            add(item, index)
        if not fixed:
            plus = button("Add entry")
            plus.clicked.connect(
                lambda: add(
                    initial_value(self.schema["items"], self.definitions), len(entries)
                )
            )
            self.body.addWidget(plus)
        self.read = lambda: [entry.read() for entry in entries]
