"""Offscreen native block caret, insertion, selection and appearance verification."""
from pathlib import Path
import json
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget
from cephvr.gui.retro_instruments import FocusBrackets
from cephvr.gui.theme import apply_theme, retro_stylesheet, stylesheet

app = QApplication([])
apply_theme(app)
app.setCursorFlashTime(0)
host = QWidget()
host.setProperty("retroConsole", True)
host.setStyleSheet(retro_stylesheet())
layout = QVBoxLayout(host)
editor = QLineEdit()
layout.addWidget(editor)
focus = FocusBrackets(editor)
host.resize(300, 70)
host.show()
host.activateWindow()
editor.setFocus()
QTest.keyClicks(editor, "123")
app.processEvents()
assert editor.text() == "123" and editor.cursorPosition() == 3
root = Path(__file__).parent
host.grab().save(str(root / "typed-value.png"))
QTest.keyClick(editor, Qt.Key.Key_Home)
app.processEvents()
host.grab().save(str(root / "cursor-at-home.png"))
QTest.keyClicks(editor, "4")
assert editor.text() == "4123" and editor.cursorPosition() == 1
QTest.keyClick(editor, Qt.Key.Key_End)
assert editor.cursorPosition() == 4
(root / "result.json").write_text(json.dumps({"typing": "123", "insertion_at_home": editor.text(), "final_cursor_position": editor.cursorPosition(), "scope": "offscreen Qt; no native/DPI acceptance"}, indent=2) + "\n")

retro_width = editor.cursorRect().width()
host.setProperty("retroConsole", False)
host.setStyleSheet(stylesheet())
app.processEvents()
standard_width = editor.cursorRect().width()
assert retro_width > standard_width, (retro_width, standard_width)
host.grab().save(str(root / "standard.png"))
host.setProperty("retroConsole", True)
host.setStyleSheet(retro_stylesheet())
app.processEvents()
assert editor.cursorRect().width() == retro_width
editor.setText("1234567890" * 6)
editor.end(False)
app.processEvents()
host.grab().save(str(root / "scrolled-end.png"))
editor.selectAll()
QTest.keyClicks(editor, "5")
assert editor.text() == "5" and editor.cursorPosition() == 1
app.processEvents()
host.grab().save(str(root / "replacement.png"))
(root / "metrics.json").write_text(json.dumps({"native_cursor_rect_retro": retro_width, "native_cursor_rect_standard": standard_width, "switch_back": "passed", "selection_replace": "passed", "long_value": "rendered at End"}, indent=2) + "\n")
host.close()

