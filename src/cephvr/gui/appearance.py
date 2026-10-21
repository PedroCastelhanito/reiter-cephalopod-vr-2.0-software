"""Shared frontend appearance preference, independent of experiment configuration."""

from __future__ import annotations

import re
from functools import cache
from importlib.resources import files
from typing import TYPE_CHECKING

from PyQt6.QtCore import QByteArray, QEvent, QMargins, QObject, QSettings, Qt
from PyQt6.QtGui import QAction, QActionGroup, QFontDatabase
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabBar,
    QWidget,
)

from cephvr.gui.components import Button, Card, Console, FittedConsole, StatusColumn
from cephvr.gui.dashboard import Dashboard
from cephvr.gui.icons import device_icon
from cephvr.gui.retro_instruments import FocusBrackets, TabBrackets
from cephvr.gui.retro_overlay import (
    PHOSPHOR_SCANLINE_ALPHA,
    SCANLINE_ALPHA,
    CrtEffects,
    WindowFilms,
)
from cephvr.gui.tables import DataTable
from cephvr.gui.theme import (
    COLORS,
    RETRO_PALETTES,
    phosphor_stylesheet,
    retro_chrome_stylesheet,
    retro_console,
    retro_stylesheet,
)

if TYPE_CHECKING:
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


def caption_caps(text: str) -> str:
    """Uppercase a caption but keep parenthesised units such as (mA) or (hh:mm:ss)."""
    return re.sub(r"[^()]+(?![^(]*\))", lambda part: part[0].upper(), text)


def mark_nested(card: Card) -> None:
    """Cards inside another card render as subsections in Amber phosphor."""
    parent = card.parentWidget()
    while parent is not None and not isinstance(parent, Card):
        parent = parent.parentWidget()
    card.setProperty("nestedCard", parent is not None)


