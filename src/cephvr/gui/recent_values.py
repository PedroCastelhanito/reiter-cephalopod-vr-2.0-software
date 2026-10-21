"""Local recent-value suggestions for free-text fields; presentation only."""

from PyQt6.QtCore import QEvent, QObject, QSettings, QStringListModel, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QCompleter, QLineEdit

from cephvr.gui.theme import suggestion_popup_stylesheet

RECENT_LIMIT = 10
VALUE_LIMIT = 80


class RecentValues:
    """Most-recent-first values kept in the local GUI settings, never in the experiment."""

    def __init__(self, settings: QSettings | None, key: str) -> None:
        self.settings = settings
        self.key = key
        self.model = QStringListModel()
        self._memory: list[str] = []
        self.model.setStringList(self.values())

    def values(self) -> list[str]:
        if self.settings is None:
            return list(self._memory)
        stored = self.settings.value(self.key, [])
        if isinstance(stored, str):
            stored = [stored]
        return [str(item) for item in stored] if isinstance(stored, list) else []

    def remember(self, value: str) -> None:
        text = value.strip()[:VALUE_LIMIT]
        if not text:
            return
        kept = [item for item in self.values() if item.casefold() != text.casefold()]
        updated = [text, *kept][:RECENT_LIMIT]
        if self.settings is None:
            self._memory = updated
        else:
            self.settings.setValue(self.key, updated)
            self.settings.sync()
        self.model.setStringList(updated)


class SuggestOnRequest(QObject):
    """Open the suggestion list from an empty field on click or Down."""

    def __init__(
        self, editor: QLineEdit, completer: QCompleter, model: QStringListModel
    ) -> None:
        super().__init__(editor)
        self.editor = editor
        self.completer = completer
        self.model = model
        editor.installEventFilter(self)
        popup = completer.popup()
        assert popup is not None
        popup.installEventFilter(self)

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
        try:
            return self.filter(watched, event)
        except RuntimeError:  # the editor was deleted while its popup was closing
            return False

    def filter(self, watched: QObject | None, event: QEvent | None) -> bool:
        if event is not None and event.type() == QEvent.Type.Show:
            popup = self.completer.popup()
            if watched is popup and popup is not None:
                popup.setStyleSheet(suggestion_popup_stylesheet(self.editor))
            return False
        if event is None or not self.editor.isEnabled() or self.editor.text():
            return False
        opens = event.type() == QEvent.Type.MouseButtonPress or (
            isinstance(event, QKeyEvent) and event.key() == Qt.Key.Key_Down
        )
        if opens and self.model.rowCount():
            self.completer.setCompletionPrefix("")
            self.completer.complete()
        return False


def suggest_values(editor: QLineEdit, recent: RecentValues) -> QCompleter:
    completer = QCompleter(recent.model, editor)
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    completer.setFilterMode(Qt.MatchFlag.MatchContains)
    completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
    editor.setCompleter(completer)
    SuggestOnRequest(editor, completer, recent.model)
    return completer
