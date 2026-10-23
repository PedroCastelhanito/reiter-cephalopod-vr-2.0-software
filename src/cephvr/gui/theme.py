"""G02 visual tokens, shared by every frontend component."""

from dataclasses import dataclass, replace
from functools import cache
from importlib.resources import files

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPalette, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QLineEdit,
    QProxyStyle,
    QStyle,
    QStyleOption,
    QWidget,
)


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


@dataclass(frozen=True)
class Palette:
    window: str = "#081018"
    page: str = "#09121a"
    sidebar: str = "#0d151d"
    card: str = "#121c25"
    input: str = "#0c141b"
    border: str = "#2a3947"
    input_border: str = "#2b3d4c"
    text: str = "#f4f7fb"
    muted: str = "#8ea3b8"
    label: str = "#9bb0c3"
    accent: str = "#8ec7ff"
    coral: str = "#ff8b82"
    projection: str = "#d9ac65"
    footprint: str = "#c09bf3"
    mirror: str = "#86cfc7"
    focus: str = "#78b5f0"
    hover: str = "#16222d"
    active: str = "#183246"
    selection: str = "#142837"
    primary: str = "#215b85"
    primary_hover: str = "#2b70a1"
    secondary: str = "#182634"
    danger: str = "#402224"
    danger_border: str = "#b36c66"
    console: str = "#08121a"
    console_text: str = coral
    ready: str = "#61c554"
    waiting: str = "#f4bf4f"
    error: str = "#ff6a6a"
    disabled: str = "#526575"


@dataclass(frozen=True)
class Metrics:
    tool_window_gap: int = 12
    page_margin: int = 20
    card_gap: int = 14
    column_gap: int = 16
    card_padding: int = 16
    card_top: int = 14
    compact_card_padding: int = 12
    compact_card_top: int = 8
    table_cell_padding: int = 12
    field_x_gap: int = 10
    field_y_gap: int = 8
    section_toggle_gap: int = 8
    card_radius: int = 16
    button_radius: int = 12
    field_radius: int = 10
    body_font: int = 14
    label_font: int = 12
    title_font: int = 17
    console_font: int = 12
    sidebar_width: int = 262
    controls_min_width: int = 300
    controls_max_width: int = 620
    status_min_width: int = 220
    wide_breakpoint: int = 760


COLORS = Palette()
SIZES = Metrics()

RETRO_COLORS = Palette(
    window="#0b1213",
    page="#0c1415",
    sidebar="#091011",
    card="#101c1d",
    input="#0a1214",
    border="#2d6e91",
    input_border="#2b5064",
    text="#c5ded3",
    muted="#86a7a8",
    label="#93bebf",
    accent="#7fd6d4",
    coral="#df7960",
    projection="#dfac6f",
    mirror="#b7dd9c",
    focus="#57b6d1",
    hover="#172e32",
    active="#19363e",
    selection="#163039",
    primary="#18465b",
    primary_hover="#1f5a70",
    secondary="#13262c",
    danger="#3a2521",
    danger_border="#dc865e",
    console="#091113",
    console_text="#bdcf9c",
    ready="#b7dd9c",
    waiting="#e0b871",
    error="#ef8b70",
    disabled="#557174",
)
# Identity tints for Retro stimulus tiles, drawn from the existing accents.
RETRO_TINTS = (
    RETRO_COLORS.accent,
    RETRO_COLORS.projection,
    RETRO_COLORS.error,
    RETRO_COLORS.mirror,
)
# Amber phosphor (satellite HUD): red-orange titles, pale-gold values and HUD/log text
# over dim amber labels, dim frames with bright corner brackets, amber focus, orange
# inverse fills and cream ready lamps on cool near-black.
PHOSPHOR_COLORS = Palette(
    window="#191f21",
    page="#191f21",
    sidebar="#161b1d",
    card="#191f21",
    input="#14191b",
    border="#82592b",
    input_border="#94673a",
    text="#ffd184",
    muted="#c18c50",
    label="#bf8a50",
    accent="#ff9f40",
    coral="#ff6a45",
    projection="#ffd27a",
    footprint="#ff5a40",
    mirror="#ffd184",
    focus="#ffb85c",
    hover="#2a2116",
    active="#14191b",
    selection="#14191b",
    primary="#191f21",
    primary_hover="#2a2116",
    secondary="#191f21",
    danger="#191f21",
    danger_border="#ff5a40",
    console="#14191b",
    console_text="#ffd184",
    ready="#ffe7b0",
    waiting="#ff9f40",
    error="#ff5a40",
    disabled="#9a7b52",
)
# Buttons rest as outlined boxes over a faint tint and fill only on hover:
# (resting tint, hover fill, outline/text).
PHOSPHOR_BUTTON = ("transparent", "#e0872e", "#ff9f40")
PHOSPHOR_STOP_BUTTON = ("transparent", "#ee6a52", "#ff6a50")
# Unselected tab text and icons stay dim so the bracketed current tab stands out.
PHOSPHOR_TAB_DIM = "#b0844f"
# Left padding that leaves room for the `>` tab marker before icon and text.
PHOSPHOR_TAB_GUTTER = 16
PHOSPHOR_TINTS = (
    PHOSPHOR_COLORS.accent,
    "#d98a5a",
    PHOSPHOR_COLORS.error,
    PHOSPHOR_COLORS.projection,
)
# Retro-family styles share Retro geometry and decoration; only the palette differs.
RETRO_PALETTES = {
    "retro_console": (RETRO_COLORS, RETRO_TINTS),
    "amber_phosphor": (PHOSPHOR_COLORS, PHOSPHOR_TINTS),
}