class DashboardAppearance(QObject):
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
            window.tracking,
            window.protocol,
        )
        self.card_titles = {
            card: card.caption.text()
            for surface in self.surfaces
            for card in surface.findChildren(Card)
        }
        # Subsection headings opt in with the `subsection` property; text is restored.
        self.subsections = {
            heading: heading.text()
            for heading in window.findChildren(QLabel)
            if heading.property("subsection") is True
        }
        # Field captions shown uppercase in Amber phosphor; text is restored after.
        self.field_labels = {
            caption: caption.text()
            for caption in window.findChildren(QLabel)
            if caption.property("role") == "label"
            and caption.property("subsection") is not True
        }
        self.card_margins: dict[Card, QMargins] = {}
        for card in self.card_titles:
            mark_nested(card)
        for bar in window.findChildren(QTabBar):
            TabBrackets(bar)
        self.settings = settings
        app = QApplication.instance()
        assert isinstance(app, QApplication)
        app.focusChanged.connect(self.focus_editor)
        window.devices.tab_bar.currentChanged.connect(self.refresh_device_icons)
        self.brand = next(
            item
            for item in window.findChildren(QLabel)
            if item.property("role") == "brand"
        )
        self.original_brand = self.brand.text()
        self.original_brand_alignment = self.brand.alignment()
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
            ("amber_phosphor", "Amber phosphor"),
        ):
            action = QAction(title, group)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, name=key: self.select(name))
            menu.addAction(action)
            self.actions[key] = action
        self.crt = CrtEffects(
            window, [window.page_title, *(card.caption for card in self.card_titles)]
        )
        self.window_films = WindowFilms(window)
        menu.addSeparator()
        self.crt_action = QAction("CRT effects", menu)
        self.crt_action.setCheckable(True)
        self.crt_action.setChecked(
            settings.value("review/crt", True, type=bool) if settings else True
        )
        self.crt_action.toggled.connect(self.set_crt)
        menu.addAction(self.crt_action)
        self.band_action = QAction("Refresh band", menu)
        self.band_action.setCheckable(True)
        self.band_action.setChecked(
            settings.value("review/crt_band", False, type=bool) if settings else False
        )
        self.band_action.toggled.connect(self.set_band)
        menu.addAction(self.band_action)
        saved = (
            settings.value(
                "appearance/style", settings.value("review/appearance", "standard")
            )
            if settings
            else "standard"
        )
        self.select(str(saved), persist=False)
        window.protocol.editor.timeline.screens_changed.connect(
            self.refresh_protocol_cards
        )

    def select(self, name: str, *, persist: bool = True) -> None:
        self.name = name if name in self.actions else "standard"
        retro = self.retro
        palette_name = self.name if retro else None
        colors = RETRO_PALETTES[self.name][0] if retro else COLORS
        extras = phosphor_stylesheet(colors) if self.name == "amber_phosphor" else ""
        self.refresh_protocol_cards()
        self.actions[self.name].setChecked(True)
        self.window.setProperty("retroConsole", retro)
        self.window.setProperty("retroPalette", palette_name)
        # Dialogs and tool windows inherit the complete palette from their owner.
        self.window.setStyleSheet(
            retro_stylesheet(colors) + retro_chrome_stylesheet(colors) + extras
            if retro
            else ""
        )
        for surface in self.surfaces:
            surface.setProperty("retroConsole", retro)
            surface.setProperty("retroPalette", palette_name)
            surface.setStyleSheet(retro_stylesheet(colors) + extras if retro else "")
            for control in surface.findChildren(Button):
                # Polish first so layouts never use pre-style metrics (clipped labels).
                control.ensurePolished()
                control.updateGeometry()
            for editor in surface.findChildren((QLineEdit, QComboBox)):
                if editor.findChild(FocusBrackets) is None:
                    FocusBrackets(editor)
            for table in surface.findChildren(DataTable):
                table.fit_rows()
            surface.update()
        self.brand.setText("CEPHVR" if retro else self.original_brand)
        phosphor = self.name == "amber_phosphor"
        for card, title in self.card_titles.items():
            card.caption.setText(self.card_title(title, card))
            self.align_nested(card, phosphor)
        for heading, text in self.subsections.items():
            heading.setText(f"/// {text.upper()} \\\\\\" if phosphor else text)
        for caption, text in list(self.field_labels.items()):
            if caption.text() not in (text, caption_caps(text)):
                text = self.field_labels[caption] = caption.text()  # changed by code
            caption.setText(caption_caps(text) if phosphor else text)
        # Amber phosphor names the page in the sidebar only, centred like navigation.
        self.window.page_header.setVisible(not phosphor)
        self.brand.setAlignment(
            Qt.AlignmentFlag.AlignCenter if phosphor else self.original_brand_alignment
        )
        self.refresh_device_icons()
        for console in self.window.findChildren(Console):
            console.ensurePolished()
            console.set_entry_prompts(retro)
            if isinstance(console, FittedConsole):
                console.fit_height()
        for status in self.window.findChildren(StatusColumn):
            status.console.set_column_header(phosphor)
            status.render_hud()
        self.dashboard.render_hud()
        # Buttons outside the Dashboard that the retro chrome styles carry the marker.
        for chrome_control in self.window.page_buttons:
            chrome_control.setProperty("retroConsole", retro)
            chrome_control.setProperty("retroPalette", palette_name)
            chrome_control.updateGeometry()
            chrome_control.update()
        self.dashboard.log_console.setPlaceholderText(
            "-- NO ENTRIES --" if retro else ""
        )
        # Measure after fonts and chrome are applied, including on style changes.
        header_controls = (self.window.page_title,)
        for header_control in header_controls:
            header_control.ensurePolished()
        self.window.page_header.setFixedHeight(
            max(control.sizeHint().height() for control in header_controls)
        )
        self.apply_crt()
        # Settle layouts before the first repaint; otherwise one frame keeps old card
        # heights and squeezes fixed-height controls.
        for _ in range(3):
            QApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
        for brackets in self.focus_brackets:
            brackets.refresh()
        self.dashboard.update()
        if persist and self.settings is not None:
            self.settings.setValue("appearance/style", self.name)
            self.settings.sync()

    def set_crt(self, enabled: bool) -> None:
        self.apply_crt()
        if self.settings is not None:
            self.settings.setValue("review/crt", enabled)
            self.settings.sync()

    def set_band(self, enabled: bool) -> None:
        self.apply_crt()
        if self.settings is not None:
            self.settings.setValue("review/crt_band", enabled)
            self.settings.sync()

    def refresh_protocol_cards(self) -> None:
        """Screen rows gain their advanced cards when displays become available."""
        added = False
        for card in self.window.protocol.findChildren(Card):
            if card in self.card_titles:
                continue
            title = card.caption.text()
            self.card_titles[card] = title
            mark_nested(card)
            card.caption.setText(self.card_title(title, card))
            self.align_nested(card, self.name == "amber_phosphor")
            self.crt.glow_labels.append(card.caption)
            added = True
        if added:
            self.apply_crt()

    def apply_crt(self) -> None:
        enabled = self.retro and self.crt_action.isChecked()
        band = self.band_action.isChecked()
        alpha = (
            PHOSPHOR_SCANLINE_ALPHA if self.name == "amber_phosphor" else SCANLINE_ALPHA
        )
        self.crt.apply(enabled, band=band, scanline_alpha=alpha)
        self.window_films.set(enabled, alpha)
        self.dashboard.preview_workspace.restyle(enabled)

    def refresh_device_icons(self) -> None:
        bar = self.window.devices.tab_bar
        for index, key in enumerate(("camera", "board", "projector", "signal")):
            colors = RETRO_PALETTES[self.name][0] if self.retro else COLORS
            selected = colors.coral if self.name == "amber_phosphor" else colors.window
            color = (
                selected
                if self.retro and index == bar.currentIndex()
                else colors.accent
            )
            bar.setTabIcon(index, device_icon(key, color))
        self.window.devices.rail.refresh_icons()
        accent = (RETRO_PALETTES[self.name][0] if self.retro else COLORS).accent
        for control in self.window.findChildren(QPushButton):
            name = control.property("iconName")
            if isinstance(name, str):
                control.setIcon(device_icon(name, accent))

    def align_nested(self, card: Card, phosphor: bool) -> None:
        """Phosphor nested cards drop their inset so content aligns with the parent."""
        margins = self.card_margins.setdefault(card, card.body.contentsMargins())
        flat = phosphor and card.property("nestedCard") is True
        card.body.setContentsMargins(QMargins() if flat else margins)
        card.caption.setContentsMargins(0 if flat else 6, 0, 0 if flat else 6, 0)

    def card_title(self, title: str, card: Card | None = None) -> str:
        """Display-only card caption for the selected style; stored titles stay."""
        if self.name == "amber_phosphor":
            if card is not None and card.property("nestedCard") is True:
                return f"/// {title.upper()} \\\\\\"
            return f"< {title.upper()} >"
        return title.upper() if self.retro else title

    @property
    def retro(self) -> bool:
        """Retro-family styles share geometry and decoration; palettes differ."""
        return self.name in RETRO_PALETTES

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
