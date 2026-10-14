"""Rig geometry drafts and physical screen placement; no rendering ownership."""

import math
from dataclasses import dataclass

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QGridLayout, QHeaderView, QLineEdit, QTableWidgetItem

from cephvr.gui.components import Card, field
from cephvr.gui.device_panel import entry
from cephvr.gui.tables import DataTable
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
        self.fields: dict[str, QLineEdit] = {}
        grid = QGridLayout()
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
            grid.addWidget(field(title, edit), i // 3, i % 3)
            grid.setColumnStretch(i % 3, 1)
        self.body.addLayout(grid)
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
        self.body.addLayout(distances)

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
        self.table = DataTable(len(FACES), 4)
        entries = (
            ("width", "WIDTH\n(mm)"),
            ("height", "HEIGHT\n(mm)"),
            ("distance", "DERIVED DIST.\n(mm)"),
        )
        self.table.setHorizontalHeaderLabels(["", *(title for _, title in entries)])
        header = self.table.horizontalHeader()
        assert header is not None
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for row, face in enumerate(FACES):
            self.table.setItem(row, 0, QTableWidgetItem(face))
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
                self.table.set_control(row, col, edit)
        for face in FACES:
            edit = QLineEdit(self)
            edit.setReadOnly(True)
            edit.hide()
            edit.textChanged.connect(
                lambda value, f=face: self.save_value(f, "throw", value)
            )
            self.fields[face, "throw"] = edit
        self.table.fit_rows()
        self.body.addWidget(self.table)

    def save_value(self, face: str, key: str, value: str) -> None:
        self.drafts[face][key] = value
        self.changed.emit()