def retro_style(widget: QWidget) -> str:
    """Owning Retro-family style; the appearance marks surfaces with `retroPalette`."""
    current: QWidget | None = widget
    while current is not None:
        name = current.property("retroPalette")
        if name in RETRO_PALETTES:
            return str(name)
        current = current.parentWidget()
    return "retro_console"


def minimal_frames(widget: QWidget) -> bool:
    """Amber phosphor draws single-line frames with corner brackets."""
    return retro_style(widget) == "amber_phosphor"


def retro_colors(widget: QWidget) -> Palette:
    return RETRO_PALETTES[retro_style(widget)][0]


def retro_tints(widget: QWidget) -> tuple[str, ...]:
    return RETRO_PALETTES[retro_style(widget)][1]


RETRO_SIZES = replace(
    SIZES,
    card_radius=0,
    button_radius=0,
    field_radius=1,
    title_font=15,
    body_font=13,
    console_font=13,
)
RETRO_FONT = "'IBM Plex Mono', 'Menlo', 'Consolas', 'DejaVu Sans Mono', monospace"


def retro_console(widget: QWidget) -> bool:
    """Use the owning frontend appearance for custom instrument painting."""
    current: QWidget | None = widget
    while current is not None:
        if current.property("retroConsole") is True:
            return True
        current = current.parentWidget()
    return False


def colors_for(widget: QWidget) -> Palette:
    return retro_colors(widget) if retro_console(widget) else COLORS


