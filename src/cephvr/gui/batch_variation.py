"""Projector/layer variation targets, paired by value position."""

from decimal import Decimal, InvalidOperation
from random import Random

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QGridLayout, QLineEdit, QSizePolicy, QWidget

from cephvr.gui.batch_random import random_values
from cephvr.gui.batch_values import ValueRule
from cephvr.gui.components import button, combo, equal_row_height, label
from cephvr.gui.epoch_batch import END_BEHAVIORS
from cephvr.gui.stimulus_columns import stimulus_columns
from cephvr.visual_stimulus.config.models.program_model import Settings


class BatchVariationRow(QWidget):
    changed = pyqtSignal()

    def __init__(
        self,
        targets: list[tuple[str, tuple[int, ...], int, str]],
        projectors: dict[str, list[int]] | None = None,
        settings: tuple[Settings, ...] = (),
    ) -> None:
        super().__init__()
        self.targets = targets
        self.settings = settings
        self.projectors = projectors or {"Rig-wide": list(range(len(targets)))}
        row = QGridLayout(self)
        self.random_cache: tuple[tuple[str, ...], tuple[str, ...]] | None = None
        self.random = Random()
        row.setContentsMargins(0, 0, 0, 0)
        self.target = combo(())
        if "Rig-wide" not in self.projectors:
            self.target.addItem("All projectors", "")
        for face in self.projectors:
            self.target.addItem(face, face)
        initial = next(
            (face for face, layers in self.projectors.items() if layers),
            next(iter(self.projectors)),
        )
        self.target.setCurrentIndex(self.target.findData(initial))
        self.layer = combo(())
        self.parameter = combo(())
        self.method = combo(("Values", "Sweep (min, max, step)", "Random"))
        self.values = QLineEdit()
        self.values.setPlaceholderText("10, 20, 30")
        for column, (caption, control) in enumerate(
            (
                ("Projectors", self.target),
                ("Layer", self.layer),
                ("Parameter", self.parameter),
            )
        ):
            control.setMinimumWidth(0)
            control.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            caption_widget = label(caption, "label")
            caption_widget.setBuddy(control)
            row.addWidget(caption_widget, 0, column)
            row.addWidget(control, 1, column)
            row.setColumnStretch(column, 1)
        self.remove = button("×", hint="Remove variation")
        self.remove.setFixedWidth(32)
        row.addWidget(self.remove, 1, 3)
        value_host = QWidget()
        self.value_grid = QGridLayout(value_host)
        self.value_grid.setContentsMargins(0, 8, 0, 0)
        self.value_grid.setHorizontalSpacing(8)
        self.value_grid.setColumnStretch(0, 1)
        for column, (caption, value_control) in enumerate(
            (("Method", self.method), ("Values", self.values))
        ):
            value_control.setMinimumWidth(0)
            value_control.setSizePolicy(
                QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
            )
            text = label(caption, "label")
            text.setBuddy(value_control)
            self.value_grid.addWidget(text, 0, column)
            self.value_grid.addWidget(value_control, 1, column)
            if caption == "Values":
                self.values_caption = text
        row.addWidget(value_host, 2, 0, 1, 4)
        self.random_fields: dict[str, QLineEdit] = {}
        self.random_captions: list[QWidget] = []
        for column, (key, caption, value) in enumerate(
            (
                ("minimum", "Minimum", "0"),
                ("maximum", "Maximum", "100"),
                ("precision", "Precision", "1"),
            )
        ):
            edit = QLineEdit(value)
            edit.setMinimumWidth(0)
            edit.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            edit.setAccessibleName(f"Random {caption.lower()}")
            text = label(caption, "label")
            text.setBuddy(edit)
            self.value_grid.addWidget(text, 0, column + 1)
            self.value_grid.addWidget(edit, 1, column + 1)
            self.value_grid.setColumnStretch(column + 1, 1)
            self.random_captions.append(text)
            self.random_fields[key] = edit
            edit.textChanged.connect(self.changed)
        self.random_fields["precision"].setToolTip(
            "Value resolution: 1 for whole numbers, 0.1 for one decimal place. "
            "Values are multiples of this step within the range; repeats are allowed."
        )
        equal_row_height(
            self.target,
            self.layer,
            self.parameter,
            self.method,
            self.values,
            self.remove,
            *self.random_fields.values(),
        )
        self.target.currentIndexChanged.connect(self.refresh_layers)
        self.layer.currentIndexChanged.connect(self.refresh)
        self.method.currentIndexChanged.connect(self.update_hint)
        self.parameter.currentIndexChanged.connect(self.update_hint)
        for control in (self.target, self.layer, self.parameter, self.method):
            control.currentIndexChanged.connect(self.changed)
        self.values.textChanged.connect(self.changed)
        self.refresh_layers()

    def selected_projectors(self) -> list[str]:
        face = self.target.currentData()
        return [face] if face else list(self.projectors)

    def refresh_layers(self) -> None:
        previous = self.layer.currentData()
        self.layer.blockSignals(True)
        self.layer.clear()
        faces = self.selected_projectors()
        count = min((len(self.projectors[f]) for f in faces), default=0)
        for ordinal in range(count):
            if len(faces) == 1:
                caption = self.targets[self.projectors[faces[0]][ordinal]][0]
                caption = caption.split(" · ", 1)[-1]
                self.layer.addItem(f"{ordinal + 1} · {caption}", ordinal)
            else:
                self.layer.addItem(f"Layer {ordinal + 1}", ordinal)
        if count > 1:
            self.layer.addItem("All layers", -1)
        self.layer.setCurrentIndex(max(0, self.layer.findData(previous)))
        self.layer.blockSignals(False)
        self.refresh()

    def target_indices(self) -> list[int]:
        faces = self.selected_projectors()
        ordinal = self.layer.currentData()
        if ordinal is None:
            raise ValueError("Selected projectors need a common stimulus layer")
        return list(
            dict.fromkeys(
                index
                for face in faces
                for index in (
                    self.projectors[face]
                    if ordinal == -1
                    else [self.projectors[face][ordinal]]
                )
            )
        )

    def refresh(self) -> None:
        self.setEnabled(bool(self.targets))
        try:
            indices = self.target_indices()
        except ValueError:
            indices = []
        previous = self.parameter.currentData()
        options = [
            stimulus_columns(self.settings[self.targets[i][2]])
            if self.settings
            else (
                ("Speed", "Speed"),
                ("Direction", "Direction"),
                ("Rotation", "Angular speed"),
            )
            for i in indices
        ]
        common = (
            [item for item in options[0] if all(item in choices for choices in options)]
            if options
            else []
        )
        self.parameter.blockSignals(True)
        self.parameter.clear()
        for caption, key in common:
            if key != "Fit":
                self.parameter.addItem(caption, key)
        self.parameter.setCurrentIndex(max(0, self.parameter.findData(previous)))
        self.parameter.blockSignals(False)
        self.update_hint()

    def sampled_values(self, count: int) -> tuple[str, ...]:
        inputs = (
            *[edit.text().strip() for edit in self.random_fields.values()],
            str(count),
        )
        if self.random_cache is None or self.random_cache[0] != inputs:
            minimum, maximum, precision, size = inputs
            values = random_values(
                minimum, maximum, precision, size, self.random.randrange
            )
            self.random_cache = (inputs, values)
        return self.random_cache[1]

    def update_hint(self) -> None:
        categorical = self.parameter.currentData() == "At end"
        self.method.setEnabled(not categorical)
        if categorical:
            self.method.setCurrentIndex(0)
        random_method = self.method.currentIndex() == 2
        for control in (*self.random_fields.values(), *self.random_captions):
            control.setVisible(random_method)
        if random_method:
            self.value_grid.removeWidget(self.values)
            self.value_grid.removeWidget(self.values_caption)
        else:
            self.value_grid.addWidget(self.values, 1, 1, 1, 3)
            self.value_grid.addWidget(self.values_caption, 0, 1, 1, 3)
        self.values.setVisible(not random_method)
        self.values_caption.setVisible(not random_method)
        if categorical:
            self.values.setPlaceholderText("loop, hold final frame")
            return
        self.values.setPlaceholderText(
            "0, 10, 2" if self.method.currentIndex() else "10, 20, 30"
        )

    def read_rules(self, random_count: int = 1) -> tuple[ValueRule, ...]:
        if not self.targets:
            raise ValueError("Add a stimulus before creating a variation")
        parameter = self.parameter.currentData()
        if not parameter:
            raise ValueError("Selected layers have no common variation parameter")
        if self.method.currentIndex() == 0:
            values = tuple(v.strip() for v in self.values.text().split(","))
            if parameter == "At end":
                if any(v.lower() not in END_BEHAVIORS for v in values):
                    raise ValueError("At end values must be loop or hold final frame")
            else:
                for value in values:
                    float(value)
        elif self.method.currentIndex() == 2:
            values = self.sampled_values(random_count)
        else:
            try:
                start, stop, step = (
                    Decimal(part.strip()) for part in self.values.text().split(",")
                )
            except (InvalidOperation, ValueError) as error:
                raise ValueError("Sweep needs min, max, step") from error
            if (
                not all(v.is_finite() for v in (start, stop, step))
                or step <= 0
                or stop < start
            ):
                raise ValueError("Sweep needs finite min ≤ max and positive step")
            count = int((stop - start) // step) + 1
            if count > 512:
                raise ValueError("Sweep exceeds 512 values")
            values = tuple(str(start + i * step) for i in range(count))
        return tuple(
            ValueRule(
                self.targets[i][1],
                self.targets[i][2],
                parameter,
                values,
            )
            for i in self.target_indices()
        )
