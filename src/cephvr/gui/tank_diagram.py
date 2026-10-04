"""Rotatable operator view of physical screens and ideal centered projector cones."""

import math
from typing import cast

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen, QPolygonF
from PyQt6.QtWidgets import QWidget

from cephvr.gui.projector_geometry import FACES, RigDimensions, screen_corners
from cephvr.gui.projector_optics import (
    Point3,
    ProjectionFootprint,
    bottom_mirror_footprint,
    projection_footprint,
)
from cephvr.gui.theme import COLORS, SIZES


class TankDiagram(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.rig: RigDimensions | None = None
        self.identifiers: dict[str, str] = {}
        self.screens: dict[str, dict[str, str]] = {}
        self.aspects: dict[str, float] = {}
        self.enabled_faces: tuple[str, ...] = ()
        self.projection_issues: dict[str, str] = {}
        self.azimuth = 45.0
        self.elevation = 25.0
        self.drag_origin: QPointF | None = None
        self.visible_elements = {
            key: True
            for key in (
                "tank",
                "screens",
                "projection",
                "subject",
                "labels",
            )
        }
        self.setMinimumHeight(150)
        self.setAccessibleName("Tank, screens and projector footprints")
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(260, 265)

    def set_element_visible(self, key: str, visible: bool) -> None:
        self.visible_elements[key] = visible
        self.update()

    def draw_legend(self, painter: QPainter) -> float:
        font = painter.font()
        font.setPointSize(SIZES.label_font)
        painter.setFont(font)
        x, y = 8.0, 14.0
        for key, title, color, marker in (
            ("tank", "Tank", COLORS.muted, "line"),
            ("screens", "Screens", COLORS.accent, "line"),
            ("projection", "Projection", COLORS.projection, "optics"),
            ("subject", "Subject", COLORS.text, "dot"),
        ):
            if not self.visible_elements[key]:
                continue
            extent = painter.fontMetrics().horizontalAdvance(title) + 32
            if x + extent > self.width() - 5 and x > 8:
                x, y = 8, y + 20
            painter.setPen(
                QPen(
                    QColor(color),
                    1.5,
                    Qt.PenStyle.DashLine if marker == "dash" else Qt.PenStyle.SolidLine,
                )
            )
            if marker == "optics":
                painter.drawLine(QPointF(x, y - 4), QPointF(x + 13, y - 4))
                painter.setBrush(QColor(COLORS.projection))
                painter.drawEllipse(QPointF(x + 2, y - 4), 2, 2)
                painter.setPen(QPen(QColor(COLORS.footprint), 1.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(QRectF(x + 9, y - 8, 5, 8))
                painter.setPen(QColor(color))
            elif marker == "dot":
                painter.setBrush(QColor(color))
                painter.drawEllipse(QPointF(x + 6, y - 4), 2.5, 2.5)
            else:
                painter.drawLine(QPointF(x, y - 4), QPointF(x + 13, y - 4))
            painter.drawText(QPointF(x + 18, y), title)
            x += extent
        return y + 8

    def screen_planes(self) -> dict[str, list[Point3]]:
        if self.rig is None:
            return {}
        faces = {}
        for face in FACES:
            try:
                faces[face] = screen_corners(
                    self.rig,
                    face,
                    self.screens.get(face, {}),
                    front_distance=self.screens.get("Front", {}).get(
                        "subject_distance", ""
                    ),
                )
            except ValueError:
                continue
        return faces

    def footprints(
        self, faces: dict[str, list[Point3]]
    ) -> dict[str, ProjectionFootprint]:
        projections = {}
        self.projection_issues.clear()
        for face, corners in faces.items():
            if face not in self.enabled_faces or face not in self.aspects:
                continue
            values = self.screens[face]
            try:
                if face == "Bottom":
                    if "Right" not in faces:
                        raise ValueError(
                            "Set Right screen geometry to locate the Bottom projector"
                        )
                    projections[face] = bottom_mirror_footprint(
                        corners,
                        faces["Right"],
                        values.get("distance", ""),
                        values.get("throw", ""),
                        self.aspects[face],
                        self.screens["Right"].get("distance", ""),
                    )
                    if projections[face].warning:
                        self.projection_issues[face] = projections[face].warning
                    continue
                projections[face] = projection_footprint(
                    corners,
                    values.get("distance", ""),
                    values.get("throw", ""),
                    self.aspects[face],
                )
            except ValueError as exc:
                self.projection_issues[face] = str(exc)
        return projections

    def refresh(self) -> None:
        footprints = self.footprints(self.screen_planes())
        descriptions = [
            "Drag to rotate · Double-click to reset view",
            "Ideal centered projection; no lens shift or optical correction",
        ]
        descriptions.extend(
            f"{face}: {p.width:g} × {p.height:g} mm" for face, p in footprints.items()
        )
        descriptions.append(
            "Bottom uses total projector → 45° mirror → screen distance; projector sits beneath Right; pyramid starts at the mirror center as a schematic; mirror outline is the required beam intercept area"
        )
        descriptions.extend(
            f"{face}: {issue}" for face, issue in self.projection_issues.items()
        )
        self.setToolTip("\n".join(descriptions))
        self.update()

    def mousePressEvent(self, event: QMouseEvent | None) -> None:  # noqa: N802
        if event is None:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_origin = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:  # noqa: N802
        if event is None:
            return
        if self.drag_origin is not None:
            delta = event.position() - self.drag_origin
            self.azimuth = (self.azimuth + delta.x() * 0.5) % 360
            self.elevation = max(-80.0, min(80.0, self.elevation + delta.y() * 0.5))
            self.drag_origin = event.position()
            self.update()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:  # noqa: N802
        if event is None:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_origin = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent | None) -> None:  # noqa: N802
        if event is None:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.azimuth, self.elevation = 45.0, 25.0
            self.drag_origin = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.update()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def paintEvent(self, event: QPaintEvent | None) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(COLORS.muted))
        if self.rig is None:
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Set tank size and subject position",
            )
            return
        rig = self.rig
        legend_height = self.draw_legend(painter)
        w, d, h = rig.width, rig.depth, rig.height
        tank: tuple[list[Point3], ...] = (
            [(0, 0, 0), (w, 0, 0), (w, d, 0), (0, d, 0)],
            [(0, 0, 0), (0, d, 0), (0, d, h), (0, 0, h)],
            [(w, 0, 0), (w, d, 0), (w, d, h), (w, 0, h)],
            [(0, 0, 0), (w, 0, 0), (w, 0, h), (0, 0, h)],
        )
        faces = self.screen_planes()
        projections = self.footprints(faces)
        yaw, pitch = math.radians(self.azimuth), math.radians(self.elevation)

        def raw(p: Point3) -> tuple[float, float, float]:
            x, y, z = p
            across = x * math.cos(yaw) - y * math.sin(yaw)
            away = x * math.sin(yaw) + y * math.cos(yaw)
            return (
                across,
                away * math.sin(pitch) - z * math.cos(pitch),
                away * math.cos(pitch) + z * math.sin(pitch),
            )

        points = [p for corners in (*faces.values(), *tank) for p in corners]
        points.extend(
            p
            for projection in projections.values()
            for p in (
                *projection.corners,
                *projection.mirror,
                projection.projector,
                *((projection.mirror_center,) if projection.mirror_center else ()),
            )
        )
        projected = [raw(p) for p in points]
        min_x, max_x = min(p[0] for p in projected), max(p[0] for p in projected)
        min_y, max_y = min(p[1] for p in projected), max(p[1] for p in projected)
        scale = max(
            0.01,
            min(
                (self.width() - 70) / max(1, max_x - min_x),
                (self.height() - legend_height - 30) / max(1, max_y - min_y),
            ),
        )

        def point(p: Point3) -> QPointF:
            px, py, _ = raw(p)
            return QPointF(
                self.width() / 2 + (px - (max_x + min_x) / 2) * scale,
                (self.height() + legend_height) / 2
                + (py - (max_y + min_y) / 2) * scale,
            )

        amber = QColor(COLORS.projection)
        painter.setPen(QPen(QColor(COLORS.muted), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.visible_elements["tank"]:
            for corners in tank:
                painter.drawPolygon(QPolygonF([point(p) for p in corners]))
        for face in sorted(
            faces, key=lambda f: sum(raw(p)[2] for p in faces[f]), reverse=True
        ):
            corners = faces[face]
            painter.setBrush(QColor(33, 91, 133, 25))
            painter.setPen(QColor(COLORS.accent))
            if self.visible_elements["screens"]:
                painter.drawPolygon(QPolygonF([point(p) for p in corners]))
        for projection in projections.values():
            if not self.visible_elements["projection"]:
                continue
            rays = QColor(amber)
            rays.setAlpha(65)
            painter.setPen(QPen(rays, 1, Qt.PenStyle.DashLine))
            origin = projection.mirror_center or projection.projector
            for corner in projection.corners:
                painter.drawLine(point(origin), point(corner))
            if projection.mirror_center:
                rays.setAlpha(160)
                painter.setPen(QPen(rays, 1.5, Qt.PenStyle.DashLine))
                painter.drawLine(
                    point(projection.projector), point(projection.mirror_center)
                )
                if not projection.mirror:
                    mark = point(projection.mirror_center)
                    painter.setPen(QPen(QColor(COLORS.mirror), 2))
                    painter.drawLine(mark + QPointF(-5, 5), mark + QPointF(5, -5))
            if projection.mirror:
                mirror_color = QColor(COLORS.mirror)
                painter.setPen(QPen(mirror_color, 1.5))
                mirror_color.setAlpha(35)
                painter.setBrush(mirror_color)
                painter.drawPolygon(QPolygonF([point(p) for p in projection.mirror]))
            painter.setPen(
                QPen(
                    QColor(COLORS.footprint),
                    1.5,
                    Qt.PenStyle.DashLine
                    if projection.warning
                    else Qt.PenStyle.SolidLine,
                )
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(QPolygonF([point(p) for p in projection.corners]))
            painter.setPen(amber)
            painter.setBrush(amber)
            painter.drawEllipse(point(projection.projector), 3, 3)
        font = painter.font()
        font.setPointSize(SIZES.label_font)
        painter.setFont(font)
        occupied: list[QRectF] = []

        def draw_label(anchor: QPointF, text: str, color: str) -> None:
            if not self.visible_elements["labels"]:
                return
            metrics = painter.fontMetrics()
            bounds = metrics.boundingRect(text)
            area = QRectF(self.rect()).adjusted(3, legend_height, -3, -3)
            box = QRectF()
            for step in range(24):
                dx = 8 if step % 2 == 0 else -bounds.width() - 8
                offset = (step // 4) * (bounds.height() + 5)
                dy = -bounds.height() - 5 - offset if step % 4 < 2 else 5 + offset
                box = QRectF(
                    anchor.x() + dx,
                    anchor.y() + dy,
                    bounds.width() + 6,
                    bounds.height() + 4,
                )
                box.moveLeft(
                    max(area.left(), min(box.left(), area.right() - box.width()))
                )
                box.moveTop(
                    max(area.top(), min(box.top(), area.bottom() - box.height()))
                )
                if not any(box.intersects(other) for other in occupied):
                    break
            occupied.append(box.adjusted(-2, -2, 2, 2))
            painter.setPen(QPen(QColor(COLORS.muted), 0.7))
            painter.drawLine(anchor, box.center())
            background = QColor(COLORS.card)
            background.setAlpha(220)
            painter.fillRect(box, background)
            painter.setPen(QColor(color))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

        for face, corners in faces.items():
            if not self.visible_elements["screens"]:
                continue
            screen_center = cast(
                Point3, tuple(sum(p[i] for p in corners) / 4 for i in range(3))
            )
            draw_label(
                point(screen_center),
                f"{face} · {self.identifiers.get(face, '—')}",
                COLORS.text if face in self.enabled_faces else COLORS.muted,
            )
        for face, projection in projections.items():
            if self.visible_elements["projection"]:
                draw_label(
                    point(projection.projector), f"{face} projector", COLORS.projection
                )
            if projection.mirror_center and self.visible_elements["projection"]:
                draw_label(point(projection.mirror_center), "45° mirror", COLORS.mirror)
        painter.setBrush(QColor(COLORS.text))
        painter.setPen(QColor(COLORS.text))
        subject = point(rig.subject)
        if self.visible_elements["subject"]:
            painter.drawEllipse(subject, 4, 4)
            draw_label(subject, "Subject", COLORS.text)