def stylesheet(
    colors: Palette = COLORS,
    metrics: Metrics = SIZES,
    font_family: str = "'Segoe UI', 'Helvetica Neue'",
) -> str:
    c, s = colors, metrics
    return f"""
    QWidget {{ color: {c.text}; font-family: {font_family};
               font-size: {s.body_font}px; }}
    QMainWindow, QDialog, QWidget#Shell {{ background: {c.window}; }}
    QWidget#Page {{ background: {c.page}; }}
    QFrame#Sidebar {{ background: {c.sidebar}; border-right: 1px solid {c.border}; }}
    QLabel {{ background: transparent; }}
    QLabel[role='brand'] {{ font-size: 23px; font-weight: 700; }}
    QLabel[role='title'] {{ font-size: {s.title_font}px; font-weight: 700; }}
    QLabel[role='eyebrow'] {{ color: {c.coral}; font-size: {s.title_font}px;
                            font-weight: 700; letter-spacing: 1.2px; }}
    QLabel[role='label'] {{ color: {c.label}; font-size: {s.label_font}px;
                          font-weight: 700; letter-spacing: 0.8px; }}
    QLabel[role='muted'] {{ color: {c.muted}; font-size: {s.label_font}px; }}
    QLabel[role='hint'] {{ color: {c.muted}; }}
    QLabel[role='error'] {{ color: {c.danger_border}; font-size: {s.label_font}px; }}
    QMenuBar {{ background: {c.sidebar}; color: {c.text};
                border-bottom: 1px solid {c.border}; spacing: 4px; }}
    QMenuBar::item {{ background: transparent; color: {c.text}; padding: 6px 10px; }}
    QMenuBar::item:selected {{ background: {c.selection}; color: {c.text}; }}
    QMenuBar::item:pressed {{ background: {c.active}; color: {c.text}; }}
    QMenuBar::item:disabled {{ color: {c.disabled}; }}
    QMenu {{ background: {c.card}; color: {c.text};
             border: 1px solid {c.border}; padding: 4px; }}
    QMenu::item {{ background: transparent; color: {c.text}; padding: 6px 24px; }}
    QMenu::item:selected {{ background: {c.selection}; color: {c.text}; }}
    QMenu::item:disabled {{ color: {c.disabled}; }}
    QMenu::separator {{ height: 1px; background: {c.border}; margin: 4px 8px; }}
    QFrame[role='card'] {{ background: transparent; border: none; }}
    QFrame[role='section-divider'] {{ background: {c.border}; border: none; }}
    QFrame[role='banner'] {{ background: {c.active}; border: 1px solid {c.input_border};
                            border-radius: {s.field_radius}px; }}
    QPushButton {{ background: {c.secondary}; border: 1px solid {c.input_border};
                  border-radius: {s.button_radius}px; padding: 10px 12px;
                  font-weight: 700; }}
    QPushButton[role='icon'] {{ padding: 0; border-radius: 6px; background: transparent; border-color: transparent; }}
    QPushButton[role='icon']::menu-indicator {{ image: none; width: 0; }}
    QPushButton:hover {{ background: {c.hover}; border-color: {c.focus}; }}
    QPushButton:pressed {{ background: {c.window}; }}
    QPushButton:focus {{ border-color: {c.focus}; }}
    QPushButton[role='primary'] {{ background: {c.primary}; border-color: {c.focus}; }}
    QPushButton[role='primary']:hover {{ background: {c.primary_hover}; }}
    QPushButton[role='danger'] {{ background: {c.danger}; border-color: {c.danger_border}; }}
    QPushButton[role='compact-stop'] {{ background: {c.danger}; border-color: {c.danger_border}; }}
    QPushButton[role='compact'], QPushButton[role='compact-stop'] {{ padding: 7px 10px; font-size: {s.label_font}px; }}
    QPushButton[role='navigation'] {{ background: transparent; color: {c.muted};
                                     text-align: left; padding: 14px 12px; }}
    QPushButton[role='navigation']:checked {{ background: {c.selection};
                                             color: {c.coral}; border-color: {c.accent}; }}
    QPushButton[toggle='on']:checked:enabled {{ background: {c.primary};
                                               border-color: {c.focus}; }}
    QPushButton:disabled {{ background: {c.window}; color: {c.disabled};
                           border-color: {c.border}; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background: {c.input}; border: 1px solid {c.input_border};
        border-radius: {s.field_radius}px; padding: 8px 10px; min-height: 18px;
        selection-background-color: {c.selection}; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {c.focus}; }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
        color: {c.muted}; background: {c.window}; }}
    QLineEdit[invalid='true'] {{ border-color: {c.danger_border}; }}
    QLineEdit[role='point-coordinate'] {{ background: transparent; border-color: transparent;
                                        border-radius: 6px; padding: 7px 4px; }}
    QLineEdit[role='point-coordinate']:hover {{ background: {c.hover}; }}
    QLineEdit[role='point-coordinate']:focus {{ background: {c.card}; border-color: {c.focus}; }}
    QLineEdit[role='point-coordinate']:disabled {{ background: transparent; color: {c.disabled}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox[chevron="true"]::down-arrow {{ image: none; }}
    QComboBox QAbstractItemView {{ background: {c.input}; color: {c.text};
                                 selection-background-color: {c.selection}; }}
    QCheckBox {{ spacing: 7px; }}
    QCheckBox::indicator {{ width: 15px; height: 15px; border-radius: 4px; }}
    QCheckBox::indicator:unchecked {{ background: {c.input}; border: 1px solid {c.input_border}; }}
    QCheckBox::indicator:checked {{ background: {c.accent}; border: 1px solid {c.focus}; }}
    QCheckBox:disabled {{ color: {c.muted}; }}
    QTabWidget::pane {{ border: none; background: transparent; }}
    QTabWidget > QWidget {{ background: transparent; }}
    QTabBar::tab {{ background: {c.card}; color: {c.muted}; border: 1px solid {c.border};
                    border-radius: 8px; padding: 9px 5px; margin-right: 4px; }}
    QTabBar::tab:last {{ margin-right: 0; }}
    QTabBar::tab:selected {{ color: {c.coral}; background: {c.selection}; border-color: {c.accent}; }}
    QTabBar::tab:hover {{ border-color: {c.focus}; }}
    QTreeWidget[role='rail'] {{ background: transparent; border: none; outline: none; }}
    QTreeWidget[role='rail']::item {{ color: {c.muted}; padding: 9px 8px;
        border: 1px solid transparent; border-radius: {s.field_radius}px; }}
    QFrame#Sidebar QTreeWidget[role='rail'] {{ font-size: 12px; }}
    QFrame#Sidebar QTreeWidget[role='rail']::item {{ padding: 6px 6px; margin: 3px 0;
        background: transparent; border: 1px solid transparent;
        border-left: 2px solid transparent; border-radius: 0; }}
    QFrame#Sidebar QTreeWidget[role='rail']::item:hover {{ color: {c.label};
        background: transparent; border-color: transparent; }}
    QFrame#Sidebar QTreeWidget[role='rail']::item:selected,
    QFrame#Sidebar QTreeWidget[role='rail']::item:selected:hover {{ color: {c.text};
        background: transparent; border-color: transparent; border-left-color: {c.accent}; }}
    QTreeWidget[role='rail']::item:hover {{ border-color: {c.focus}; }}
    QTreeWidget[role='rail']::item:selected {{ background: {c.selection}; color: {c.coral};
        border-color: {c.accent}; }}
    QLabel[role='selector-heading'] {{ color: {c.accent}; font-size: {s.label_font}px;
                                       font-weight: 700; min-height: 20px; }}
    QLabel[role='selector-source'] {{ color: {c.text}; min-height: 22px; }}
    QLabel:disabled, QLabel[role='label']:disabled, QLabel[role='selector-source']:disabled {{ color: {c.disabled}; }}
    QCheckBox[role='viewer-toggle'] {{ padding: 3px; border: 1px solid transparent;
                                      border-radius: 6px; }}
    QCheckBox[role='viewer-toggle']:hover {{ background: {c.hover}; }}
    QCheckBox[role='viewer-toggle']:focus {{ border-color: {c.focus}; }}
    QRadioButton[role='status-indicator'] {{ background: transparent; spacing: 8px; color: {c.muted}; }}
    QRadioButton[role='status-indicator']::indicator {{ width: 12px; height: 12px;
        border-radius: 7px; border: 1px solid {c.input_border}; background: {c.input}; }}
    QRadioButton[role='status-indicator']::indicator:checked {{ background: {c.ready}; border-color: {c.ready}; }}
    QPlainTextEdit[role='source'] {{ background: {c.input}; color: {c.text};
        border: 1px solid {c.input_border}; border-radius: {s.field_radius}px;
        padding: 8px; font-family: monospace; }}
    QPlainTextEdit[role='source']:focus {{ border-color: {c.focus}; }}
    QPlainTextEdit[role='source']:disabled {{ color: {c.disabled}; }}
    QPlainTextEdit[role='console'] {{ background: {c.console}; color: {c.console_text};
        border: 1px solid {c.input_border}; border-radius: {s.button_radius}px;
        font-family: 'Consolas', 'Courier New', monospace;
        font-size: {s.console_font}px; padding: 8px; }}
    QTextEdit {{ background: {c.console}; color: {c.console_text};
        selection-background-color: {c.selection}; selection-color: {c.text}; }}
    QListWidget[role='trials'] {{ background: transparent; border: none; outline: none; }}
    QListWidget[role='trials']::item {{ color: {c.text}; padding: 12px 40px 12px 8px; border-radius: 6px; }}
    QListWidget[role='trials']::item:selected {{ background: {c.selection}; }}
    QTableWidget {{ background: {c.input}; border: 1px solid {c.input_border};
                   border-radius: {s.field_radius}px; gridline-color: transparent; }}
    QHeaderView {{ background: transparent; }}
    QHeaderView::section {{ background: {c.active}; color: {c.accent}; border: none;
                           font-size: {s.label_font}px; font-weight: 700; padding: 8px {s.table_cell_padding}px; }}
    QHeaderView::section:first {{ border-top-left-radius: {s.field_radius}px; }}
    QHeaderView::section:last {{ border-top-right-radius: {s.field_radius}px; }}
    QTableView::item {{ padding: 6px {s.table_cell_padding}px; }}
    QTableView::item:selected {{ background: {c.selection}; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ width: 0px; }}
    QScrollBar:horizontal {{ height: 0px; }}
    QScrollBar#ConsoleLogScroll:vertical {{ width: 10px; background: {c.console}; border-radius: 4px; }}
    QScrollBar#ConsoleLogScroll::handle:vertical {{ background: {c.border}; min-height: 24px; border-radius: 4px; }}
    QScrollBar#ConsoleLogScroll::handle:vertical:hover {{ background: {c.muted}; }}
    QScrollBar#TimelineScroll:horizontal {{ height: 10px; background: {c.input}; border-radius: 5px; }}
    QScrollBar#TimelineScroll::handle:horizontal {{ background: {c.border}; min-width: 28px; border-radius: 5px; }}
    QScrollBar#TimelineScroll::handle:horizontal:hover {{ background: {c.muted}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0px; height: 0px; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QTableCornerButton::section {{ background: {c.active}; border: none; }}
    QProgressBar {{ background: {c.input}; border: 1px solid {c.input_border};
                   border-radius: 6px; min-height: 14px; text-align: center; }}
    QProgressBar::chunk {{ background: {c.primary}; border-radius: 5px; }}
    QToolTip {{ background: {c.card}; color: {c.text}; border: 1px solid {c.focus}; padding: 6px; }}
    QWidget#PreviewWorkspace QLabel[role='eyebrow'],
    QWidget#PreviewWorkspace QFrame[role='card'] QLabel[role='title'] {{ color: {c.coral}; }}
    QWidget#PreviewWorkspace QLabel[role='eyebrow']:disabled {{ color: {c.disabled}; }}
    QWidget#PreviewWorkspace QLabel[role='muted'] {{ color: {c.label}; }}
    QWidget#PreviewWorkspace QFrame#PreviewToggles {{ border: 1px solid {c.border};
        border-radius: {s.field_radius}px; }}
    QWidget#PreviewWorkspace QFrame#ProjectorCard {{ border: 1px solid {c.border};
        border-radius: {s.field_radius}px; }}
    """


