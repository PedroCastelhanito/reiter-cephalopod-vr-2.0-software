"""G02 visual tokens, shared by every frontend component."""

from dataclasses import dataclass, replace

from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication, QWidget


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
    body_font: int = 13
    label_font: int = 11
    title_font: int = 16
    console_font: int = 11
    sidebar_width: int = 166
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
RETRO_SIZES = replace(
    SIZES,
    card_radius=0,
    button_radius=0,
    field_radius=1,
    title_font=14,
    body_font=12,
    console_font=12,
)
RETRO_FONT = "'Menlo', 'Consolas', 'DejaVu Sans Mono', monospace"


def retro_console(widget: QWidget) -> bool:
    """Use the appearance of the owning frontend window for custom painting."""
    current: QWidget | None = widget
    while current is not None:
        if current.property("retroConsole") is True:
            return True
        current = current.parentWidget()
    return False


def colors_for(widget: QWidget) -> Palette:
    return RETRO_COLORS if retro_console(widget) else COLORS


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
    QLabel[role='brand'] {{ font-size: 22px; font-weight: 700; }}
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
    QFrame[role='planner-divider'] {{ background: {c.border}; border: none; }}
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
    QWidget#PreviewSources {{ background: {c.card}; border: 1px solid {c.border};
                             border-radius: {s.field_radius}px; }}
    QLabel[role='selector-heading'] {{ color: {c.accent}; font-size: {s.label_font}px;
                                       font-weight: 700; min-height: 24px; }}
    QLabel[role='selector-source'] {{ color: {c.text}; min-height: 26px; }}
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
    """


def retro_stylesheet() -> str:
    c = RETRO_COLORS
    return (
        stylesheet(c, RETRO_SIZES, RETRO_FONT)
        + f"""
    QTabBar::tab {{ border-radius: 0; }}
    QFrame[role='planner-divider'] {{ background: {c.border}; border: none; }}
    QFrame[role='card'] QLabel[role='title'] {{ color: {c.coral}; letter-spacing: 1px; font-size: 13px; }}
    QLabel[role='label'] {{ letter-spacing: 1px; }}
    QLineEdit, QComboBox {{ color: {c.text}; }}
    QPushButton {{ letter-spacing: 0.8px; }}
    QPushButton:pressed {{ background: {c.active}; border: 1px solid {c.accent}; }}
    QCheckBox::indicator {{ border-radius: 0; width: 13px; height: 13px; }}
    QCheckBox::indicator:checked {{ background: {c.ready}; border-color: {c.ready}; }}
    QRadioButton[role='status-indicator']::indicator {{ border-radius: 0; width: 8px; height: 8px; }}
    QRadioButton[role='status-indicator'] {{ min-height: 36px; }}
    QPlainTextEdit[role='console'] {{ font-family: {RETRO_FONT}; padding: 12px;
        border: 1px solid {c.input_border}; border-radius: 0; }}
    QPlainTextEdit[terminal='telemetry'] {{ color: {c.mirror}; }}
    """
    )


def retro_chrome_stylesheet() -> str:
    c = RETRO_COLORS
    return f"""
    QMainWindow, QWidget#Shell, QWidget#Page {{ background: {c.page}; }}
    QFrame#Sidebar {{ background: {c.sidebar}; border-right: 1px solid {c.border}; }}
    QFrame#Sidebar QLabel, QWidget#WindowHeader QLabel {{
        font-family: {RETRO_FONT}; color: {c.accent}; }}
    QFrame#Sidebar QLabel[role='muted'] {{ color: {c.muted}; font-size: 10px; }}
    QFrame#Sidebar QLabel[role='brand'] {{ color: {c.projection}; }}
    QFrame#Sidebar QPushButton {{ font-family: {RETRO_FONT}; font-size: 12px;
        color: {c.muted}; border-radius: 0; border: 1px solid transparent; }}
    QFrame#Sidebar QPushButton:checked {{ color: {c.accent}; background: {c.selection};
        border: 1px solid {c.border}; border-left: 3px solid {c.accent}; }}
    QFrame#Sidebar QPushButton:hover {{ background: {c.hover}; border-color: {c.focus}; }}
    QWidget#WindowHeader QPushButton {{ font-family: {RETRO_FONT}; color: {c.focus};
        background: {c.secondary}; border: 1px solid {c.input_border}; border-radius: 1px; }}
    QMenuBar, QMenu {{ font-family: {RETRO_FONT}; color: {c.text}; background: {c.sidebar}; }}
    QMenuBar {{ border-bottom: 1px solid {c.border}; }}
    QMenuBar::item, QMenu::item {{ color: {c.text}; }}
    QMenuBar::item:selected, QMenu::item:selected {{ background: {c.selection}; color: {c.accent}; }}
    QMenu {{ border: 1px solid {c.border}; }}
    """


def apply_theme(app: QApplication) -> None:
    from cephvr.gui.wheel_guard import install_wheel_guard

    install_wheel_guard(app)
    app.setStyle("Fusion")
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS.selection))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(COLORS.text))
    app.setPalette(palette)
    font = QFont("Segoe UI")
    font.setPixelSize(SIZES.body_font)
    app.setFont(font)
    app.setStyleSheet(stylesheet())
