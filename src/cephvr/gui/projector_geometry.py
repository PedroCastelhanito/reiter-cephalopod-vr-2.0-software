"""Rig geometry drafts and physical screen placement; no rendering ownership."""

import math
from dataclasses import dataclass

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import QGridLayout, QLineEdit, QSizePolicy, QVBoxLayout, QWidget

from cephvr.gui.components import Card, field, label
from cephvr.gui.device_panel import entry
from cephvr.gui.editing_card import EditingRow, EditingSurface
from cephvr.gui.theme import SIZES
from cephvr.visual_stimulus.configuration import load_projection_settings

FACES = ("Front", "Left", "Right", "Bottom")
FRAME_GAP_MM = 5.0


@dataclass(frozen=True)
class RigDimensions:
    width: float
    depth: float
    height: float
    subject: tuple[float, float, float]


def screen_corners(
    rig: RigDimensions,
    face: str,
    values: dict[str, str],
    *,
    front_distance: str = "",
    bottom_distance: str = "",
) -> list[tuple[float, float, float]]:
    """Place inward-facing planes with frame gaps and Bottom image width along tank depth."""
    sw, sh, distance = (
        float(values.get(key, "")) for key in ("width", "height", "subject_distance")
    )
    if not all(math.isfinite(v) and v > 0 for v in (sw, sh, distance)):
        raise ValueError(f"Set positive dimensions and subject distance for {face}")
    x, y, z = rig.subject
    front = distance if face == "Front" else float(front_distance)
    if not math.isfinite(front) or front <= 0:
        raise ValueError("Set a positive subject distance for Front")
    front_y = y - front
    bottom = distance if face == "Bottom" else float(bottom_distance)
    if not math.isfinite(bottom) or bottom <= 0:
        raise ValueError("Set a positive subject distance for Bottom")
    wall_z = z - bottom + FRAME_GAP_MM + sh / 2
    inset_y = front_y + FRAME_GAP_MM
    centers = {
        "Front": (rig.width / 2, front_y, wall_z),
        "Left": (x - distance, inset_y + sw / 2, wall_z),
        "Right": (x + distance, inset_y + sw / 2, wall_z),
        "Bottom": (rig.width / 2, inset_y + sw / 2, z - distance),
    }
    right, up = {
        "Front": ((-1, 0, 0), (0, 0, 1)),
        "Left": ((0, 1, 0), (0, 0, 1)),
        "Right": ((0, -1, 0), (0, 0, 1)),
        "Bottom": ((0, 1, 0), (-1, 0, 0)),
    }[face]
    return [
        (
            centers[face][0] + u * sw / 2 * right[0] + v * sh / 2 * up[0],
            centers[face][1] + u * sw / 2 * right[1] + v * sh / 2 * up[1],
            centers[face][2] + u * sw / 2 * right[2] + v * sh / 2 * up[2],
        )
        for u, v in ((-1, -1), (1, -1), (1, 1), (-1, 1))
    ]


def resolved_screens(
    rig: RigDimensions | None, screens: dict[str, dict[str, str]]
) -> dict[str, dict[str, str]]:
    """Mirror the left screen's tank-wall offset; never reuse a stale right distance."""
    result = {face: dict(values) for face, values in screens.items()}
    distance = ""
    if rig is not None:
        try:
            left = float(screens["Left"].get("subject_distance", ""))
            right = rig.width + left - 2 * rig.subject[0]
            if math.isfinite(left) and math.isfinite(right) and min(left, right) > 0:
                distance = str(right)
        except ValueError:
            pass
    result["Right"]["subject_distance"] = distance
    return result


