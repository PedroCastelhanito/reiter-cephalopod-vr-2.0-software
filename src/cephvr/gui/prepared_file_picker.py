"""One cancelable prepared-file dialog; no document state ownership."""

from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QWidget

from cephvr.gui.file_dialogs import file_dialog, open_file_dialog


class PreparedFilePicker(QObject):
    selected = pyqtSignal(str, str, bool)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.dialog: QFileDialog | None = None

    def open(self, preset: str, root: str, new_epoch: bool) -> None:
        if not root or not Path(root).is_dir():
            raise ValueError("Choose the Assets folder first")
        if self.dialog is not None:
            self.dialog.raise_()
            return
        parent = self.parent()
        assert isinstance(parent, QWidget)
        dialog = file_dialog(
            parent,
            f"Select prepared {preset.lower().replace('looming image', 'looming')}",
            root,
        )
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        filters = {
            "Texture drift": "Textures (*.json *.png *.tif *.tiff *.jpg *.jpeg)",
            "Texture": "Textures (*.json *.png *.tif *.tiff *.jpg *.jpeg)",
            "Grating": "Grating texture designs (*.json)",
            "Image": "Images (*.png *.tif *.tiff *.jpg *.jpeg)",
            "Looming image": "Images (*.png *.tif *.tiff *.jpg *.jpeg)",
            "Video": "Videos (*.mp4 *.mkv)",
            "3D arena": "Arenas (*.glb)",
        }
        dialog.setNameFilter(filters[preset])
        dialog.fileSelected.connect(
            lambda path: self.selected.emit(preset, path, new_epoch)
        )
        dialog.finished.connect(lambda: setattr(self, "dialog", None))
        dialog.finished.connect(dialog.deleteLater)
        self.dialog = dialog
        open_file_dialog(dialog)
