"""Small vector navigation icons using the shared palette."""

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from cephvr.gui.theme import COLORS

PATHS = {
    "refresh": '<path d="M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-1l2 6M4 12l2 6a7 7 0 0 0 12-1"/>',
    "camera": '<path d="M3 7h4l2-3h6l2 3h4v13H3Z"/><circle cx="12" cy="13" r="4"/>',
    "board": '<rect x="5" y="4" width="14" height="16" rx="2"/><rect x="9" y="8" width="6" height="8"/><path d="M2 8h3m-3 4h3m-3 4h3m14-8h3m-3 4h3m-3 4h3"/>',
    "signal": '<path d="M2 12h4l3-8 4 16 3-8h6"/>',
    "projector": '<rect x="2" y="6" width="20" height="12" rx="3"/><circle cx="16" cy="12" r="3"/><path d="M5 10h4m-4 4h4m-4 4v2m14-2v2"/>',
}


def device_icon(name: str) -> QIcon:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="{COLORS.accent}" stroke-width="1.6" '
        f'stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>'
    )
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)
