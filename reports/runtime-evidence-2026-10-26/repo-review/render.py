"""Capture isolated Protocol and Tracking configuration views offscreen."""

import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import QCoreApplication, QEvent, QSettings
from PyQt6.QtWidgets import QApplication, QWidget

from cephvr.gui.protocol_batches import grouped_program
from cephvr.gui.protocol_document import review_program
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme, load_terminal_font
from cephvr.gui.window import DashboardWindow


OUT = Path(__file__).parent
STYLES = ("standard", "retro_console", "amber_phosphor")
FULL_SIZE = (1920, 1032)
NARROW_SIZE = (720, 950)

app = QApplication([])
apply_theme(app)
load_terminal_font()


def settle() -> None:
    for _ in range(4):
        app.processEvents()


def capture(window: DashboardWindow, style: str, view: str) -> None:
    settle()
    size = window.size()
    path = OUT / f"{style}-{view}.png"
    if not window.grab().save(str(path)):
        raise RuntimeError(f"Could not save {path}")
    print(
        f"{path}: style={style}, view={view}, "
        f"window={size.width()}x{size.height()}, "
        f"protocol={window.protocol.size().width()}x{window.protocol.size().height()}, "
        f"tracking={window.tracking.size().width()}x{window.tracking.size().height()}"
    )


def capture_card(
    window: DashboardWindow, style: str, view: str, widget: QWidget
) -> None:
    window.appearance.crt.apply(False, scanline_alpha=0)
    try:
        settle()
        size = widget.size()
        path = OUT / f"{style}-{view}.png"
        if not widget.grab().save(str(path)):
            raise RuntimeError(f"Could not save {path}")
        print(
            f"{path}: style={style}, view={view}, card={size.width()}x{size.height()}"
        )
    finally:
        window.appearance.apply_crt()


for style in STYLES:
    settings = QSettings(str(OUT / f"settings-{style}.ini"), QSettings.Format.IniFormat)
    settings.clear()
    settings.sync()
    window = DashboardWindow(sample=True, settings=settings)
    ReviewControls(window)
    editor = window.protocol.editor
    editor.set_program(grouped_program(review_program()))
    editor.enter_group()
    editor.select_epochs(((0, 1),), open_group=False)
    editor.subgroup.add_variation()
    editor.subgroup.rows[-1].values.setText("10, 20")
    window.resize(*FULL_SIZE)
    window.appearance.select(style, persist=False)
    window.show()
    window.page_buttons[1].click()
    capture(window, style, "protocol-full")
    window.page_buttons[3].click()
    capture(window, style, "tracking-configuration")
    window.page_buttons[1].click()
    window.resize(*NARROW_SIZE)
    capture(window, style, "protocol-narrow")
    capture_card(window, style, "protocol-narrow-timeline", editor.timeline_card)
    capture_card(window, style, "protocol-narrow-settings", editor.settings_card)
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()

print(
    f"Output directory: {OUT.resolve()}\n"
    f"Styles: {', '.join(STYLES)}\n"
    f"Requested page sizes: full={FULL_SIZE[0]}x{FULL_SIZE[1]}, "
    f"narrow={NARROW_SIZE[0]}x{NARROW_SIZE[1]}. "
    "No runtime or device commands were issued."
)
