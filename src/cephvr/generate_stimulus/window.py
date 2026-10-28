"""Offline authoring window; documents own state, workers receive snapshots."""

import copy
from collections.abc import Callable
from pathlib import Path
from queue import Empty
from typing import Any

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QKeySequence
from PyQt6.QtWidgets import (
    QFileDialog,
    QListWidget,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.theme import SIZES
from cephvr.visual_stimulus.config.models.display_profile import Geometry

from .arena import CompiledArena, arena_job
from .bake import TextureCache
from .documents import load_design, save_design, save_suggestion
from .errors import describe_error, error_items, status_line
from .geometry import GeometryCache
from .jobs import Jobs
from .layout import AuthoringLayout
from .markers import show_errors, workspace_items
from .models import ArenaDesign
from .prompts import ask_reset, ask_unsaved, save_file_name
from .properties import flush_edits
from .surfaces import SurfaceEditor, arena_panel
from .texture_panel import texture_widgets
from .texture_preview import texture_job
from .textures import (
    is_pristine,
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
        # Conversion notice while a document differs from its legacy source file.
        self.legacy: list[str | None] = [None, None]
        self.jobs = Jobs()
        self.geometry_cache = GeometryCache()
        self.texture_cache = TextureCache()
        self.selected_names = ["floor"]
        self.surface_editor: SurfaceEditor | None = None
        self.problems: list[tuple[str, str]] = []
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
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.preview)
        # Polled only while a job is outstanding.
        self.poll = QTimer(self)
        self.poll.setInterval(40)
        self.poll.timeout.connect(self.collect)
        self.tabs.currentChanged.connect(self.tab_changed)
        self.face.currentIndexChanged.connect(self.schedule)
        self.preview_mode.currentIndexChanged.connect(self.rebuild)
        self.index.valueChanged.connect(self.schedule)
        self.rebuild()

    @property
    def surfaces(self) -> QListWidget:
        assert self.surface_editor is not None
        return self.surface_editor.list

    def active(self) -> int:
        return self.tabs.currentIndex()

    def flush(self) -> None:
        flush_edits(self.properties)

    def refresh_modified(self) -> None:
        self.setWindowModified(self.documents != self.saved)

    def changed(self, index: int | None = None) -> None:
        self.refresh_modified()
        self.schedule()

    def schedule(self, *args: Any) -> None:
        self.jobs.cancel.set()
        self.timer.start()

    def submit(self, operation: Callable[[Callable[[], None]], Any]) -> int:
        serial = self.jobs.submit(operation)
        self.poll.start()
        return serial

    def tab_changed(self, index: int) -> None:
        # Pending edits still belong to the panel being left.
        self.flush()
        self.problems = []
        self.set_stale(False)
        self.rebuild()

    def rebuild(self, *args: Any) -> None:
        i = self.active()
        arena = i == 1
        self.viewport.setVisible(arena)
        self.image.setVisible(not arena)
        self.arena_controls.setVisible(arena)
        self.preview_controls.setVisible(not arena)
        self.face_field.setVisible(not arena and self.preview_mode.currentIndex() == 1)
        self.mode_field.setVisible(not arena)
        self.legacy_note.setText(self.legacy[i] or "")
        self.legacy_note.setVisible(self.legacy[i] is not None)
        self.index_field.setVisible(
            not arena and self.documents[0].get("kind") == "sparse_noise"
        )
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SIZES.card_gap)
        if arena:
            self.arena_panel(layout)
        else:
            for widget in texture_widgets(
                self.documents[0],
                self.root if self.paths[0] is None else self.paths[0].parent,
                lambda: self.changed(0),
                self.rebuild,
                self.change_pattern,
            ):
                layout.addWidget(widget)
        layout.addStretch()
        self.set_properties(panel)
        self.apply_markers()
        self.schedule()

    def change_pattern(self, selector: Any, old: str, new: str) -> None:
        """Replace the document's pattern; its parameters reset, so confirm real edits."""
        self.flush()
        if new == old:
            return
        if not is_pristine(self.documents[0], old) and not ask_reset(
            self,
            "Change pattern",
            "Changing the pattern resets its parameters. Continue?",
            "Reset parameters",
        ):
            selector.blockSignals(True)
            selector.setCurrentIndex(selector.findData(old))
            selector.blockSignals(False)
            return
        self.documents[0] = new_texture(new)
        self.changed(0)
        self.rebuild()

    def arena_panel(self, layout: QVBoxLayout) -> None:
        self.surface_editor = arena_panel(
            layout,
            self.documents[1],
            self.root,
            self.selected_names,
            lambda: self.changed(1),
            self.rebuild,
            self.surfaces_rebuilt,
        )

    def surfaces_rebuilt(self) -> None:
        self.apply_markers()
        self.refresh_captions()

    def select_surface(self, name: str) -> None:
        if self.active() == 1 and self.surface_editor is not None:
            self.surface_editor.select(name)

    def preview(self) -> None:
        document = copy.deepcopy(self.documents[self.active()])
        root, geometry = self.root, self.display_geometry
        face, index = str(self.face.currentData()), self.index.value()
        screen = self.preview_mode.currentIndex() == 1
        recipe_directory = self.root if self.paths[0] is None else self.paths[0].parent
        if self.active() == 1:
            self.submit(
                arena_job(document, root, self.geometry_cache, self.texture_cache)
            )
        else:
            self.submit(
                texture_job(
                    document,
                    root,
                    geometry,
                    face=face,
                    index=index,
                    screen=screen,
                    directory=recipe_directory,
                )
            )

    def collect(self) -> None:
        while True:
            try:
                serial, result, error = self.jobs.results.get_nowait()
            except Empty:
                break
            if serial != self.jobs.serial or self.jobs.cancel.is_set():
                continue
            if error:
                self.show_problem(error)
                continue
            self.problems = []
            self.apply_markers()
            self.set_stale(False)
            if isinstance(result, CompiledArena):
                self.viewport.set_arena(result)
            else:
                self.image.set_pixels(result)
            if isinstance(result, CompiledArena) and self.viewport.error:
                message = f"3D preview unavailable: {self.viewport.error}. Saving remains available."
                self.status.showMessage(message)
            else:
                self.status.clearMessage()
        if not self.jobs.working and self.jobs.results.empty():
            self.poll.stop()

    def show_problem(self, text: str) -> None:
        """Mark the offending fields and dim the now-stale preview."""
        self.problems = error_items(text)
        self.apply_markers()
        self.set_stale(True)
        self.status.showMessage(status_line(text))

    def apply_markers(self) -> None:
        items = workspace_items(self.problems, self.active() == 1, self.selected_names)
        show_errors(self.properties, items)

    def set_stale(self, stale: bool) -> None:
        self.image.dimmer.setEnabled(stale)
        self.preview_note.setText(
            "Preview out of date: fix the marked fields." if stale else ""
        )
        self.preview_note.setVisible(stale)

    def validate(self) -> None:
        if self.active() == 1:
            ArenaDesign.model_validate(self.documents[1])
        else:
            validate_texture(self.documents[0])

    def confirm_discard(self) -> bool:
        self.flush()
        i = self.active()
        if self.documents[i] == self.saved[i]:
            return True
        choice = ask_unsaved(self, "Unsaved design", "This design has unsaved changes.")
        return self.save() if choice == "save" else choice == "discard"

    def open(self) -> None:
        self.flush()
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open design", str(self.root), "Design JSON (*.json)"
        )
        if not filename:
            return
        try:
            path = Path(filename)
            data, notice = load_design(path)
            i = 1 if data.get("kind") == "arena_design" else 0
            if i != self.active():
                if self.documents[i] != self.saved[i]:
                    raise ValueError(
                        "Save or discard the other workspace's modified design before opening this file"
                    )
            elif not self.confirm_discard():
                return
            self.documents[i] = data
            # A converted design never equals its file, so it stays modified.
            self.saved[i] = copy.deepcopy(data) if notice is None else {}
            self.paths[i], self.legacy[i] = path, notice
            self.tabs.setCurrentIndex(i)
            self.refresh_modified()
            self.rebuild()
        except Exception as error:
            QMessageBox.warning(self, "Cannot open design", describe_error(error))

    def save(self) -> bool:
        self.flush()
        try:
            self.validate()
            i = self.active()
            previous_path = self.paths[i]
            default = self.root / ("design.arena.json" if i else "texture.json")
            legacy = previous_path is not None and self.legacy[i] is not None
            title = "Save design as"
            if legacy:
                title = "Save converted legacy design as a new file"
            filename = save_file_name(
                self, title, save_suggestion(previous_path, legacy, default)
            )
            if not filename:
                return False
            path = Path(filename)
            if previous_path and legacy and path.resolve() == previous_path.resolve():
                QMessageBox.warning(
                    self,
                    "Cannot save design",
                    "The legacy file is never overwritten; choose a new file name.",
                )
                return False
            origin = self.root if previous_path is None else previous_path.parent
            self.documents[i] = save_design(self.documents[i], self.root, path, origin)
            self.paths[i], self.legacy[i] = path, None
            self.saved[i] = copy.deepcopy(self.documents[i])
            self.refresh_modified()
            # Saving returns a new document; bind controls and preview to that owner.
            self.rebuild()
            self.status.showMessage(f"Saved {path}")
            return True
        except Exception as error:
            text = describe_error(error)
            self.show_problem(text)
            QMessageBox.warning(self, "Cannot save design", text)
            return False

    def closeEvent(self, event: QCloseEvent | None) -> None:
        if event is None:
            return
        if not self.confirm_close():
            event.ignore()
            return
        self.shutdown()
        event.accept()

    def confirm_close(self) -> bool:
        self.flush()
        if self.documents == self.saved or self.documents == self._approved_close:
            return True
        choice = ask_unsaved(
            self, "Unsaved designs", "Save your changes before closing?"
        )
        if choice == "cancel":
            return False
        if choice == "save":
            for i in range(len(self.documents)):
                if self.documents[i] != self.saved[i]:
                    self.tabs.setCurrentIndex(i)
                    if not self.save():
                        return False
            return True
        # Managed closure may finish asynchronously after configuration history saves.
        self._approved_close = copy.deepcopy(self.documents)
        return True

    def shutdown(self) -> None:
        self.jobs.close()
        self.timer.stop()
        self.poll.stop()
