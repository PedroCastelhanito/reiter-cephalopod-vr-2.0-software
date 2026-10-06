"""Per-projector value editors for one selected batch parameter."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from cephvr.gui.components import button, combo, label
from cephvr.gui.epoch_batch import LayerTarget, matching_layer, parameter_value
from cephvr.gui.paths import PathEdit
from cephvr.gui.program_editing import node_at
from cephvr.visual_stimulus.config.models.program_model import Epoch, Program

PARAMETERS = (
    "Duration",
    "Asset",
    "Fit",
    "Speed",
    "Direction",
    "Angular speed",
    "Start size",
    "End size",
    "Growth duration",
    "Playback start",
    "Opacity",
)


def supports(family_name: str, parameter: str) -> bool:
    if parameter == "Fit":
        return family_name == "Image"
    if parameter in ("Asset", "Angular speed"):
        return True
    if parameter in ("Speed", "Direction"):
        return family_name in ("Texture", "Image", "3D arena")
    if parameter in ("Start size", "End size", "Growth duration"):
        return family_name == "Looming image"
    if parameter == "Playback start":
        return family_name == "Video"
    return parameter == "Opacity" and family_name != "3D arena"


class ProjectorEditRow(QWidget):
    """One projector/layer selector and one pending value for the chosen parameter."""

    browse_requested = pyqtSignal(object)
    change_requested = pyqtSignal(object)

    def __init__(self, face: str) -> None:
        super().__init__()
        self.face = face
        self.targets: list[LayerTarget] = []
        self.program: Program | None = None
        self.paths: tuple[tuple[int, ...], ...] = ()
        self.parameter = ""
        self.dirty = False
        self.bound_layer = 0
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.caption = label(face or "3D arena", "label")
        self.caption.setMinimumWidth(84)
        layout.addWidget(self.caption)
        self.layer = combo(())
        self.layer.setMinimumWidth(0)
        self.layer.currentIndexChanged.connect(self.choose_layer)
        layout.addWidget(self.layer, 2)
        self.value = PathEdit()
        self.value.setMinimumWidth(0)
        self.value.textEdited.connect(self.mark_changed)
        layout.addWidget(self.value, 3)
        self.fit = combo(("Contain", "Cover", "Stretch"))
        self.fit.hide()
        self.fit.currentTextChanged.connect(self.set_fit)
        layout.addWidget(self.fit, 3)
        self.browse = button("…", hint="Choose prepared asset")
        self.browse.clicked.connect(lambda: self.browse_requested.emit(self))
        layout.addWidget(self.browse)

    @property
    def target(self) -> LayerTarget | None:
        index = self.layer.currentIndex()
        return self.targets[index] if 0 <= index < len(self.targets) else None

    def bind(
        self,
        program: Program,
        paths: tuple[tuple[int, ...], ...],
        parameter: str,
        targets: list[LayerTarget],
    ) -> None:
        previous = self.target
        self.program, self.paths, self.parameter = program, paths, parameter
        self.targets = targets
        self.dirty = False
        self.layer.blockSignals(True)
        self.layer.clear()
        for target in targets:
            title = target.family.replace("Looming image", "Looming")
            self.layer.addItem(f"{title} · layer {target.ordinal + 1}")
        self.layer.setCurrentIndex(
            targets.index(previous) if previous in targets else (0 if targets else -1)
        )
        self.layer.blockSignals(False)
        self.layer.setEnabled(bool(targets))
        self.browse.setVisible(parameter == "Asset")
        self.browse.setEnabled(bool(targets))
        self.refresh_value()

    def choose_layer(self) -> None:
        self.change_requested.emit(self)

    def restore_layer(self) -> None:
        self.layer.blockSignals(True)
        self.layer.setCurrentIndex(self.bound_layer)
        self.layer.blockSignals(False)

    def refresh_value(self) -> None:
        self.bound_layer = self.layer.currentIndex()
        target = self.target
        self.value.clear()
        self.value.setPlaceholderText("Unavailable")
        self.value.setEnabled(target is not None)
        self.value.setVisible(self.parameter != "Fit")
        self.fit.setVisible(self.parameter == "Fit")
        self.fit.setEnabled(target is not None)
        self.fit.blockSignals(True)
        self.fit.setCurrentIndex(-1)
        self.fit.blockSignals(False)
        if self.program is None or target is None:
            return
        values: list[str] = []
        units: set[str] = set()
        for path in self.paths:
            try:
                epoch = node_at(self.program, path)
                assert isinstance(epoch, Epoch)
                setting = epoch.settings[
                    matching_layer(self.program, path, target)
                ].model_dump(mode="json")
                if self.parameter == "Asset":
                    identity = setting.get(
                        "asset_id", setting.get("pattern", {}).get("asset_id")
                    )
                    value = next(
                        asset.logical_path
                        for asset in self.program.assets
                        if asset.asset_id == identity
                    )
                else:
                    raw = parameter_value(setting, self.parameter)
                    value = f"{raw:g}" if isinstance(raw, (float, int)) else str(raw)
                length = (
                    "mm"
                    if setting["kind"] == "arena"
                    or setting["space"]["kind"] == "physical_surface"
                    else "°"
                )
                units.add(
                    {
                        "Speed": length + "/s",
                        "Direction": "°",
                        "Angular speed": "°/s",
                        "Start size": length,
                        "End size": length,
                        "Growth duration": "s",
                        "Playback start": "s",
                    }.get(self.parameter, "")
                )
                values.append(value)
            except (ValueError, KeyError, AssertionError, StopIteration):
                values.append("Custom / unavailable")
        if len(units) > 1:
            self.value.setEnabled(False)
            self.value.setPlaceholderText("Mixed units")
        elif values and len(set(values)) == 1 and values[0] != "Custom / unavailable":
            self.value.setText(values[0])
        else:
            self.value.setPlaceholderText(
                "Mixed" if len(set(values)) > 1 else values[0] if values else ""
            )
        unit = next(iter(units)) if len(units) == 1 else ""
        if self.parameter == "Fit":
            self.fit.blockSignals(True)
            self.fit.setCurrentIndex(self.fit.findText(self.value.text().title()))
            self.fit.blockSignals(False)
        self.value.setAccessibleName(
            f"{self.face or '3D arena'} {self.parameter}"
            + (f" ({unit})" if unit else "")
        )

    def mark_changed(self, _text: str) -> None:
        self.dirty = True

    def set_fit(self, text: str) -> None:
        self.value.setText(text.lower())
        self.dirty = True

    def set_asset(self, path: str) -> None:
        self.value.setText(path)
        self.dirty = True