def retro_stylesheet(c: Palette = RETRO_COLORS) -> str:
    return (
        stylesheet(c, RETRO_SIZES, RETRO_FONT)
        + f"""
    QTabBar::tab {{ border-radius: 0; }}
    QFrame[role='planner-divider'] {{ background: {c.border}; border: none; }}
    QFrame[role='card'] QLabel[role='title'] {{ color: {c.coral}; letter-spacing: 1px; font-size: 14px; }}
    QLabel[role='label'] {{ letter-spacing: 1px; }}
    QLineEdit, QComboBox {{ color: {c.text}; }}
    QPushButton {{ letter-spacing: 0.8px; }}
    QTabBar::tab {{ border-radius: 0; }}
    QPushButton:pressed {{ background: {c.active}; border: 1px solid {c.accent}; }}
    QCheckBox::indicator {{ border-radius: 0; width: 13px; height: 13px; }}
    QCheckBox::indicator:checked {{ background: {c.ready}; border-color: {c.ready}; }}
    QRadioButton[role='status-indicator']::indicator {{ border-radius: 0; width: 8px; height: 8px; }}
    QRadioButton[role='status-indicator'] {{ min-height: 36px; }}
    QPlainTextEdit[role='console'] {{ font-family: {RETRO_FONT}; padding: 6px 8px;
        border: 1px solid {c.input_border}; border-radius: 0; }}
    QPlainTextEdit[terminal='telemetry'] {{ color: {c.mirror}; }}
    QPushButton:hover, QPushButton[role='primary']:hover {{
        background: {c.accent}; color: {c.window}; border-color: {c.accent}; }}
    QPushButton[toggle='on']:checked:enabled {{
        background: {c.accent}; color: {c.window}; border-color: {c.accent}; }}
    QPushButton[role='danger']:hover, QPushButton[role='compact-stop']:hover {{
        background: {c.danger_border}; color: {c.window}; border-color: {c.danger_border}; }}
    QPushButton[role='icon']:hover, QPushButton[role='icon']:pressed {{
        background: {c.hover}; border-color: {c.accent}; }}
    QPushButton:disabled:hover {{ background: {c.window}; color: {c.disabled};
        border-color: {c.border}; }}
    QLineEdit, QComboBox, QPlainTextEdit[role='console'], QTextEdit {{
        selection-background-color: {c.accent}; selection-color: {c.window}; }}
    QComboBox QAbstractItemView {{
        selection-background-color: {c.accent}; selection-color: {c.window}; }}
    QMenu::item:selected {{ background: {c.accent}; color: {c.window}; }}
    QListWidget[role='trials']::item {{ border-radius: 0; }}
    QListWidget[role='trials']::item:selected {{ background: {c.accent}; color: {c.window}; }}
    QScrollBar#ConsoleLogScroll:vertical, QScrollBar#ConsoleLogScroll::handle:vertical,
    QScrollBar#TimelineScroll:horizontal, QScrollBar#TimelineScroll::handle:horizontal {{
        border-radius: 0; }}
    QTableView::item:selected {{ background: {c.primary}; color: {c.text}; }}
    QTabBar::tab:selected {{ background: {c.accent}; color: {c.window}; }}
    QTreeWidget[role='rail']::item:selected {{ background: {c.accent}; color: {c.window}; }}
    """
    )


