"""Lazy in-process authoring page; no experiment or projector ownership."""

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from cephvr.visual_stimulus.config.models.display_profile import Geometry

if TYPE_CHECKING:
    from cephvr.generate_stimulus.window import AuthoringWindow


class StimulusAuthoringPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        # Qt recreates a shown native window when its first GL child is added.
        # A hidden child selects GL composition before show without a GL context.
        self.composition_anchor = QOpenGLWidget(self)
        self.composition_anchor.hide()
        self.editor: AuthoringWindow | None = None
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(0, 0, 0, 0)

    def open_editor(self, root: Path, geometry: Geometry | None) -> None:
        if self.editor is not None:
            return
        from cephvr.generate_stimulus.window import AuthoringWindow

        self.editor = AuthoringWindow(root, geometry, parent=self)
        self.body.addWidget(self.editor)

    def confirm_close(self) -> bool:
        return self.editor is None or self.editor.confirm_close()

    def shutdown(self) -> None:
        if self.editor is not None:
            self.editor.shutdown()
