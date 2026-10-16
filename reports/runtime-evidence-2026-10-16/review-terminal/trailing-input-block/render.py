"""Offscreen trailing terminal block and preserved insertion verification."""
from pathlib import Path
import json
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget
from cephvr.gui.retro_instruments import FocusBrackets, blink
from cephvr.gui.theme import apply_theme, retro_stylesheet

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
blink().timer.stop()
blink().on = True
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
host.close()