def suggestion_popup_stylesheet(editor: QWidget) -> str:
    """Completer popups are top-level widgets, so they take the style explicitly."""
    retro = retro_console(editor)
    c = colors_for(editor)
    family = RETRO_FONT if retro else "'Segoe UI', 'Helvetica Neue'"
    selected = (
        f"background: {c.accent}; color: {c.window};"
        if retro
        else f"background: {c.selection}; color: {c.text};"
    )
    return f"""
    QListView {{ background: {c.input}; color: {c.text}; border: 1px solid {c.border};
        font-family: {family}; font-size: {RETRO_SIZES.body_font if retro else SIZES.body_font}px;
        outline: none; padding: 2px; }}
    QListView::item {{ padding: 6px 10px; }}
    QListView::item:selected {{ {selected} }}
    """


def retro_chrome_stylesheet(c: Palette = RETRO_COLORS) -> str:
    return f"""
    QMainWindow, QWidget#Shell, QWidget#Page {{ background: {c.page}; }}
    QFrame#Sidebar {{ background: {c.sidebar}; border-right: 1px solid {c.border}; }}
    QFrame#Sidebar QLabel, QWidget#WindowHeader QLabel {{
        font-family: {RETRO_FONT}; color: {c.accent}; }}
    QFrame#Sidebar QLabel[role='muted'] {{ color: {c.muted}; font-size: 11px; }}
    QFrame#Sidebar QLabel[role='brand'] {{ color: {c.projection}; }}
    QFrame#Sidebar QLabel[role='brand'] {{ font-size: 19px; font-weight: 600;
        letter-spacing: 2px; padding: 0 0 12px 0;
        border-bottom: 1px solid {c.border}; }}
    QFrame#Sidebar QPushButton {{ font-family: {RETRO_FONT}; font-size: 13px;
        color: {c.muted}; border-radius: 0; border: 1px solid transparent; }}
    QFrame#Sidebar QPushButton:checked, QFrame#Sidebar QPushButton:hover {{
        color: {c.window}; background: {c.accent}; border: 1px solid {c.accent}; }}
    QWidget#WindowHeader QPushButton {{ font-family: {RETRO_FONT}; color: {c.focus};
        background: {c.secondary}; border: 1px solid {c.input_border}; border-radius: 1px; }}
    QWidget#WindowHeader QPushButton:hover {{
        color: {c.window}; background: {c.accent}; border-color: {c.accent}; }}
    QMenuBar, QMenu {{ font-family: {RETRO_FONT}; color: {c.text}; background: {c.sidebar}; }}
    QMenuBar {{ border-bottom: 1px solid {c.border}; }}
    QMenuBar::item, QMenu::item {{ color: {c.text}; }}
    QMenuBar::item:selected, QMenu::item:selected {{ background: {c.accent}; color: {c.window}; }}
    QMenu {{ border: 1px solid {c.border}; }}
    """


