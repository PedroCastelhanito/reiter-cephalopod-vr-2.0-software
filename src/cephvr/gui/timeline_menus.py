"""Keyboard-accessible selection of shared and inactive authored layers."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QMenu, QWidget

from cephvr.gui.program_editing import NodePath, node_at, path_tuple
from cephvr.gui.projector_layers import layer_title, layers_for
from cephvr.gui.stimulus_scope import surfaces
from cephvr.visual_stimulus.config.models.program_model import Epoch, Program


class StimulusSelectionMenu(QMenu):
    selected = pyqtSignal(int, str, int)

    def __init__(self, parent: QWidget) -> None:
        super().__init__("Select stimulus…", parent)

    def populate(
        self, program: Program, path: NodePath, screens: tuple[str, ...]
    ) -> None:
        self.clear()
        node = node_at(program, path)
        if not isinstance(node, Epoch):
            return
        authored = set().union(
            *(set(surfaces(s.model_dump(mode="json"))) for s in node.settings)
        )
        faces = (
            "",
            *screens,
            *(f.title() for f in sorted(authored) if f.title() not in screens),
        )
        index = path_tuple(path)[-1]
        for face in faces:
            caption = face or "All projectors"
            if face and face not in screens:
                caption += " (inactive)"
            submenu = self.addMenu(caption)
            assert submenu is not None
            for layer in layers_for(program, node, face):
                action = submenu.addAction(layer_title(program, node.settings[layer]))
                assert action is not None
                action.triggered.connect(
                    lambda checked=False, f=face, selected_layer=layer: (
                        self.selected.emit(index, f, selected_layer)
                    )
                )
