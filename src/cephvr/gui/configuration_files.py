"""Bounded JSON snapshot files and authority-aware, nonmodal file controls."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QIODevice, QObject, QSaveFile, pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QPushButton, QWidget

from cephvr.gui.components import button

JSON = dict[str, Any]
SNAPSHOT_LIMIT = 32 * 1024 * 1024


def members(pairs: list[tuple[str, Any]]) -> JSON:
    result: JSON = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate configuration key: {key}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise ValueError(f"Nonfinite JSON value: {value}")


def read_snapshot(path: str, limit: int = SNAPSHOT_LIMIT) -> JSON:
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"Configuration exceeds its {limit:,} byte limit")
    value = json.loads(
        raw.decode("utf-8"), object_pairs_hook=members, parse_constant=reject_constant
    )
    if not isinstance(value, dict):
        raise ValueError("Expected a configuration object")
    return value


def write_snapshot(path: str, value: JSON, limit: int = SNAPSHOT_LIMIT) -> None:
    raw = (
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    if len(raw) > limit:
        raise ValueError(f"Configuration exceeds its {limit:,} byte limit")
    output = QSaveFile(path)
    if not output.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError(output.errorString())
    if output.write(raw) != len(raw):
        output.cancelWriting()
        raise OSError(output.errorString())
    if not output.commit():
        raise OSError(output.errorString())


def fields(value: Any, keys: set[str], name: str) -> JSON:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{name}: invalid field inventory")
    return value


def text(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name}: expected text")
    return value


def boolean(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name}: expected true or false")
    return bool(value)


def envelope(value: Any, name: str, keys: set[str]) -> JSON:
    data = fields(value, keys | {"format", "version"}, name)
    if (
        data["format"] != name
        or type(data["version"]) is not int
        or data["version"] != 1
    ):
        raise ValueError(f"Unsupported {name} format/version")
    return data


class ConfigurationFiles(QObject):
    """File callbacks receive only their owning section; loading sends no commands."""

    message = pyqtSignal(str)
    loaded = pyqtSignal()
    loaded_document = pyqtSignal(object, str)

    def __init__(
        self,
        parent: QWidget,
        title: str,
        filename: str,
        *,
        capture: Callable[[], JSON],
        validate: Callable[[Any], JSON],
        apply: Callable[[JSON], None],
        available: Callable[[], bool],
        load_button: QPushButton | None = None,
        save_button: QPushButton | None = None,
        limit: int = SNAPSHOT_LIMIT,
        connect_actions: bool = True,
    ) -> None:
        super().__init__(parent)
        self.parent_widget = parent
        self.title, self.filename = title, filename
        self.capture, self.validate, self.apply, self.available = (
            capture,
            validate,
            apply,
            available,
        )
        self.limit = limit
        self.dialog: QFileDialog | None = None
        self.load_button = load_button if load_button is not None else button("Load…")
        self.save_button = (
            save_button if save_button is not None else button("Save as…")
        )
        self.load_button.setToolTip(f"Load {title} configuration JSON")
        self.save_button.setToolTip(f"Save {title} configuration JSON")
        if connect_actions:
            self.load_button.clicked.connect(lambda: self.choose(save=False))
            self.save_button.clicked.connect(lambda: self.choose(save=True))

    def set_enabled(self, enabled: bool) -> None:
        self.load_button.setEnabled(enabled)
        self.save_button.setEnabled(enabled)
        if not enabled and self.dialog is not None:
            self.dialog.reject()

    def choose(self, *, save: bool) -> None:
        if not self.available():
            return
        if self.dialog is not None:
            self.dialog.raise_()
            return
        dialog = QFileDialog(
            self.parent_widget, f"{'Save' if save else 'Load'} {self.title}"
        )
        dialog.setNameFilter(f"{self.title} configuration (*.json)")
        if save:
            dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
            dialog.setDefaultSuffix("json")
            dialog.selectFile(self.filename)
        else:
            dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.fileSelected.connect(
            lambda path: (
                (self.save_path(path) if save else self.load_path(path))
                if self.dialog is dialog
                else None
            )
        )
        dialog.finished.connect(lambda: self.finish(dialog))
        self.dialog = dialog
        dialog.open()

    def finish(self, dialog: QFileDialog) -> None:
        if self.dialog is dialog:
            self.dialog = None
        dialog.deleteLater()

    def load_path(self, path: str) -> bool:
        if not path or not self.available():
            return False
        try:
            value = self.validate(read_snapshot(path, self.limit))
            if not self.available():
                return False
            self.apply(value)
        except (OSError, ValueError, TypeError, RecursionError) as error:
            self.message.emit(f"Cannot load {self.title}: {error}")
            return False
        self.loaded.emit()
        self.loaded_document.emit(value, path)
        self.message.emit(f"Loaded {self.title} configuration: {path}")
        return True

    def save_path(self, path: str) -> bool:
        if not path or not self.available():
            return False
        try:
            value = self.capture()
            self.validate(value)
            write_snapshot(path, value, self.limit)
        except (OSError, ValueError, TypeError, RecursionError) as error:
            self.message.emit(f"Cannot save {self.title}: {error}")
            return False
        self.message.emit(f"Saved {self.title} configuration: {path}")
        return True