def phosphor_stylesheet(c: Palette = PHOSPHOR_COLORS) -> str:
    """Amber phosphor refinements over the Retro sheets: wide-tracked regular headings,
    underlined fields, unboxed HUD/log text, inset checkboxes and bracketed
    navigation (brackets are painted by the navigation button)."""
    (tint, fill, ink), (stop_tint, stop_fill, stop_ink) = (
        PHOSPHOR_BUTTON,
        PHOSPHOR_STOP_BUTTON,
    )
    return f"""
    QLabel[role='title'], QLabel[role='eyebrow'], QLabel[role='label'],
    QLabel[role='selector-heading'], QHeaderView::section {{
        font-weight: 400; letter-spacing: 2px; }}
    QFrame[role='card'] QLabel[role='title'] {{ color: {c.coral}; letter-spacing: 2px; }}
    QPushButton, QPushButton[role='primary'], QPushButton[role='compact'] {{
        font-weight: 400; background: {tint}; color: {ink};
        border: 1px solid {ink}; }}
    QPushButton:hover, QPushButton[role='primary']:hover,
    QPushButton[role='compact']:hover {{ background: {fill}; color: {c.window};
        border-color: {fill}; }}
    QPushButton:pressed, QPushButton[role='primary']:pressed {{ background: {c.label};
        color: {c.window}; border-color: {c.label}; }}
    QPushButton[role='danger'], QPushButton[role='compact-stop'],
    QPushButton[stopAction='true'] {{ background: {stop_tint}; color: {stop_ink};
        border-color: {stop_fill}; }}
    QPushButton[role='danger']:hover, QPushButton[role='compact-stop']:hover,
    QPushButton[stopAction='true']:hover {{ background: {stop_fill};
        color: {c.window}; border-color: {stop_fill}; }}
    QPushButton[toggle='on'] {{ background: transparent; color: {c.text};
        border-color: {c.input_border}; }}
    QPushButton[toggle='on']:checked:enabled {{ background: {fill}; color: {c.window};
        border-color: {fill}; }}
    QPushButton:disabled, QPushButton:disabled:hover,
    QPushButton[role='primary']:disabled, QPushButton[role='danger']:disabled,
    QPushButton[role='compact']:disabled, QPushButton[role='compact-stop']:disabled,
    QPushButton[stopAction='true']:disabled {{ background: transparent;
        color: {c.disabled}; border-color: {c.input_border}; }}
    QPushButton[role='icon'] {{ background: transparent; border-color: transparent; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: transparent;
        border: none; border-bottom: 1px solid {c.input_border}; padding-left: 2px; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border-bottom: 1px solid {c.focus}; }}
    QLineEdit[invalid='true'] {{ border-bottom: 1px solid {c.danger_border}; }}
    QLineEdit, QPlainTextEdit {{ placeholder-text-color: {PHOSPHOR_TAB_DIM}; }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
        background: transparent; color: {c.disabled};
        border-bottom: 1px solid {c.border}; }}
    QPlainTextEdit[role='console'] {{ border: none; background: transparent; }}
    QCheckBox::indicator {{ width: 7px; height: 7px; padding: 3px; }}
    QCheckBox::indicator:unchecked {{ background: transparent;
        border: 1px solid {c.input_border}; }}
    QCheckBox::indicator:checked {{ background: {c.accent}; border: 1px solid {c.accent};
        background-clip: content; }}
    QCheckBox:hover {{ color: {c.text}; }}
    QCheckBox::indicator:unchecked:hover {{ border: 1px solid {c.accent}; }}
    QCheckBox::indicator:checked:hover {{ background: {c.focus};
        border: 1px solid {c.focus}; }}
    QCheckBox:disabled:hover {{ color: {c.muted}; }}
    QFrame#Sidebar QPushButton, QFrame#Sidebar QPushButton:checked,
    QFrame#Sidebar QPushButton:hover {{ background: transparent;
        border: 1px solid transparent; text-align: left; }}
    QFrame#Sidebar QPushButton:checked, QFrame#Sidebar QPushButton:checked:hover {{ color: {c.coral}; }}
    QFrame#Sidebar QPushButton:hover {{ color: {c.text}; }}
    QFrame#Sidebar QLabel[role='brand'] {{ color: {c.coral}; font-weight: 400;
        letter-spacing: 4px; }}
    QListWidget[role='trials']::item:selected,
    QTreeWidget[role='rail']::item:selected {{ background: {c.active}; color: {c.text};
        border: 1px solid {c.accent}; }}
    QFrame#Sidebar QTreeWidget[role='rail']::item {{ color: {PHOSPHOR_TAB_DIM};
        padding: 6px 20px 6px 20px; }}
    QFrame#Sidebar QTreeWidget[role='rail']::item:hover {{ color: {c.text}; }}
    QFrame#Sidebar QTreeWidget[role='rail']::item:selected,
    QFrame#Sidebar QTreeWidget[role='rail']::item:selected:hover {{ color: {c.coral};
        border-left-color: transparent; }}
    QTabBar::tab, QTabBar::tab:selected, QTabBar::tab:hover {{ background: transparent;
        border: 1px solid transparent; }}
    QTabBar::tab {{ color: {PHOSPHOR_TAB_DIM}; padding-left: {PHOSPHOR_TAB_GUTTER}px;
        padding-right: {PHOSPHOR_TAB_GUTTER}px; }}
    QTabBar::tab:hover {{ color: {c.text}; }}
    QTabBar::tab:selected, QTabBar::tab:selected:hover {{ color: {c.coral}; }}
    QHeaderView::section {{ background: transparent; color: {c.muted}; border: none;
        border-bottom: 1px dashed {c.border}; font-weight: 400; }}
    QTableCornerButton::section {{ background: transparent; border: none; }}
    QTableWidget {{ background: transparent; border: none; }}
    QComboBox {{ combobox-popup: 0; }}
    QComboBoxPrivateContainer, QComboBox QAbstractItemView {{ background: {c.input};
        color: {c.text}; border: 1px solid {c.input_border}; outline: none; }}
    QComboBox QAbstractItemView {{ selection-background-color: {c.hover};
        selection-color: {c.accent}; }}
    QComboBox QAbstractItemView::item:selected {{ background: {c.hover};
        color: {c.accent}; }}
    QFrame[nestedCard='true'] QLabel[role='title'] {{ color: {c.label}; }}
    QWidget#PreviewWorkspace QFrame#ProjectorCard {{ border: none; }}
    """


