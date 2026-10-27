"""Per-projector recipe selection with cancellable off-thread preparation."""

from collections.abc import Callable
from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Event, Thread
from typing import cast

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import Card, button, label
from cephvr.gui.notices import FormNotice
from cephvr.gui.paths import PathField
from cephvr.gui.sparse_noise_import import (
    RecipeSelection,
    prepare_selection,
    saved_selection,
    select_recipe,
)
from cephvr.visual_stimulus.config.models.display_profile import Geometry
from cephvr.visual_stimulus.config.models.program_model import Program
from cephvr.visual_stimulus.config.models.schema_common import SurfaceId


def _prepare(
    selections: dict[SurfaceId, RecipeSelection],
    root: Path,
    geometry: Geometry,
    pattern_count: int,
    pattern_duration: str,
    cancelled: Event,
    results: SimpleQueue[tuple[Program, Path] | Exception],
) -> None:
    def check() -> None:
        if cancelled.is_set():
            raise ValueError("Sparse-noise preparation cancelled")

    try:
        results.put(
            prepare_selection(
                selections,
                root,
                geometry,
                pattern_count=pattern_count,
                pattern_duration=pattern_duration,
                check=check,
            )
        )
    except Exception as error:
        results.put(error)


class SparseNoiseDialog(QDialog):
    prepared = pyqtSignal(object, str, str)

    def __init__(
        self,
        parent: QWidget,
        *,
        root: Path,
        geometry: Geometry,
        screens: tuple[str, ...],
        available: Callable[[], bool],
        program_path: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sparse noise recipes")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(720, 760)
        self.root, self.scene_geometry, self.available = root, geometry, available
        self.cancelled = Event()
        self.results: SimpleQueue[tuple[Program, Path] | Exception] = SimpleQueue()
        self.running = False
        self.fields: dict[SurfaceId, PathField] = {}
        self.summaries = {}
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        body = QVBoxLayout(content)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        body.addWidget(
            label(
                "Select a recipe for each projector you want to use. Leave others blank.",
                wrap=True,
            )
        )
        self.name = QLineEdit("Sparse noise")
        self.name.setAccessibleName("Sparse-noise trial name")
        body.addWidget(label("Trial name", "label"))
        body.addWidget(self.name)
        paths, count, duration = saved_selection(root, program_path)
        self.pattern_count = QSpinBox()
        self.pattern_count.setRange(1, 1_000_000)
        self.pattern_count.setValue(count)
        self.pattern_duration = QLineEdit(duration)
        body.addWidget(label("Pattern count", "label"))
        body.addWidget(self.pattern_count)
        body.addWidget(label("Pattern duration (seconds)", "label"))
        body.addWidget(self.pattern_duration)
        for screen in screens:
            face = cast(SurfaceId, screen.lower())
            if face not in {"front", "left", "right", "bottom"}:
                raise ValueError("Unknown sparse-noise projector")
            card = Card(screen, compact=True)
            field = PathField(
                title=f"Select {screen} sparse-noise recipe",
                placeholder="No sparse-noise recipe",
                file_filter="Sparse-noise recipes (*.json)",
            )
            field.editor.filename_only = True
            field.editor.setAccessibleName(f"{screen} sparse-noise recipe")
            field.editor.setText(paths.get(face, ""))
            field.path_selected.connect(lambda _, f=face: self.describe(f))
            field.browse.clicked.connect(
                lambda checked=False, f=field: (
                    f.dialog.setDirectory(str(self.root))
                    if f.dialog is not None
                    else None
                )
            )
            field.editor.editingFinished.connect(lambda f=face: self.describe(f))
            summary = label("", wrap=True)
            card.body.addWidget(field)
            card.body.addWidget(summary)
            self.fields[face], self.summaries[face] = field, summary
            body.addWidget(card)
            self.describe(face)
        body.addWidget(
            label(
                "Selected recipes must use matching backgrounds. Each screen keeps its recipe seed.",
                wrap=True,
            )
        )
        self.status = label("", wrap=True)
        body.addWidget(self.status)
        self.notice = FormNotice()
        body.addWidget(self.notice)
        row = QHBoxLayout()
        row.addStretch()
        self.cancel_button = button("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        self.prepare_button = button("Add sparse-noise trial")
        self.prepare_button.clicked.connect(self.start)
        row.addWidget(self.cancel_button)
        row.addWidget(self.prepare_button)
        layout.addLayout(row)
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.poll)

    def describe(self, face: SurfaceId) -> None:
        text = self.fields[face].editor.text().strip()
        try:
            recipe = select_recipe(self.root, text).recipe if text else None
            summary = (
                (
                    f"Seed {recipe.seed} · min distance {recipe.min_active_cell_distance_mm:g} mm · "
                    f"{recipe.active_probability:.1%} active probability · "
                    f"{recipe.square_size_mm:g} mm squares"
                )
                if recipe
                else "Background only"
            )
        except (OSError, ValueError) as error:
            summary = str(error)
        self.summaries[face].setText(summary)

    def start(self) -> None:
        if self.running or not self.available():
            return
        try:
            if not self.name.text().strip():
                raise ValueError("Enter a trial name")
            selections = {
                face: select_recipe(self.root, field.editor.text().strip())
                for face, field in self.fields.items()
                if field.editor.text().strip()
            }
            if not selections:
                raise ValueError("Select a recipe for at least one projector")
        except (OSError, ValueError) as error:
            self.notice.warn(error)
            return
        self.cancelled.clear()
        self.running = True
        self.prepare_button.setEnabled(False)
        self.name.setEnabled(False)
        self.pattern_count.setEnabled(False)
        self.pattern_duration.setEnabled(False)
        for field in self.fields.values():
            field.setEnabled(False)
        self.status.setText("Preparing sparse-noise patterns…")
        # Worker owns only immutable inputs and cancellation/result channels, never Qt objects.
        Thread(
            target=_prepare,
            args=(
                selections,
                self.root,
                self.scene_geometry,
                self.pattern_count.value(),
                self.pattern_duration.text().strip(),
                self.cancelled,
                self.results,
            ),
            daemon=True,
            name="sparse-noise-preparation",
        ).start()
        self.timer.start()

    def poll(self) -> None:
        if not self.available():
            self.reject()
            return
        try:
            result = self.results.get_nowait()
        except Empty:
            return
        self.timer.stop()
        self.running = False
        if isinstance(result, Exception):
            self.prepare_button.setEnabled(True)
            self.name.setEnabled(True)
            self.pattern_count.setEnabled(True)
            self.pattern_duration.setEnabled(True)
            for field in self.fields.values():
                field.setEnabled(True)
            self.status.clear()
            self.notice.warn(result)
            return
        program, path = result
        self.prepared.emit(program, str(path), self.name.text().strip())
        self.accept()

    def reject(self) -> None:
        self.cancelled.set()
        self.timer.stop()
        for field in self.fields.values():
            if field.dialog is not None:
                field.dialog.reject()
        super().reject()
