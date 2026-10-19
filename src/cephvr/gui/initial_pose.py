"""Existing stimulus initial-pose fields presented in Advanced settings."""

from typing import Any

from PyQt6.QtWidgets import QLineEdit, QWidget

from cephvr.gui.components import field, label
from cephvr.gui.layouts import advanced_grid
from cephvr.gui.stimulus_form import ValueEditor


class PoseNumber(ValueEditor):
    """Plain numeric input; preserve imported condition references without flattening."""

    def build(self, value: Any) -> None:
        saved_reference = isinstance(value, dict)
        control = QLineEdit("" if saved_reference else str(value))
        control.setMinimumWidth(0)
        if saved_reference:
            control.setReadOnly(True)
            control.setPlaceholderText("Saved condition value")
            control.setToolTip("This imported field uses a saved condition reference")
        self.control = control
        self.body.addWidget(control)
        self.read = lambda: value if saved_reference else float(control.text())


class ArenaPose(ValueEditor):
    """Present the planar pose plus fixed height/pitch/roll as aligned XYZ/Euler fields."""

    def build(self, values: Any) -> None:
        grid = advanced_grid()
        self.body.addLayout(grid)
        grid.addWidget(label("Initial position (mm)", "label"), 0, 0)
        grid.addWidget(label("Orientation (°)", "label"), 0, 1)
        self.position_fields: list[QWidget] = []
        self.orientation_fields: list[QWidget] = []
        for row, entries in enumerate(
            (
                (
                    ("x", "X", values["initial"]["position_mm"][0]),
                    ("yaw_deg", "Yaw", values["initial"]["yaw_deg"]),
                ),
                (
                    ("y", "Y", values["initial"]["position_mm"][1]),
                    (
                        "fixed_pitch_deg",
                        "Pitch",
                        values["fixed_pitch_deg"],
                    ),
                ),
                (
                    (
                        "fixed_height_mm",
                        "Z",
                        values["fixed_height_mm"],
                    ),
                    (
                        "fixed_roll_deg",
                        "Roll",
                        values["fixed_roll_deg"],
                    ),
                ),
            ),
            start=1,
        ):
            for column, (key, caption, value) in enumerate(entries):
                child = PoseNumber({"type": "number"}, value, self.definitions)
                child.setAccessibleName(f"Initial {caption}")
                child.changed.connect(self.changed)
                self.children_by_key[key] = child
                widget = field(caption, child)
                (
                    self.position_fields if column == 0 else self.orientation_fields
                ).append(widget)
                grid.addWidget(widget, row, column)
        self.read = lambda: {
            "initial": {
                "position_mm": [self.children_by_key[key].read() for key in ("x", "y")],
                "yaw_deg": self.children_by_key["yaw_deg"].read(),
            },
            **{
                key: self.children_by_key[key].read()
                for key in ("fixed_height_mm", "fixed_pitch_deg", "fixed_roll_deg")
            },
        }


def initial_pose_fields(
    values: dict[str, Any], schema: dict[str, Any], definitions: dict[str, Any]
) -> tuple[ValueEditor, QWidget]:
    keys = ["initial"]
    if values["kind"] == "arena":
        keys += ["fixed_height_mm", "fixed_pitch_deg", "fixed_roll_deg"]
    editor_type = ArenaPose if values["kind"] == "arena" else ValueEditor
    editor = editor_type(
        {
            "type": "object",
            "properties": {key: schema["properties"][key] for key in keys},
        },
        {key: values[key] for key in keys},
        definitions,
    )
    # Nested array/object forms must retain enough height inside compact cards.
    editor.setMinimumHeight(editor.minimumSizeHint().height())
    return (
        editor,
        editor
        if values["kind"] == "arena"
        else field("Initial position / orientation", editor),
    )
