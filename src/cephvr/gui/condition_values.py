"""Compact condition lists, recovering physical motion controls from canonical refs."""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFormLayout, QLineEdit, QVBoxLayout, QWidget

from cephvr.gui.components import label
from cephvr.gui.protocol_groups import motion_numbers, varied_fields
from cephvr.visual_stimulus.config.models.program_model import Group


@dataclass
class MotionTarget:
    name: str
    setting: dict[str, Any]
    columns: dict[tuple[str, ...], str]
    parameters: list[str]


def substitute(value: Any, group: str, cells: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        if value.get("kind") == "condition" and value.get("group_id") == group:
            return cells[value["column_id"]]
        return {key: substitute(item, group, cells) for key, item in value.items()}
    if isinstance(value, list):
        return [substitute(item, group, cells) for item in value]
    return value


def semantic_targets(group: Group) -> list[MotionTarget]:
    """Recognize constant motion/size bindings without adding authoring metadata."""
    assert group.conditions is not None
    targets: list[MotionTarget] = []
    used: list[str] = []

    def walk(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            if node["kind"] == "group":
                walk(node["body"])
                continue
            for setting in node["settings"]:
                columns: dict[tuple[str, ...], str] = {}

                def refs(
                    value: Any,
                    path: tuple[str, ...] = (),
                    found: dict[tuple[str, ...], str] = columns,
                ) -> None:
                    if isinstance(value, dict):
                        if (
                            value.get("kind") == "condition"
                            and value.get("group_id") == group.group_id
                        ):
                            found[path] = value["column_id"]
                        else:
                            for key, item in value.items():
                                refs(item, path + (key,))
                    elif isinstance(value, list):
                        for i, item in enumerate(value):
                            refs(item, path + (str(i),))

                refs(setting)
                if not columns:
                    continue
                parameters: list[str] = []
                translation = (
                    [("phase_x", "function", "value"), ("phase_y", "function", "value")]
                    if setting["kind"] == "texture"
                    else [
                        ("motion", "x", "function", "value"),
                        ("motion", "y", "function", "value"),
                    ]
                )
                allowed = set(translation)
                if any(p in columns for p in translation):
                    if not all(p in columns for p in translation):
                        raise ValueError("Partial Cartesian condition binding")
                    parameters.extend(("Speed", "Direction"))
                angular = (
                    "motion",
                    "yaw" if setting["kind"] == "arena" else "rotation",
                    "function",
                    "value",
                )
                allowed.add(angular)
                if angular in columns:
                    parameters.append("Angular speed")
                for name, key in (
                    ("Width", "width"),
                    ("Height", "height"),
                    ("Opacity", "opacity"),
                ):
                    allowed.add((key, "value"))
                    if (key, "value") in columns:
                        parameters.append(name)
                if not set(columns).issubset(allowed):
                    raise ValueError(
                        "Use declared-unit editing for custom condition bindings"
                    )
                used.extend(columns.values())
                targets.append(
                    MotionTarget(
                        f"{node['epoch_id']} / {setting['instance_id']}",
                        setting,
                        columns,
                        parameters,
                    )
                )

    walk(group.model_dump(mode="json")["body"])
    if len(used) != len(set(used)) or set(used) != {
        c.column_id for c in group.conditions.columns
    }:
        raise ValueError("Shared/custom columns retain their declared units")
    return targets


class ConditionValues(QWidget):
    changed = pyqtSignal()

    def __init__(self, group: Group) -> None:
        super().__init__()
        assert group.conditions is not None
        self.group = group
        self.original = group.conditions.model_dump(mode="json")
        self.targets: list[MotionTarget] = []
        self.edited = False
        self.controls: list[tuple[int, str, QLineEdit]] = []
        self.initial_text: dict[QLineEdit, list[str]] = {}
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.addWidget(
            label(
                "Comma-separated lists are paired by position. Every list must have the same length.",
                wrap=True,
            )
        )
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        body.addLayout(form)
        try:
            self.targets = semantic_targets(group)
            for index, target in enumerate(self.targets):
                values: dict[str, list[float]] = {
                    name: [] for name in target.parameters
                }
                for row in self.original["rows"]:
                    source = substitute(
                        target.setting,
                        group.group_id,
                        {c["column_id"]: c["value"] for c in row["cells"]},
                    )
                    motion = (
                        dict(
                            zip(
                                ("Speed", "Direction", "Angular speed"),
                                motion_numbers(source),
                                strict=True,
                            )
                        )
                        if any(
                            n in values for n in ("Speed", "Direction", "Angular speed")
                        )
                        else {}
                    )
                    for name in values:
                        values[name].append(
                            motion[name]
                            if name in motion
                            else source[name.lower()]["value"]
                        )
                length = (
                    "mm"
                    if target.setting["kind"] == "arena"
                    or target.setting["space"]["kind"] == "physical_surface"
                    else "deg"
                )
                for name, items in values.items():
                    unit = {
                        "Speed": f"{length}/s",
                        "Direction": "deg",
                        "Angular speed": "deg/s",
                        "Width": length,
                        "Height": length,
                        "Opacity": "1",
                    }[name]
                    self.add_field(
                        form,
                        index,
                        name,
                        f"{target.name} · {name} ({unit})",
                        ", ".join(f"{v:.12g}" for v in items),
                    )
        except (ValueError, TypeError, KeyError):
            while form.rowCount():
                form.removeRow(0)
            self.controls.clear()
            self.targets = []
            for column in self.original["columns"]:
                identity = column["column_id"]
                raw_values = [
                    next(c["value"] for c in row["cells"] if c["column_id"] == identity)
                    for row in self.original["rows"]
                ]
                unit = column["unit"]
                self.add_field(
                    form,
                    -1,
                    identity,
                    f"{identity} ({unit or 'asset ID'})",
                    ", ".join(str(v) for v in raw_values),
                )
        self.changed.connect(lambda: setattr(self, "edited", True))

    def add_field(
        self, form: QFormLayout, index: int, name: str, caption: str, text: str
    ) -> None:
        control = QLineEdit(text)
        control.setMinimumWidth(0)
        control.textEdited.connect(self.changed)
        self.controls.append((index, name, control))
        self.initial_text[control] = text.split(",")
        form.addRow(label(caption, wrap=True), control)

    def read(self) -> dict[str, Any]:
        if not self.edited:
            return deepcopy(self.original)
        lists = [control.text().split(",") for _, _, control in self.controls]
        lengths = {len(items) for items in lists}
        if len(lengths) != 1 or not 0 < next(iter(lengths)) <= 512:
            raise ValueError("Use equally long value lists, with at most 512 rows")
        columns = {c["column_id"]: c for c in self.original["columns"]}
        result = deepcopy(self.original)
        rows: list[dict[str, Any]] = []
        for row_index in range(next(iter(lengths))):
            previous = self.original["rows"][
                min(row_index, len(self.original["rows"]) - 1)
            ]
            cells = {c["column_id"]: c["value"] for c in previous["cells"]}
            if self.targets:
                for index, target in enumerate(self.targets):
                    if all(
                        row_index < len(self.initial_text[control])
                        and items[row_index].strip()
                        == self.initial_text[control][row_index].strip()
                        for (i, _, control), items in zip(
                            self.controls, lists, strict=True
                        )
                        if i == index
                    ):
                        continue
                    source = substitute(target.setting, self.group.group_id, cells)
                    values = {
                        name: float(items[row_index])
                        for (i, name, _), items in zip(
                            self.controls, lists, strict=True
                        )
                        if i == index
                    }
                    for path, (value, _) in varied_fields(source, values).items():
                        if path in target.columns:
                            cells[target.columns[path]] = value
            else:
                for (_, identity, _), items in zip(self.controls, lists, strict=True):
                    cells[identity] = (
                        float(items[row_index])
                        if columns[identity]["value_type"] == "number"
                        else items[row_index].strip()
                    )
            row_id = (
                self.original["rows"][row_index]["row_id"]
                if row_index < len(self.original["rows"])
                else f"Added_{row_index + 1}"
            )
            while any(row["row_id"] == row_id for row in rows):
                row_id += "_new"
            rows.append(
                dict(
                    row_id=row_id,
                    cells=[dict(column_id=k, value=v) for k, v in cells.items()],
                )
            )
        result["rows"] = rows
        return result
