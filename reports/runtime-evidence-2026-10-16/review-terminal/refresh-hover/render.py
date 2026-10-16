"""Render actual refresh control hover/press states with the Retro stylesheet."""
import json
from pathlib import Path
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget
from cephvr.gui.tables import refresh_button
from cephvr.gui.theme import RETRO_COLORS, apply_theme, retro_stylesheet

app = QApplication([])
apply_theme(app)
host = QWidget()
host.setProperty("retroConsole", True)
host.setStyleSheet(retro_stylesheet())
layout = QVBoxLayout(host)
control = refresh_button("Refresh devices")
layout.addWidget(control)
host.resize(110, 90)
host.show()
app.processEvents()
root = Path(__file__).parent
states = {}
for state in ("normal", "hover", "pressed", "disabled"):
    if state == "normal":
        QTest.mouseMove(host, QPoint(90, 75))
    elif state == "hover":
        QTest.mouseMove(control, control.rect().center())
    elif state == "pressed":
        QTest.mousePress(control, Qt.MouseButton.LeftButton)
    else:
        QTest.mouseRelease(control, Qt.MouseButton.LeftButton)
        control.setEnabled(False)
    app.processEvents()
    image = control.grab().toImage()
    image.save(str(root / f"{state}.png"))
    background = image.pixelColor(4, 13).name()
    states[state] = {"background": background, "under_mouse": control.underMouse()}
    if state in ("hover", "pressed"):
        assert background == RETRO_COLORS.hover, states
(root / "result.json").write_text(json.dumps(states, indent=2) + "\n")
host.close()
