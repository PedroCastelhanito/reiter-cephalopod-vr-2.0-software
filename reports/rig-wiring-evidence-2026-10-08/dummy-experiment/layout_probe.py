"""Inspect owning Qt layouts with the actual Windows style."""
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QApplication, QWidget
from cephvr.gui.window import DashboardWindow
from cephvr.gui.theme import apply_theme

app = QApplication([])
apply_theme(app)
window = DashboardWindow(sample=True, settings=QSettings("layout-probe.ini", QSettings.Format.IniFormat))
window.show()

def inspect(widget, depth=0):
    if depth > 10 or not widget.isVisible():
        return
    width = widget.minimumSizeHint().width()
    if width < 150:
        return
    title = getattr(widget, "text", lambda: "")()
    print(" " * depth, type(widget).__name__, str(title)[:45], "size", widget.width(), "minhint", width, "min", widget.minimumWidth())
    for child in widget.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
        inspect(child, depth + 1)

for size in (720, 1175):
    window.resize(size, 883)
    window.page_buttons[2].click()
    for index, panel in enumerate(window.devices.panels):
        window.devices.tabs.setCurrentIndex(index)
        app.processEvents()
        scroll = panel.config_scroll
        print("DEVICE", size, index, "viewport", scroll.viewport().width(), "content", scroll.widget().width(), "overflow", scroll.horizontalScrollBar().maximum())
        inspect(scroll.widget())
    window.page_buttons[1].click()
    app.processEvents()
    print("PROTOCOL", size)
    inspect(window.protocol.config_scroll.widget())
window.close()
