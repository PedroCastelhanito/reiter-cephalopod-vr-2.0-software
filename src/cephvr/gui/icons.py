"""Small vector navigation icons using the shared palette."""

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from cephvr.gui.theme import COLORS

PATHS = {
    "tracking": '<g transform="scale(1.2)"><path d="M2.6 8L4.4 2.4M2.7 4L4.4 2.4L4.9 4.7"/><path d="M7.4 7.7L10.6 2.8M8.5 3.7L10.6 2.8L10.3 5"/><path d="M13 7.3L17.4 3.8M15.2 3.9L17.4 3.8L16.7 5.9"/><g transform="translate(0 9)"><path d="M2.6 8L4.4 2.4M2.7 4L4.4 2.4L4.9 4.7"/><path d="M7.4 7.7L10.6 2.8M8.5 3.7L10.6 2.8L10.3 5"/><path d="M13 7.3L17.4 3.8M15.2 3.9L17.4 3.8L16.7 5.9"/></g></g>',
    "dashboard": '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
    "protocol": '<path d="M8 6h10M6 12h9M11 18h10"/>',
    "devices": '<circle cx="12" cy="19" r="2"/><path d="M12 17V3m-3 3 3-3 3 3M12 14l-5-3V8m5 4 5-3V6"/><circle cx="7" cy="7" r="1"/><rect x="16" y="3" width="2" height="3"/>',
    "configure": '<path d="M21 4h-7M10 4H3m18 8h-3m-4 0H3m18 8h-9m-4 0H3M14 2v4m4 4v4m-6 4v4"/>',
    "monitor": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
    "geometry": '<path d="m12 3 9 5v9l-9 5-9-5V8Zm-9 5 9 5 9-5M12 13v9"/>',
    "calibration": '<path d="M8 3H5a2 2 0 0 0-2 2v3m13-5h3a2 2 0 0 1 2 2v3M3 16v3a2 2 0 0 0 2 2h3m8 0h3a2 2 0 0 0 2-2v-3"/>',
    "sync": '<rect x="2" y="2" width="20" height="20"/><rect x="8" y="8" width="8" height="8"/>',
    "refresh": '<path d="M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-1l2 6M4 12l2 6a7 7 0 0 0 12-1"/>',
    "camera": '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3Z"/><circle cx="12" cy="13" r="3"/>',
    "board": '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3m6-3v3M9 20v3m6-3v3M1 9h3m-3 6h3m16-6h3m-3 6h3"/>',
    "signal": '<path d="M2 12h4l3-9 6 18 3-9h4"/>',
    "projector": '<rect x="2" y="6" width="20" height="12" rx="3"/><circle cx="16" cy="12" r="3"/><path d="M5 10h4m-4 4h4m-4 4v2m14-2v2"/>',
}


def device_icon(name: str, color: str = COLORS.accent) -> QIcon:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="1.6" '
        f'stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>'
    )
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)
