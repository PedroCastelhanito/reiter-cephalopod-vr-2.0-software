"""Projector/layer variation targets, paired by value position."""

from random import Random
from typing import Literal

from PyQt6.QtCore import QEvent, QTimer, pyqtSignal
from PyQt6.QtGui import QEnterEvent, QResizeEvent, QShowEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.batch_random import random_values
from cephvr.gui.batch_values import ValueRule, listed_values
from cephvr.gui.components import button, combo, equal_row_height, label
from cephvr.gui.editing_card import EditingSurface
from cephvr.gui.stimulus_columns import stimulus_columns
from cephvr.gui.variation_assets import VariationAssets
from cephvr.visual_stimulus.config.models.authoring import VariationDraft
from cephvr.visual_stimulus.config.models.program_model import Settings


class BatchVariationRow(EditingSurface):
    changed = pyqtSignal()

    def __init__(
        self,
        targets: list[tuple[str, tuple[int, ...], int, str]],
        projectors: dict[str, list[int]] | None = None,
        settings: tuple[Settings, ...] = (),
        *,
        presentation: bool = False,
        random_only: bool = False,
    ) -> None:
        super().__init__()
        self.presentation = presentation
        self.random_only = random_only
        self.targets = targets
        self.settings = settings
        self.projectors = projectors or {"Rig-wide": list(range(len(targets)))}
        self.stacked: bool | None = None
        body = QVBoxLayout(self)
        body.setContentsMargins(16, 16, 16, 16)
        body.setSpacing(8)
        target_host = QWidget()
        self.target_grid = QGridLayout(target_host)
        row = self.target_grid
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
        self.target_captions = []
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
        self.method = combo(())
        for method, title in enumerate(("Values", "Sweep (min, max, step)", "Random")):
            if not random_only or method == 2:
                self.method.addItem(title, method)
        self.method.setToolTip(
            "Assign a random parameter value to each repetition without adding source epochs."
            if random_only
            else "Choose how to generate parameter values."
        )
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
            self.target_captions.append(caption_widget)
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
        row.addWidget(self.editing_label, 0, 3)
        self.remove.hide()
        self.hover_timer = QTimer(self)
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self.refresh_remove)
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
            if caption == "Method":
                self.method_caption = text
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
                ("precision", "Resolution", "1"),
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
        self.asset_folder = VariationAssets()
        self.asset_folder.editor.textChanged.connect(self.changed)
        self.folder_caption = label("Folder", "label")
        self.folder_caption.setBuddy(self.asset_folder.editor)
        body.addWidget(self.folder_caption)
        body.addWidget(self.asset_folder)
        self.fit_control_heights()
        self.target.currentIndexChanged.connect(self.refresh_layers)
        self.layer.currentIndexChanged.connect(self.refresh)
        self.method.currentIndexChanged.connect(self.update_hint)
        self.parameter.currentIndexChanged.connect(self.update_hint)
        for control in (self.target, self.layer, self.parameter, self.method):
            control.currentIndexChanged.connect(self.changed)
        self.values.textChanged.connect(self.changed)
        self.refresh_layers()
        self.arrange(self.width())

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        self.arrange(self.width())

    def arrange(self, width: int) -> None:
        stacked = width < 460
        if stacked == self.stacked:
            return
        self.stacked = stacked
        for widget in (
            *self.target_captions,
            self.target,
            self.layer,
            self.parameter,
            self.editing_label,
            self.remove,
        ):
            self.target_grid.removeWidget(widget)
        value_widgets = (
            self.method_caption,
            self.method,
            self.values_caption,
            self.values,
            *self.random_captions,
            *self.random_fields.values(),
            self.shared,
        )
        for widget in value_widgets:
            self.value_grid.removeWidget(widget)
        if stacked:
            self.target_grid.addWidget(self.target_captions[0], 0, 0, 1, 2)
            self.target_grid.addWidget(self.target_captions[1], 0, 2)
            self.target_grid.addWidget(self.editing_label, 0, 3)
            self.target_grid.addWidget(self.target, 1, 0, 1, 2)
            self.target_grid.addWidget(self.layer, 1, 2)
            self.target_grid.addWidget(self.remove, 1, 3)
            self.target_grid.addWidget(self.target_captions[2], 2, 0, 1, 4)
            self.target_grid.addWidget(self.parameter, 3, 0, 1, 4)
            self.target_grid.setColumnStretch(0, 1)
            self.target_grid.setColumnStretch(1, 0)
            self.target_grid.setColumnStretch(2, 0)
            self.target_grid.setColumnStretch(3, 0)
            self.value_grid.addWidget(self.method_caption, 0, 0, 1, 4)
            self.value_grid.addWidget(self.method, 1, 0, 1, 4)
            self.value_grid.addWidget(self.values_caption, 2, 0, 1, 4)
            self.value_grid.addWidget(self.values, 3, 0, 1, 4)
            for index, (caption, edit) in enumerate(
                zip(self.random_captions, self.random_fields.values(), strict=True)
            ):
                self.value_grid.addWidget(caption, 4 + index * 2, 0, 1, 4)
                self.value_grid.addWidget(edit, 5 + index * 2, 0, 1, 4)
            self.value_grid.addWidget(self.shared, 10, 0, 1, 4)
        else:
            for column, caption in enumerate(self.target_captions):
                self.target_grid.addWidget(caption, 0, column)
            for column, control in enumerate((self.target, self.layer, self.parameter)):
                self.target_grid.addWidget(control, 1, column)
            self.target_grid.addWidget(self.editing_label, 0, 3)
            self.target_grid.addWidget(self.remove, 1, 3)
            self.target_grid.setColumnStretch(0, 1)
            self.target_grid.setColumnStretch(1, 0)
            self.target_grid.setColumnStretch(2, 1)
            self.target_grid.setColumnStretch(3, 0)
            span = 4 if self.parameter.currentData() == "Asset" else 1
            self.value_grid.addWidget(self.method_caption, 0, 0, 1, span)
            self.value_grid.addWidget(self.method, 1, 0, 1, span)
            self.value_grid.addWidget(self.values_caption, 0, 1, 1, 3)
            self.value_grid.addWidget(self.values, 1, 1, 1, 3)
            for column, (caption, edit) in enumerate(
                zip(self.random_captions, self.random_fields.values(), strict=True),
                start=1,
            ):
                self.value_grid.addWidget(caption, 0, column)
                self.value_grid.addWidget(edit, 1, column)
            self.value_grid.addWidget(self.shared, 2, 0, 1, 4)

    def refresh_remove(self) -> None:
        self.remove.setVisible(self.underMouse() or self.editing)

    def enterEvent(self, event: QEnterEvent | None) -> None:
        super().enterEvent(event)
        self.hover_timer.start()

    def leaveEvent(self, event: QEvent | None) -> None:
        super().leaveEvent(event)
        self.hover_timer.start()

    def focus_changed(self, old: QWidget | None, new: QWidget | None) -> None:
        super().focus_changed(old, new)
        if hasattr(self, "hover_timer"):
            self.hover_timer.start()

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
        # Empty rules must remain removable; only their value editors are unavailable.
        for control in (
            self.target,
            self.layer,
            self.parameter,
            self.values,
            self.shared,
            *self.random_fields.values(),
        ):
            control.setEnabled(bool(self.targets))
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
            if self.presentation and key not in ("Playback start", "At end"):
                continue
            if key != "Fit" and not (
                self.random_only and self.method.currentData() == 2 and key == "At end"
            ):
                self.parameter.addItem(caption, key)
        if (
            self.random_only
            and indices
            and self.settings
            and all(
                (setting := self.settings[self.targets[i][2]]).kind == "video"
                or setting.kind == "image"
                or (setting.kind == "texture" and setting.pattern.kind == "image_tile")
                for i in indices
            )
        ):
            self.parameter.addItem("Asset", "Asset")
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
        asset = self.parameter.currentData() == "Asset"
        if asset and self.method.currentText() != "Random from folder":
            self.method.blockSignals(True)
            self.method.clear()
            self.method.addItem("Random from folder", 2)
            self.method.blockSignals(False)
        elif not asset and self.method.currentText() == "Random from folder":
            self.method.setItemText(self.method.findData(2), "Random")
        categorical = self.parameter.currentData() == "At end"
        self.method.setEnabled(bool(self.targets) and not categorical)
        if categorical:
            self.method.setCurrentIndex(self.method.findData(0))
        random_method = self.method.currentData() == 2
        self.shared.setVisible(random_method and len(self.selected_projectors()) > 1)
        for control in (*self.random_fields.values(), *self.random_captions):
            control.setVisible(random_method and not asset)
        self.values.setVisible(not random_method and not asset)
        self.values_caption.setVisible(not random_method and not asset)
        self.asset_folder.setVisible(asset)
        self.folder_caption.setVisible(asset)
        if self.stacked is False:
            self.value_grid.addWidget(self.method_caption, 0, 0, 1, 4 if asset else 1)
            self.value_grid.addWidget(self.method, 1, 0, 1, 4 if asset else 1)
        if categorical:
            self.values.setPlaceholderText("loop, hold final frame")
            return
        self.values.setPlaceholderText(
            "0, 10, 2" if self.method.currentData() == 1 else "10, 20, 30"
        )

    def read_rules(self, random_count: int = 1) -> tuple[ValueRule, ...]:
        if not self.targets:
            raise ValueError("Add a stimulus before creating a variation")
        if self.target.currentIndex() < 0 or self.layer.currentIndex() < 0:
            raise ValueError("A saved variation target is unavailable")
        parameter = self.parameter.currentData()
        if not parameter:
            raise ValueError("Selected layers have no common variation parameter")
        if self.method.currentData() == 2:
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
            values = listed_values(
                self.method.currentData(), self.values.text(), parameter
            )
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
            method=self.method.currentData(),
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
            folder=self.asset_folder.editor.text().strip(),
            asset_ids=self.asset_folder.asset_ids,
            grating_periods_mm=self.asset_folder.grating_periods_mm,
        )

    def restore(self, draft: VariationDraft) -> None:
        if self.method.findData(draft.method) < 0:
            # Retain imported list semantics without offering them for new rules.
            self.method.addItem(
                "Values (saved)" if draft.method == 0 else "Sweep (saved)", draft.method
            )
        if draft.method != 2:
            self.method.setCurrentIndex(self.method.findData(draft.method))
            self.refresh()
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
        self.method.setCurrentIndex(self.method.findData(draft.method))
        self.values.setText(draft.values)
        self.asset_folder.restore(
            draft.folder, draft.asset_ids, draft.grating_periods_mm
        )
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
