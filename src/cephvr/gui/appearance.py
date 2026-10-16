"""Shared frontend appearance preference, independent of experiment configuration."""

from PyQt6.QtCore import QObject, QSettings
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QComboBox, QLineEdit, QMainWindow, QWidget

from cephvr.gui.components import Card
from cephvr.gui.dashboard import Dashboard
from cephvr.gui.retro_instruments import FocusBrackets
from cephvr.gui.theme import retro_chrome_stylesheet, retro_stylesheet


class DashboardAppearance(QObject):
    def __init__(
        self,
        window: QMainWindow,
        dashboard: Dashboard,
        header: QWidget,
        settings: QSettings | None,
    ) -> None:
        super().__init__(window)
        self.window = window
        self.dashboard = dashboard
        self.card_titles = {
            card: card.caption.text() for card in dashboard.findChildren(Card)
        }
        self.focus_brackets = [
            FocusBrackets(editor)
            for editor in dashboard.subject_card.findChildren((QLineEdit, QComboBox))
        ]
        self.settings = settings
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
        saved = (
            settings.value(
                "appearance/style", settings.value("review/appearance", "standard")
            )
            if settings
            else "standard"
        )
        self.select(str(saved), persist=False)

    def select(self, name: str, *, persist: bool = True) -> None:
        self.name = name if name in self.actions else "standard"
        retro = self.name == "retro_console"
        self.actions[self.name].setChecked(True)
        self.window.setProperty("retroConsole", retro)
        self.window.setStyleSheet(
            retro_stylesheet() + retro_chrome_stylesheet() if retro else ""
        )
        for card, title in self.card_titles.items():
            card.caption.setText(title.upper() if retro else title)
        self.dashboard.render_hud()
        for brackets in self.focus_brackets:
            brackets.refresh()
        self.dashboard.update()
        if persist and self.settings is not None:
            self.settings.setValue("appearance/style", self.name)
            self.settings.sync()
