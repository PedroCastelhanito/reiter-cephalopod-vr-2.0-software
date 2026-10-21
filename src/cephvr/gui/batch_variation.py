"""Projector/layer variation targets, paired by value position."""

from decimal import Decimal, InvalidOperation
from random import Random
from typing import Literal

from PyQt6.QtCore import QEvent, pyqtSignal
from PyQt6.QtGui import QEnterEvent, QShowEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.batch_random import random_values
from cephvr.gui.batch_values import ValueRule
from cephvr.gui.components import button, combo, equal_row_height, label
from cephvr.gui.epoch_batch import END_BEHAVIORS
from cephvr.gui.stimulus_columns import stimulus_columns
from cephvr.visual_stimulus.config.models.authoring import VariationDraft
from cephvr.visual_stimulus.config.models.program_model import Settings


class BatchVariationRow(QWidget):
    changed = pyqtSignal()

    def __init__(
        self,
        targets: list[tuple[str, tuple[int, ...], int, str]],
        projectors: dict[str, list[int]] | None = None,
        settings: tuple[Settings, ...] = (),
        *,
        table_mode: bool = False,
    ) -> None:
        super().__init__()
        self.table_mode = table_mode
        self.targets = targets
        self.settings = settings
        self.projectors = projectors or {"Rig-wide": list(range(len(targets)))}
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(8)
        target_host = QWidget()
        row = QGridLayout(target_host)
        row.setHorizontalSpacing(8)
        body.addWidget(target_host)
        self.random_cache: tuple[tuple[str, ...], tuple[str, ...]] | None = None
        self.random = Random()
        self.random_seed = ""
        self.seed_key: tuple[str, ...] = ()
        self.rig_coordinates = True
        self.rig_angle_version: Literal[1, 2] = 2
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
            row.setColumnStretch(column, 0 if column == 1 else 1)
        self.layer.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.layer.setFixedWidth(64)
        row.setColumnMinimumWidth(1, 64)
        self.remove = button("×", "compact", hint="Remove variation")
        policy = self.remove.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.remove.setSizePolicy(policy)
        self.remove.hide()
        row.addWidget(self.remove, 1, 3)
        value_host = QWidget()
        self.value_grid = QGridLayout(value_host)
        self.value_grid.setContentsMargins(0, 0, 0, 0)
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
        body.addWidget(value_host)
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
        self.shared = QCheckBox("Share random values across projectors")
        self.shared.toggled.connect(self.changed)
        self.value_grid.addWidget(self.shared, 2, 0, 1, 4)
        if table_mode:
            target_host.hide()
            self.value_grid.removeWidget(self.method)
            method_item = self.value_grid.itemAtPosition(0, 0)
            assert method_item is not None
            method_caption = method_item.widget()
            if method_caption is not None:
                method_caption.hide()
            self.value_grid.setColumnStretch(0, 0)
        self.fit_control_heights()
        self.target.currentIndexChanged.connect(self.refresh_layers)
        self.layer.currentIndexChanged.connect(self.refresh)
        self.method.currentIndexChanged.connect(self.update_hint)
        self.parameter.currentIndexChanged.connect(self.update_hint)
        for control in (self.target, self.layer, self.parameter, self.method):
            control.currentIndexChanged.connect(self.changed)
        self.values.textChanged.connect(self.changed)
        self.refresh_layers()

    def enterEvent(self, event: QEnterEvent | None) -> None:
        if not self.table_mode:
            self.remove.show()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent | None) -> None:
        if not self.table_mode:
            self.remove.hide()
        super().leaveEvent(event)

    def fit_control_heights(self) -> None:
        equal_row_height(
            self.target,
            self.layer,
            self.parameter,
            self.method,
            self.values,
            self.remove,
            *self.random_fields.values(),
        )

    def showEvent(self, event: QShowEvent | None) -> None:
        super().showEvent(event)
        # Ancestor styles settle after insertion; fit again before the row is shown.
        self.fit_control_heights()

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
            self.layer.addItem(str(ordinal + 1), ordinal)
        if count > 1:
            self.layer.addItem("All", -1)
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

    def sampled_values(
        self, count: int, target_key: str = "", streams: int = 1
    ) -> tuple[str, ...]:
        inputs = (
            *[edit.text().strip() for edit in self.random_fields.values()],
            str(count),
            target_key,
            str(streams),
        )
        if self.random_cache is None or self.random_cache[0] != inputs:
            minimum, maximum, precision, size, _, _ = inputs
            values = tuple(
                value
                for _ in range(streams)
                for value in random_values(
                    minimum, maximum, precision, size, self.random.randrange
                )
            )
            self.random_cache = (inputs, values)
        return self.random_cache[1]

    def update_hint(self) -> None:
        categorical = self.parameter.currentData() == "At end"
        self.method.setEnabled(not categorical)
        if categorical:
            self.method.setCurrentIndex(0)
        random_method = self.method.currentIndex() == 2
        self.shared.setVisible(random_method and len(self.selected_projectors()) > 1)
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
        if self.target.currentIndex() < 0 or self.layer.currentIndex() < 0:
            raise ValueError("A saved variation target is unavailable")
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
            indices = self.target_indices()
            independent = not self.shared.isChecked()
            draws = self.sampled_values(
                random_count,
                repr(
                    (
                        self.target.currentData(),
                        self.layer.currentData(),
                        indices,
                        independent,
                    )
                ),
                len(indices) if independent else 1,
            )
            return tuple(
                ValueRule(
                    self.targets[index][1],
                    self.targets[index][2],
                    parameter,
                    draws[position * random_count : (position + 1) * random_count]
                    if independent
                    else draws,
                    self.rig_coordinates,
                    self.rig_angle_version,
                )
                for position, index in enumerate(indices)
            )
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
                self.rig_coordinates,
                self.rig_angle_version,
            )
            for i in self.target_indices()
        )

    def draft(self) -> VariationDraft:
        return VariationDraft(
            rig_coordinates=self.rig_coordinates,
            rig_angle_version=self.rig_angle_version,
            projector=self.target.currentData() or "",
            projectors=tuple(self.projectors),
            layer=self.layer.currentData()
            if self.layer.currentData() is not None
            else 0,
            parameter=self.parameter.currentData() or "",
            method=self.method.currentIndex(),
            values=self.values.text(),
            minimum=self.random_fields["minimum"].text(),
            maximum=self.random_fields["maximum"].text(),
            precision=self.random_fields["precision"].text(),
            shared=self.shared.isChecked(),
            seed=self.random_seed,
            sample_key=self.seed_key
            if self.random_seed
            else self.random_cache[0]
            if self.random_cache
            else (),
            samples=self.random_cache[1] if self.random_cache else (),
        )

    def restore(self, draft: VariationDraft) -> None:
        self.rig_coordinates = draft.rig_coordinates
        self.rig_angle_version = draft.rig_angle_version
        if self.rig_coordinates and self.rig_angle_version == 1:
            self.setToolTip(
                "Saved variation uses Back 0°; recreate it to use Right 0°."
            )
        if not self.rig_coordinates:
            self.setToolTip(
                "Saved variation uses legacy local coordinates; recreate it to use rig directions."
            )
        self.target.setCurrentIndex(self.target.findData(draft.projector))
        self.layer.setCurrentIndex(self.layer.findData(draft.layer))
        self.parameter.setCurrentIndex(self.parameter.findData(draft.parameter))
        self.method.setCurrentIndex(draft.method)
        self.values.setText(draft.values)
        for key, edit in self.random_fields.items():
            edit.setText(getattr(draft, key))
        self.shared.setChecked(draft.shared)
        self.random_seed, self.seed_key = draft.seed, draft.sample_key
        self.random_cache = (draft.sample_key, draft.samples) if draft.samples else None
        direction_index = self.parameter.findData("Direction")
        if (
            direction_index >= 0
            and self.rig_coordinates
            and self.rig_angle_version == 1
        ):
            self.parameter.setItemText(direction_index, "Direction (legacy rig)")
        if direction_index >= 0 and not self.rig_coordinates:
            self.parameter.setItemText(direction_index, "Direction (legacy local)")
