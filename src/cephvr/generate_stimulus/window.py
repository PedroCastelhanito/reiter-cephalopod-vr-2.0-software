"""Offline authoring window; documents own state, workers receive snapshots."""

import copy
from pathlib import Path
from queue import Empty
from typing import Any

import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QImage, QKeySequence, QPixmap
from PyQt6.QtWidgets import (
    QFileDialog,
    QListWidget,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import Card, combo, field
from cephvr.gui.theme import SIZES
from cephvr.visual_stimulus.config.models.display_profile import Geometry

from .arena import CompiledArena, compile_arena, export_arena
from .documents import apply_changes, read_design, save_design
from .geometry import GeometryCache
from .jobs import Jobs
from .layout import AuthoringLayout
from .models import ArenaDesign
from .properties import property_form
from .texture_preview import preview_texture
from .textures import (
    PATTERNS,
    load_geometry,
    new_texture,
    validate_texture,
)


class AuthoringWindow(AuthoringLayout):
    def __init__(
        self,
        root: Path,
        geometry: Geometry | None = None,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if parent is not None:
            self.setWindowFlags(Qt.WindowType.Widget)
        self.root, self.display_geometry = root.resolve(), geometry
        self.documents = [new_texture(), ArenaDesign().model_dump(mode="json")]
        self.saved = copy.deepcopy(self.documents)
        self._approved_close: list[dict[str, Any]] | None = None
        self.paths: list[Path | None] = [None, None]
        self.history = [[copy.deepcopy(d)] for d in self.documents]
        self.positions = [0, 0]
        self.jobs = Jobs()
        self.geometry_cache = GeometryCache()
        self.job_kind = "preview"
        self.exporting = False
        self.pixels: np.ndarray | None = None
        self.setWindowTitle("CephVR2 — Generate assets[*]")
        self.resize(1280, 850)
        if parent is None:
            self.setMinimumSize(720, 600)
        self.build_layout(
            [
                ("Open…", self.open, QKeySequence.StandardKey.Open),
                ("Save as…", self.save, QKeySequence.StandardKey.Save),
            ],
        )
        self.viewport.failed.connect(self.status.showMessage)
        self.viewport.selected.connect(self.select_surface)
        self.image.resized.connect(self.show_pixels)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.preview)
        self.poll = QTimer(self)
        self.poll.setInterval(40)
        self.poll.timeout.connect(self.collect)
        self.poll.start()
        self.tabs.currentChanged.connect(self.rebuild)
        self.face.currentTextChanged.connect(self.schedule)
        self.preview_mode.currentIndexChanged.connect(self.rebuild)
        self.index.valueChanged.connect(self.schedule)
        self.rebuild()

    def active(self) -> int:
        return self.tabs.currentIndex()

    def changed(self) -> None:
        i = self.active()
        current = copy.deepcopy(self.documents[i])
        if current != self.history[i][self.positions[i]]:
            self.history[i] = self.history[i][: self.positions[i] + 1] + [current]
            self.history[i] = self.history[i][-100:]
            self.positions[i] = len(self.history[i]) - 1
        self.setWindowModified(self.documents != self.saved)
        self.schedule()

    def schedule(self, *args: Any) -> None:
        if not self.exporting:
            self.jobs.cancel.set()
            self.timer.start()

    def rebuild(self, *args: Any) -> None:
        i = self.active()
        arena = i == 1
        self.viewport.setVisible(arena)
        self.image.setVisible(not arena)
        self.fit_button.setVisible(arena)
        self.face_field.setVisible(not arena and self.preview_mode.currentIndex() == 1)
        self.mode_field.setVisible(not arena)
        self.index_field.setVisible(
            not arena and self.documents[0].get("kind") == "sparse_noise"
        )
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SIZES.card_gap)
        if not arena:
            selector = combo(
                tuple(
                    name
                    for name in [*PATTERNS, "sparse_noise"]
                    if name not in {"bars_horizontal", "bars_vertical"}
                )
            )
            pattern = self.documents[0].get("pattern", "sparse_noise")
            selector.setPlaceholderText(f"{pattern} (saved recipe)")
            selector.setCurrentIndex(selector.findText(pattern))

            def pattern_changed(pattern: str) -> None:
                self.documents[0] = new_texture(pattern)
                self.changed()
                self.rebuild()

            selector.currentTextChanged.connect(pattern_changed)
            pattern_card = Card("Texture")
            pattern_card.body.addWidget(field("Pattern", selector))
            layout.addWidget(pattern_card)
            data = self.documents[0]
            if data.get("kind") == "texture":
                data = data["params"]
            layout.addWidget(
                property_form(
                    data,
                    self.changed,
                    self.rebuild,
                    title="Parameters",
                    hidden=frozenset(
                        {
                            "texture_resolution",
                            "tile_width_mm",
                            "line_spacing_mm",
                            "line_width_mm",
                        }
                        if self.documents[0].get("pattern")
                        in {"bars_horizontal", "bars_vertical"}
                        else ()
                    ),
                    directory=self.root
                    if self.paths[0] is None
                    else self.paths[0].parent,
                )
            )
        else:
            design = self.documents[1]
            geometry = {k: v for k, v in design.items() if k != "surfaces"}

            def geometry_changed() -> None:
                design.update(geometry)
                self.changed()

            layout.addWidget(
                property_form(
                    geometry, geometry_changed, self.rebuild, title="Geometry"
                )
            )
            self.surfaces = QListWidget()
            self.surfaces.addItems(list(design["surfaces"]))
            self.surfaces.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
            self.surfaces.setFixedHeight(130)
            layout.addWidget(self.surfaces)
            self.surfaces.setCurrentRow(0)
            self.surface_panel = QVBoxLayout()
            layout.addLayout(self.surface_panel)
            self.surfaces.itemSelectionChanged.connect(self.surface_properties)
            self.surface_properties()
        layout.addStretch()
        self.set_properties(panel)
        self.schedule()

    def surface_properties(self) -> None:
        while self.surface_panel.count():
            item = self.surface_panel.takeAt(0)
            assert item is not None
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        selected = [item.text() for item in self.surfaces.selectedItems()]
        if not selected:
            return
        data = copy.deepcopy(self.documents[1]["surfaces"][selected[0]])
        previous = copy.deepcopy(data)

        def changed() -> None:
            nonlocal previous
            for name in selected:
                apply_changes(self.documents[1]["surfaces"][name], previous, data)
            previous = copy.deepcopy(data)
            self.changed()

        self.surface_panel.addWidget(
            property_form(
                data,
                changed,
                self.surface_properties,
                title=" / ".join(selected),
                directory=self.root,
            )
        )
        self.refresh_captions()

    def select_surface(self, name: str) -> None:
        if self.active() == 1:
            self.surfaces.setCurrentRow(list(self.documents[1]["surfaces"]).index(name))

    def undo(self) -> None:
        self.restore(-1)

    def redo(self) -> None:
        self.restore(1)

    def restore(self, step: int) -> None:
        i = self.active()
        position = self.positions[i] + step
        if 0 <= position < len(self.history[i]):
            self.positions[i] = position
            self.documents[i] = copy.deepcopy(self.history[i][position])
            self.rebuild()

    def preview(self) -> None:
        document = copy.deepcopy(self.documents[self.active()])
        root, geometry = self.root, self.display_geometry
        face, index = self.face.currentText(), self.index.value()
        screen = self.preview_mode.currentIndex() == 1
        recipe_directory = self.root if self.paths[0] is None else self.paths[0].parent
        geometry_cache = self.geometry_cache
        self.job_kind = "preview"
        if self.active() == 1:
            self.jobs.submit(
                lambda check: compile_arena(
                    ArenaDesign.model_validate(document),
                    root,
                    check=check,
                    geometry_cache=geometry_cache,
                )
            )
        else:
            self.jobs.submit(
                lambda check: preview_texture(
                    document,
                    root,
                    geometry,
                    face=face,
                    index=index,
                    check=check,
                    directory=recipe_directory,
                    screen=screen,
                )
            )
        self.status.clearMessage()

    def collect(self) -> None:
        while True:
            try:
                serial, result, error = self.jobs.results.get_nowait()
            except Empty:
                break
            if serial != self.jobs.serial or self.jobs.cancel.is_set():
                continue
            exporting = self.exporting
            self.set_exporting(False)
            if error:
                self.status.showMessage(error)
                continue
            if exporting:
                self.status.showMessage(f"Exported {result}")
                continue
            if isinstance(result, CompiledArena):
                self.viewport.set_arena(result)
            else:
                self.pixels, _caption = result
                self.show_pixels()
            if isinstance(result, CompiledArena) and self.viewport.error:
                message = f"3D preview unavailable: {self.viewport.error}. Export remains available."
                self.status.showMessage(message)
            else:
                self.status.clearMessage()

    def show_pixels(self) -> None:
        if self.pixels is None:
            return
        from .textures import display_pixels

        pixels = display_pixels(self.pixels)
        height, width = pixels.shape[:2]
        image = QImage(
            pixels.tobytes(), width, height, width * 3, QImage.Format.Format_RGB888
        ).copy()
        self.image.setPixmap(
            QPixmap.fromImage(image).scaled(
                self.image.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        )

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self.show_pixels()

    def validate(self) -> None:
        if self.active() == 1:
            ArenaDesign.model_validate(self.documents[1])
        else:
            validate_texture(self.documents[0])

    def confirm_discard(self) -> bool:
        i = self.active()
        return (
            self.documents[i] == self.saved[i]
            or QMessageBox.question(
                self, "Unsaved design", "Discard unsaved changes to this design?"
            )
            == QMessageBox.StandardButton.Yes
        )

    def new(self) -> None:
        if self.confirm_discard():
            i = self.active()
            self.documents[i] = (
                new_texture() if i == 0 else ArenaDesign().model_dump(mode="json")
            )
            self.paths[i] = None
            self.saved[i] = copy.deepcopy(self.documents[i])
            self.history[i] = [copy.deepcopy(self.documents[i])]
            self.positions[i] = 0
            self.rebuild()

    def open(self) -> None:
        if not self.confirm_discard():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open design", str(self.root), "Design JSON (*.json)"
        )
        if not filename:
            return
        try:
            path = Path(filename)
            data = read_design(path)
            arena = data.get("kind") == "arena_design"
            i = 1 if arena else 0
            if i != self.active() and self.documents[i] != self.saved[i]:
                raise ValueError(
                    "Save or discard the other workspace's modified design before opening this file"
                )
            self.documents[i] = data
            self.saved[i] = copy.deepcopy(data)
            self.paths[i] = path
            self.history[i] = [copy.deepcopy(data)]
            self.positions[i] = 0
            self.tabs.setCurrentIndex(i)
            self.rebuild()
        except Exception as error:
            QMessageBox.warning(self, "Cannot open design", str(error))

    def save(self) -> None:
        try:
            self.validate()
            i = self.active()
            previous_path = self.paths[i]
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Save design as",
                str(
                    previous_path
                    or self.root / ("design.arena.json" if i else "texture.json")
                ),
                "JSON (*.json)",
            )
            if not filename:
                return
            path = Path(filename)
            origin = self.root if previous_path is None else previous_path.parent
            self.documents[i] = save_design(self.documents[i], self.root, path, origin)
            self.paths[i] = path
            self.saved[i] = copy.deepcopy(self.documents[i])
            # Saving returns a new document; bind controls and preview to that owner.
            self.rebuild()
            self.status.showMessage(f"Saved {path}")
        except Exception as error:
            QMessageBox.warning(self, "Cannot save design", str(error))

    def set_exporting(self, exporting: bool) -> None:
        self.exporting = exporting
        self.properties.setEnabled(not exporting)
        self.tabs.setEnabled(not exporting)
        for action in self.file_actions:
            action.setEnabled(not exporting)

    def export(self) -> None:
        if self.active() == 0:
            self.save()
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export new arena bundle directory",
            str(self.root / "arena-bundle"),
            "Bundle directory (*)",
        )
        if not filename:
            return
        try:
            design = ArenaDesign.model_validate(self.documents[1])
            root = self.root
            destination = Path(filename)
            self.timer.stop()
            self.set_exporting(True)
            self.job_kind = "export"
            self.jobs.submit(
                lambda check: export_arena(design, root, destination, check=check)
            )
            self.status.showMessage("Validating and exporting arena…")
        except Exception as error:
            self.set_exporting(False)
            QMessageBox.warning(self, "Cannot export", str(error))

    def cancel_job(self) -> None:
        self.jobs.cancel.set()
        self.timer.stop()
        self.set_exporting(False)
        self.status.showMessage(
            "Generation cancelled; already published exports are preserved"
        )

    def choose_root(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Asset root", str(self.root))
        if directory:
            self.root = Path(directory).resolve()
            self.schedule()

    def calibration(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load calibration geometry", str(self.root), "JSON (*.json)"
        )
        if filename:
            try:
                self.display_geometry = load_geometry(Path(filename))
                self.schedule()
            except Exception as error:
                QMessageBox.warning(self, "Invalid calibration", str(error))

    def closeEvent(self, event: QCloseEvent | None) -> None:
        if event is None:
            return
        if not self.confirm_close():
            event.ignore()
            return
        self.shutdown()
        event.accept()

    def confirm_close(self) -> bool:
        if self.documents == self.saved or self.documents == self._approved_close:
            return True
        if (
            QMessageBox.question(
                self, "Unsaved designs", "Close and discard unsaved changes?"
            )
            != QMessageBox.StandardButton.Yes
        ):
            return False
        # Managed closure may finish asynchronously after configuration history saves.
        self._approved_close = copy.deepcopy(self.documents)
        return True

    def shutdown(self) -> None:
        self.jobs.close()
        self.timer.stop()
        self.poll.stop()
