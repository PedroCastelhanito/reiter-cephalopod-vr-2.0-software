"""Static design proposal only; does not start the GUI or read/write preferences."""

import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication

from cephvr.gui.theme import COLORS, PHOSPHOR_COLORS, RETRO_COLORS

app = QApplication([])
for font_file in ("segoeui.ttf", "segoeuib.ttf", "consola.ttf"):
    assert QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + font_file) >= 0
image = QImage(1560, 650, QImage.Format.Format_ARGB32)
image.fill(QColor("#252b32"))
p = QPainter(image)
p.setRenderHint(QPainter.RenderHint.Antialiasing)


def text(rect, value, size, color, family="Segoe UI", bold=False):
    p.setPen(QColor(color))
    font = QFont(family)
    font.setPixelSize(size)
    font.setBold(bold)
    p.setFont(font)
    p.drawText(QRectF(*rect), Qt.AlignmentFlag.AlignCenter, value)


text((0, 24, 1560, 42), "CephVR2.0 · Startup preview", 26, "#f4f7fb")
text((0, 70, 1560, 30), "The splash follows your last selected style", 17, "#b3beca")
for i, (label, palette, family) in enumerate([
    ("Standard", COLORS, "Segoe UI"),
    ("Retro console", RETRO_COLORS, "Consolas"),
    ("Amber phosphor", PHOSPHOR_COLORS, "Consolas"),
]):
    x = 30 + i * 510
    text((x, 125, 480, 32), label, 19, "#d6dfe8")
    p.setBrush(QColor(palette.window))
    p.setPen(QPen(QColor(palette.border), 1))
    p.drawRoundedRect(QRectF(x, 180, 480, 350), 14 if i == 0 else 0, 14 if i == 0 else 0)
    if i:
        p.setPen(QPen(QColor(palette.accent), 2))
        for cx, cy, sx, sy in [(x, 180, 1, 1), (x+480, 180, -1, 1), (x, 530, 1, -1), (x+480, 530, -1, -1)]:
            p.drawLine(QPointF(cx, cy+sy*16), QPointF(cx, cy))
            p.drawLine(QPointF(cx, cy), QPointF(cx+sx*16, cy))
    p.save()
    p.translate(x + 240, 286)
    # A simple vector cephalopod: mantle, eyes, and four paired curling arms.
    p.setPen(QPen(QColor(palette.accent), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    mantle = QPainterPath(QPointF(-26, 12))
    mantle.cubicTo(-48, -55, 48, -55, 26, 12)
    p.drawPath(mantle)
    for side in (-1, 1):
        for j in range(4):
            arm = QPainterPath(QPointF(side*(7+j*6), 10))
            arm.cubicTo(side*(8+j*7), 44+j*3, side*(30+j*10), 45-j*9, side*(25+j*10), 30-j*9)
            p.drawPath(arm)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(palette.text))
    p.drawEllipse(QPointF(-10, -3), 3, 3)
    p.drawEllipse(QPointF(10, -3), 3, 3)
    p.restore()
    text((x, 356, 480, 48), "CephVR2.0", 36, palette.coral if i else palette.text, family, i == 0)
    text((x, 424, 480, 30), "Initializing", 19, palette.text, family)
    p.setPen(QPen(QColor(palette.border), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(x+172, 478), QPointF(x+308, 478))
    p.setPen(QPen(QColor(palette.accent), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(x+214, 478), QPointF(x+250, 478))
text((0, 568, 1560, 32), "One splash while loading. The main window appears when ready.", 18, "#d6dfe8")
text((0, 604, 1560, 24), "Design preview · Loading indicator shown as a still frame", 14, "#a7b4c1")
p.end()
assert image.save(str(Path(__file__).with_name("startup-preview.png")))
