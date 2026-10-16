"""Local Review appearance preference, independent of experiment configuration."""

from functools import cache
from importlib.resources import files

from PyQt6.QtCore import QByteArray, QObject, QSettings
from PyQt6.QtGui import QAction, QActionGroup, QFontDatabase
from PyQt6.QtWidgets import QApplication, QComboBox, QLabel, QLineEdit, QWidget

from cephvr.gui.components import Button, Card, StatusColumn
from cephvr.gui.dashboard import Dashboard
from cephvr.gui.icons import device_icon
from cephvr.gui.retro_instruments import FocusBrackets
from cephvr.gui.retro_overlay import CrtEffects
from cephvr.gui.tables import DataTable
from cephvr.gui.theme import (
    COLORS,
    RETRO_COLORS,
    retro_chrome_stylesheet,
    retro_console,
    retro_stylesheet,
)
from cephvr.gui.window import DashboardWindow


@cache
def load_terminal_font() -> None:
    """Register the packaged OFL font once, without an installed-font dependency."""
    data = (
        files("cephvr.gui")
        .joinpath("assets/fonts/IBMPlexMono-Regular.ttf")
        .read_bytes()
    )
    if QFontDatabase.addApplicationFontFromData(QByteArray(data)) < 0:
        raise RuntimeError("Cannot load bundled IBM Plex Mono font")


class ReviewAppearance(QObject):
    def __init__(
        self,
        window: DashboardWindow,
        dashboard: Dashboard,
        header: QWidget,
        settings: QSettings | None,
    ) -> None:
        super().__init__(window)
        self.window = window
        self.dashboard = dashboard
        self.surfaces = (
            dashboard,
            window.devices,
            window.tracking.status,
            window.protocol,
            dashboard.preview_dialog,
        )
        self.card_titles = {
            card: card.caption.text()
            for surface in self.surfaces
            for card in surface.findChildren(Card)
        }
        self.settings = settings
        app = QApplication.instance()
        assert isinstance(app, QApplication)
        app.focusChanged.connect(self.focus_editor)
        window.devices.tab_bar.currentChanged.connect(self.refresh_device_icons)
        load_terminal_font()
        self.brand = next(
            item
            for item in window.findChildren(QLabel)
            if item.property("role") == "brand"
        )
        self.original_brand = self.brand.text()
        header.setObjectName("WindowHeader")
        menu_bar = window.menuBar()
        assert menu_bar is not None
        menu_bar.setNativeMenuBar(False)
        menu = menu_bar.addMenu("Style")
        assert menu is not None
        group = QActionGroup(self)
        group.setExclusive(True)
        self.actions: dict[str, QAction] = {}
        for key, title in (
            ("standard", "Standard"),
            ("retro_console", "Retro console"),
        ):
            action = QAction(title, group)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, name=key: self.select(name))
            menu.addAction(action)
            self.actions[key] = action
        self.crt = CrtEffects(
            window, [window.page_title, *(card.caption for card in self.card_titles)]
        )
        self.preview_crt = CrtEffects(dashboard.preview_dialog, [])
        menu.addSeparator()
        self.crt_action = QAction("CRT effects", menu)
        self.crt_action.setCheckable(True)
        self.crt_action.setChecked(
            settings.value("review/crt", True, type=bool) if settings else True
        )
        self.crt_action.toggled.connect(self.set_crt)
        menu.addAction(self.crt_action)
        saved = (
            settings.value("review/appearance", "standard") if settings else "standard"
        )
        self.select(str(saved), persist=False)
        window.protocol.editor.timeline.screens_changed.connect(
            self.refresh_protocol_cards
        )

    def select(self, name: str, *, persist: bool = True) -> None:
        self.name = name if name in self.actions else "standard"
        self.refresh_protocol_cards()
        retro = self.name == "retro_console"
        self.actions[self.name].setChecked(True)
        self.window.setStyleSheet(retro_chrome_stylesheet() if retro else "")
        for surface in self.surfaces:
            surface.setProperty("retroConsole", retro)
            surface.setStyleSheet(retro_stylesheet() if retro else "")
            for control in surface.findChildren(Button):
                control.updateGeometry()
            for editor in surface.findChildren((QLineEdit, QComboBox)):
                if editor.findChild(FocusBrackets) is None:
                    FocusBrackets(editor)
            for table in surface.findChildren(DataTable):
                table.fit_rows()
            surface.update()
        self.brand.setText("CEPHVR" if retro else self.original_brand)
        for card, title in self.card_titles.items():
            card.caption.setText(title.upper() if retro else title)
        self.refresh_device_icons()
        for status in self.window.findChildren(StatusColumn):
            status.render_hud()
        self.dashboard.render_hud()
        # Buttons outside the Dashboard that the retro chrome styles carry the marker.
        for chrome_control in (
            *self.window.page_buttons,
            self.dashboard.preview_button,
        ):
            chrome_control.setProperty("retroConsole", retro)
            chrome_control.updateGeometry()
            chrome_control.update()
        self.dashboard.log_console.setPlaceholderText(
            "-- NO ENTRIES --" if retro else ""
        )
        self.apply_crt()
        for brackets in self.focus_brackets:
            brackets.refresh()
        if self.dashboard.preview_dialog.isVisible():
            self.dashboard.preview_dialog.fit_contents()
        self.dashboard.update()
        if persist and self.settings is not None:
            self.settings.setValue("review/appearance", self.name)
            self.settings.sync()

    def set_crt(self, enabled: bool) -> None:
        self.apply_crt()
        if self.settings is not None:
            self.settings.setValue("review/crt", enabled)
            self.settings.sync()

    def refresh_protocol_cards(self) -> None:
        """Screen rows gain their advanced cards when displays become available."""
        added = False
        for card in self.window.protocol.findChildren(Card):
            if card in self.card_titles:
                continue
            title = card.caption.text()
            self.card_titles[card] = title
            if self.name == "retro_console":
                card.caption.setText(title.upper())
            self.crt.glow_labels.append(card.caption)
            added = True
        if added:
            self.apply_crt()

    def apply_crt(self) -> None:
        enabled = self.name == "retro_console" and self.crt_action.isChecked()
        self.crt.apply(enabled)
        self.preview_crt.apply(enabled)
        for indicator in self.dashboard.backend_indicators.values():
            indicator.setProperty("crtGlow", enabled)
            indicator.update()

    def refresh_device_icons(self) -> None:
        bar = self.window.devices.tab_bar
        for index, key in enumerate(("camera", "board", "projector", "signal")):
            color = (
                (
                    RETRO_COLORS.window
                    if index == bar.currentIndex()
                    else RETRO_COLORS.accent
                )
                if self.name == "retro_console"
                else COLORS.accent
            )
            bar.setTabIcon(index, device_icon(key, color))

    @property
    def focus_brackets(self) -> list[FocusBrackets]:
        # Tables rebuild editors; query live children rather than retaining dead wrappers.
        return self.window.findChildren(FocusBrackets)

    def focus_editor(self, previous: QWidget | None, editor: QWidget | None) -> None:
        """Rows added after style selection receive the same editor decoration."""
        if not isinstance(editor, (QLineEdit, QComboBox)) or not retro_console(editor):
            return
        if not any(surface.isAncestorOf(editor) for surface in self.surfaces):
            return
        brackets = editor.findChild(FocusBrackets)
        if brackets is None:
            brackets = FocusBrackets(editor)
        brackets.refresh()
