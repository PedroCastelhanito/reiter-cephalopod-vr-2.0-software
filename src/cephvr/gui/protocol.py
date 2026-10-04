"""Card-based local protocol configuration and canonical timeline editing."""

from pathlib import Path

from PyQt6.QtCore import QIODevice, QSaveFile, Qt, pyqtSignal
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import Card, button, combo, equal_row_height, label
from cephvr.gui.layouts import column
from cephvr.gui.protocol_editor import ProtocolEditor
from cephvr.gui.recordings import RecordingsCard
from cephvr.gui.stimulus_assets import StimulusAssetsCard
from cephvr.gui.view import DashboardView
from cephvr.visual_stimulus.config.models.program_model import parse_program_json


class ProtocolPage(QWidget):
    participation_changed = pyqtSignal()

    def __init__(self, recordings: RecordingsCard, *, sample: bool = False) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.config_scroll = QScrollArea()
        self.config_scroll.setWidgetResizable(True)
        self.config_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.config_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        content, body = column()
        self.config_scroll.setWidget(content)
        root.addWidget(self.config_scroll)
        top = self.top_grid = QGridLayout()
        top.setSpacing(14)
        body.addLayout(top)
        self.assets = StimulusAssetsCard()
        top.addWidget(self.assets, 0, 1)
        top.setColumnStretch(0, 3)
        top.setColumnStretch(1, 2)
        self.recordings = recordings
        self.can_edit = False
        self.session_mode = combo(("Open-loop", "Closed-loop"))
        self.session_mode.currentTextChanged.connect(self.participation_changed.emit)
        recordings.changed.connect(self.participation_changed.emit)
        self.program_card = Card("Protocol type")
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        toolbar.addWidget(self.session_mode, 1)
        self.load_button = button("Load…")
        self.load_button.clicked.connect(self.choose_load)
        self.save_button = button("Save as…")
        self.save_button.clicked.connect(self.choose_save)
        equal_row_height(self.session_mode, self.load_button, self.save_button)
        toolbar.addWidget(self.load_button, alignment=Qt.AlignmentFlag.AlignBottom)
        toolbar.addWidget(self.save_button, alignment=Qt.AlignmentFlag.AlignBottom)
        self.program_card.body.addLayout(toolbar)
        self.message = label("", wrap=True)
        self.message.hide()
        self.program_card.body.addWidget(self.message)
        top.addWidget(self.program_card, 0, 0)
        self.editor = ProtocolEditor(sample=sample)
        self.editor.changed.connect(self.mark_changed)
        self.assets.folders["root"].editor.textChanged.connect(
            lambda path: setattr(self.editor.parameters, "asset_root", path)
        )
        self.assets.folders["root"].editor.textChanged.connect(
            self.editor.create_batch.composer.set_asset_root
        )
        self.assets.folders["root"].editor.textChanged.connect(
            lambda path: setattr(self.editor.batch_edit, "asset_root", path)
        )
        body.addWidget(self.editor, 1)
        self.save_dialog: QFileDialog | None = None
        self.load_dialog: QFileDialog | None = None

    def resizeEvent(self, event: QResizeEvent | None) -> None:  # noqa: N802
        super().resizeEvent(event)
        wide = self.width() >= 650
        self.top_grid.removeWidget(self.assets)
        self.top_grid.addWidget(self.assets, 0 if wide else 1, 1 if wide else 0)
        self.top_grid.setColumnStretch(1, 2 if wide else 0)

    @property
    def tracking_active(self) -> bool:
        return (
            self.session_mode.currentText() == "Closed-loop"
            or self.recordings.velocities.isChecked()
        )

    def mark_changed(self) -> None:
        self.message.clear()
        self.message.hide()

    def load_program(self, path: str) -> None:
        if not self.can_edit or not path:
            return
        try:
            with Path(path).open("rb") as stream:
                data = stream.read(1_048_577)
            program = parse_program_json(data.decode("utf-8"), max_bytes=1_048_576)
        except (OSError, ValueError) as error:
            self.show_error("Cannot load program", error)
            return
        self.editor.drafts[self.editor.index].path = path
        self.editor.set_program(program)
        self.message.hide()

    def show_error(self, title: str, error: Exception) -> None:
        self.message.setText(f"{title} · see details")
        self.message.show()
        self.message.setToolTip(str(error))

    def choose_load(self) -> None:
        if not self.can_edit:
            return
        if self.load_dialog is not None:
            self.load_dialog.raise_()
            return
        dialog = QFileDialog(self, "Load stimulus program")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setNameFilter("Stimulus programs (*.json)")
        dialog.fileSelected.connect(self.load_program)
        dialog.finished.connect(lambda: setattr(self, "load_dialog", None))
        dialog.finished.connect(dialog.deleteLater)
        self.load_dialog = dialog
        dialog.open()

    def choose_save(self) -> None:
        if not self.can_edit:
            return
        if self.save_dialog is not None:
            self.save_dialog.raise_()
            return
        dialog = QFileDialog(self, "Save stimulus program")
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setNameFilter("Stimulus programs (*.json)")
        dialog.setDefaultSuffix("json")
        dialog.fileSelected.connect(self.save_program)
        dialog.finished.connect(lambda: setattr(self, "save_dialog", None))
        dialog.finished.connect(dialog.deleteLater)
        self.save_dialog = dialog
        dialog.open()

    def save_program(self, path: str) -> None:
        if not self.can_edit or not self.editor.flush_parameters():
            return
        try:
            program = parse_program_json(
                self.editor.program.model_dump_json(), max_bytes=1_048_576
            )
            data = program.model_dump_json(indent=2).encode("utf-8")
            output = QSaveFile(path)
            if not output.open(QIODevice.OpenModeFlag.WriteOnly):
                raise OSError(output.errorString())
            if output.write(data) != len(data):
                output.cancelWriting()
                raise OSError(output.errorString())
            if not output.commit():
                raise OSError(output.errorString())
        except (OSError, ValueError) as error:
            self.show_error("Cannot save program", error)
            return
        self.editor.drafts[self.editor.index].path = path
        self.message.setText("Trial saved")
        self.message.show()

    def apply_view(self, view: DashboardView) -> None:
        self.assets.apply_view(view)
        self.can_edit = view.sample and view.can_edit
        if not self.can_edit:
            self.editor.parameters.close_file_dialog()
            self.editor.create_batch.composer.close_file_dialogs()
            batch_picker = self.editor.batch_edit.asset_picker
            if batch_picker.dialog is not None:
                batch_picker.dialog.reject()
            self.editor.close_source_dialog()
            if self.save_dialog is not None:
                self.save_dialog.reject()
            if self.load_dialog is not None:
                self.load_dialog.reject()
        self.program_card.setEnabled(self.can_edit)
        self.editor.setEnabled(self.can_edit)
        self.editor.create_batch.setEnabled(self.can_edit)
        self.editor.batch_edit.setEnabled(self.can_edit)