class RigGeometryEditor(Card):
    changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__("Rig geometry")
        self.body.setSpacing(SIZES.group_gap)
        self.tank_group = EditingRow("Tank")
        self.subject_group = EditingRow("Subject position")
        self.distance_group = EditingRow("Subject to screens")
        self.body.setSpacing(12)
        self.fields: dict[str, QLineEdit] = {}
        grids = (QGridLayout(), QGridLayout())
        for i, (key, title) in enumerate(
            (
                ("width", "TANK WIDTH (mm)"),
                ("depth", "DEPTH (mm)"),
                ("height", "HEIGHT (mm)"),
                ("subject_x", "SUBJECT →\nLEFT WALL (mm)"),
                ("subject_y", "SUBJECT →\nFRONT WALL (mm)"),
                ("subject_z", "SUBJECT →\nBOTTOM (mm)"),
            )
        ):
            edit = entry("mm")
            edit.setAccessibleName(title)
            edit.textChanged.connect(self.changed)
            self.fields[key] = edit
            grid = grids[i // 3]
            grid.addWidget(field(title, edit), 0, i % 3)
            grid.setColumnStretch(i % 3, 1)
        for group, grid in zip(
            (self.tank_group, self.subject_group), grids, strict=True
        ):
            group.body.addLayout(grid)
            self.body.addWidget(group)
        self.screen_distances: dict[str, QLineEdit] = {}
        distances = QGridLayout()
        for i, face in enumerate(("Left", "Front", "Bottom")):
            edit = entry("mm")
            edit.setAccessibleName(f"Subject to {face.lower()} screen distance")
            self.screen_distances[face] = edit
            distances.addWidget(
                field(
                    f"SUBJECT →\n{face.upper()} SCREEN (mm)",
                    edit,
                    hint="Perpendicular distance from subject to screen plane",
                ),
                0,
                i,
            )
            distances.setColumnStretch(i, 1)
        self.distance_group.body.addLayout(distances)
        self.body.addWidget(self.distance_group)

    def dimensions(self) -> RigDimensions | None:
        try:
            values = [float(edit.text()) for edit in self.fields.values()]
            if not all(math.isfinite(v) for v in values):
                return None
            w, d, h, x, y, z = values
            if min(w, d, h) <= 0 or not (0 < x < w and 0 < y < d and 0 < z < h):
                return None
            return RigDimensions(w, d, h, (x, y, z))
        except ValueError:
            return None

    def geometry_payload(self, screens: dict[str, dict[str, str]]) -> dict[str, object]:
        """Build frame-separated parallel planes; calibrated meshes remain separate."""
        rig = self.dimensions()
        if rig is None:
            raise ValueError(
                "Set positive tank dimensions and an interior subject position"
            )
        limits = load_projection_settings()
        surfaces = []
        screens = resolved_screens(rig, screens)
        for face in FACES:
            corners = screen_corners(
                rig,
                face,
                screens[face],
                front_distance=screens["Front"].get("subject_distance", ""),
                bottom_distance=screens["Bottom"].get("subject_distance", ""),
            )
            surfaces.append(
                dict(
                    surface_id=face.lower(),
                    **dict(
                        zip(
                            (
                                "bottom_left_mm",
                                "bottom_right_mm",
                                "top_right_mm",
                                "top_left_mm",
                            ),
                            corners,
                            strict=True,
                        )
                    ),
                )
            )
        return dict(
            frame_id="rig-mm", observer_mm=rig.subject, surfaces=surfaces, **limits
        )


class ScreenGeometryEditor(Card):
    changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__("Screen dimensions")
        self.fields: dict[tuple[str, str], QLineEdit] = {}
        self.drafts: dict[str, dict[str, str]] = {face: {} for face in FACES}
        self.rows: dict[str, EditingSurface] = {}
        entries = (
            ("width", "WIDTH\n(mm)"),
            ("height", "HEIGHT\n(mm)"),
            ("distance", "DERIVED DIST.\n(mm)"),
        )
        self.headings = [label(title, "label", wrap=True) for _, title in entries]
        self.column_header = QWidget()
        header_grid = self.row_grid(self.column_header)
        header_grid.addWidget(label("Screen", "label"), 0, 0)
        for col, heading in enumerate(self.headings, 1):
            policy = heading.sizePolicy()
            policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
            heading.setSizePolicy(policy)
            header_grid.addWidget(heading, 0, col)
        self.body.addWidget(self.column_header)
        self.body.setSpacing(12)
        for face in FACES:
            row = EditingSurface()
            self.rows[face] = row
            grid = self.row_grid(row)
            identity = QWidget()
            identity.setFixedWidth(84)
            identity_body = QVBoxLayout(identity)
            identity_body.setContentsMargins(0, 0, 0, 0)
            identity_body.setSpacing(0)
            identity_body.addWidget(label(face, "projector-title"))
            identity_body.addWidget(row.editing_label)
            grid.addWidget(identity, 0, 0)
            for col, (key, title) in enumerate(entries, 1):
                edit = entry("—")
                edit.setMinimumWidth(0)
                edit.setAccessibleName(f"{face} {title}")
                if face == "Bottom" and key in ("width", "height"):
                    edit.setToolTip(
                        "Image X / width runs front to back along tank depth"
                        if key == "width"
                        else "Image Y / height runs across tank width"
                    )
                if key == "distance":
                    edit.setReadOnly(True)
                    edit.setToolTip(
                        "Total optical path: projector → 45° mirror → Bottom screen, in mm"
                        if face == "Bottom"
                        else "Projector-to-screen distance in mm"
                    )
                edit.textChanged.connect(
                    lambda value, f=face, k=key: self.save_value(f, k, value)
                )
                self.fields[face, key] = edit
                grid.addWidget(edit, 0, col)
            self.body.addWidget(row)
        for face in FACES:
            edit = QLineEdit(self)
            edit.setReadOnly(True)
            edit.hide()
            edit.textChanged.connect(
                lambda value, f=face: self.save_value(f, "throw", value)
            )
            self.fields[face, "throw"] = edit

    @staticmethod
    def row_grid(host: QWidget) -> QGridLayout:
        grid = QGridLayout(host)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setHorizontalSpacing(12)
        grid.setColumnMinimumWidth(0, 84)
        for col in range(1, 4):
            grid.setColumnStretch(col, 1)
        return grid

    def save_value(self, face: str, key: str, value: str) -> None:
        self.drafts[face][key] = value
        self.changed.emit()

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        grid = self.column_header.layout()
        assert grid is not None
        self.column_header.setMinimumHeight(
            grid.heightForWidth(self.column_header.width())
        )