# Message-box glyph and colour per standard icon, drawn in the Amber palette.
PHOSPHOR_DIALOG_ICONS = {
    QStyle.StandardPixmap.SP_MessageBoxInformation: ("i", "accent"),
    QStyle.StandardPixmap.SP_MessageBoxQuestion: ("?", "accent"),
    QStyle.StandardPixmap.SP_MessageBoxWarning: ("!", "accent"),
    QStyle.StandardPixmap.SP_MessageBoxCritical: ("×", "error"),
}


def phosphor_dialog_icon(glyph: str, ink: str, ratio: float) -> QIcon:
    size = 32
    pixmap = QPixmap(int(size * ratio), int(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setPen(QColor(ink))
    painter.drawRect(QRectF(1.5, 1.5, size - 3, size - 3))
    font = QFont("IBM Plex Mono")
    font.setPixelSize(20)
    painter.setFont(font)
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, glyph)
    painter.end()
    return QIcon(pixmap)


class EditorCursorStyle(QProxyStyle):
    """Let Qt own insertion, scrolling and blinking for the Retro block caret."""

    def standardIcon(
        self,
        standard_icon: QStyle.StandardPixmap,
        option: QStyleOption | None = None,
        widget: QWidget | None = None,
    ) -> QIcon:
        if (
            widget is not None
            and standard_icon in PHOSPHOR_DIALOG_ICONS
            and retro_console(widget)
            and minimal_frames(widget)
        ):
            glyph, key = PHOSPHOR_DIALOG_ICONS[standard_icon]
            return phosphor_dialog_icon(
                glyph, getattr(retro_colors(widget), key), widget.devicePixelRatioF()
            )
        return super().standardIcon(standard_icon, option, widget)

    def pixelMetric(
        self,
        metric: QStyle.PixelMetric,
        option: QStyleOption | None = None,
        widget: QWidget | None = None,
    ) -> int:
        if (
            metric == QStyle.PixelMetric.PM_TextCursorWidth
            and isinstance(widget, QLineEdit)
            and retro_console(widget)
        ):
            return max(6, widget.fontMetrics().horizontalAdvance(" "))
        return super().pixelMetric(metric, option, widget)


def apply_theme(app: QApplication) -> None:
    from cephvr.gui.wheel_guard import install_wheel_guard

    install_wheel_guard(app)
    app.setStyle(EditorCursorStyle("Fusion"))
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS.selection))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(COLORS.text))
    app.setPalette(palette)
    font = QFont("Segoe UI")
    font.setPixelSize(SIZES.body_font)
    app.setFont(font)
    app.setStyleSheet(stylesheet())
