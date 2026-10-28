"""Assemble the family-specific forms for one stimulus layer, as explicit data."""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QWidget

from cephvr.gui.advanced_appearance import AdvancedAppearance
from cephvr.gui.arena_limits import ArenaLimits
from cephvr.gui.arena_movement import ArenaMovement
from cephvr.gui.components import field as labelled_field
from cephvr.gui.epoch_motion import EpochMotion
from cephvr.gui.feedback_mappings import FeedbackMappings
from cephvr.gui.grating_appearance import GratingAppearance
from cephvr.gui.grating_motion import GratingMotion
from cephvr.gui.image_parameters import ImageParameters
from cephvr.gui.initial_pose import initial_pose_fields
from cephvr.gui.looming_size import LoomingSize
from cephvr.gui.stimulus_form import ValueEditor
from cephvr.gui.stimulus_scope import set_surfaces
from cephvr.visual_stimulus.config.models.program_model import (
    Epoch,
    Program,
    Settings,
)

SECTIONS = (
    ("Motion", ("motion", "phase_x", "phase_y")),
    ("Playback", ("initial_playback", "end_behavior")),
)
RETAIN_HINT = (
    "Continue position and phase from the previous epoch. Unchecked resets to "
    "initial values. Explicit saved assignments still apply."
)


@dataclass
class Parts:
    """Forms that read back into the setting and widgets to place around them."""

    forms: list[Any] = field(default_factory=list)
    primary: list[QWidget] = field(default_factory=list)
    hidden: list[QWidget] = field(default_factory=list)


@dataclass(frozen=True)
class Binding:
    """The selected layer's model values, shared by the form builders."""

    program: Program
    node: Epoch
    setting: Settings
    values: dict[str, Any]
    schema: dict[str, Any]
    definitions: dict[str, Any]
    looming: bool
    uniform: bool
    sparse: bool
    compact: bool

    @classmethod
    def create(
        cls, program: Program, node: Epoch, layer_index: int, *, compact: bool
    ) -> "Binding":
        setting = node.settings[layer_index]
        schema = type(setting).model_json_schema()
        values = setting.model_dump(mode="json")
        return cls(
            program,
            node,
            setting,
            values,
            schema,
            schema.get("$defs", {}),
            values["kind"] == "image"
            and any(values[k]["kind"] == "keyframes" for k in ("width", "height")),
            values["kind"] == "texture" and values.get("uniform", False),
            values["kind"] == "sparse_noise",
            compact,
        )

    def motion_values(self, projector: str) -> dict[str, Any]:
        result = deepcopy(self.values)
        if projector and self.values["kind"] != "arena":
            set_surfaces(result, [projector.lower()])
        return result


def primary_parts(
    b: Binding, motion_values: dict[str, Any], projector: str, duration: object
) -> Parts:
    """Motion/playback, grating colours, uniform colour, arena and looming forms."""
    parts = Parts()
    values = b.values
    for name, fields in SECTIONS:
        if b.uniform or b.sparse:
            continue
        if name == "Motion" and values["kind"] == "image" and not b.looming:
            continue
        keys = [
            key
            for key in fields
            if key in values
            and not (key == "space" and projector)
            and not (b.looming and key in ("width", "height"))
        ]
        if not keys:
            continue
        form: ValueEditor | EpochMotion | GratingMotion
        if name == "Motion":
            form = (
                GratingMotion(motion_values)
                if values.get("grating", False)
                else EpochMotion(motion_values, b.schema, b.definitions)
            )
        else:
            form = ValueEditor(
                {
                    "type": "object",
                    "properties": {key: b.schema["properties"][key] for key in keys},
                },
                {key: values[key] for key in keys},
                b.definitions,
            )
        parts.forms.append(form)
        if isinstance(form, GratingMotion):
            parts.primary.append(form)
        elif isinstance(form, EpochMotion):
            form.extra.hide()
            if not b.looming and values["kind"] not in ("video", "arena"):
                parts.primary.append(form)
            else:
                parts.hidden.append(form)
        elif name == "Playback":
            parts.primary.append(form)
    if values.get("grating", False) and values["pattern"]["kind"] != "image_tile":
        appearance = GratingAppearance(values)
        parts.forms.append(appearance)
        parts.primary.append(appearance)
    if b.uniform:
        color = ValueEditor(
            {
                "type": "object",
                "properties": {
                    "mean_linear_rgb": b.schema["properties"]["mean_linear_rgb"]
                },
            },
            {"mean_linear_rgb": values["mean_linear_rgb"]},
            b.definitions,
        )
        parts.forms.append(color)
        parts.primary.append(color)
    if values["kind"] == "arena":
        movement = ArenaMovement(values)
        parts.forms.append(movement)
        parts.primary.append(movement)
    if b.looming:
        size = LoomingSize(values, b.schema, b.definitions, duration)
        parts.forms.append(size)
        parts.primary.append(size)
        size.extra.hide()
    return parts


@dataclass
class AdvancedParts(Parts):
    """Advanced-card widgets in display order, plus the controls the owner wires."""

    retain: QCheckBox | None = None
    appearance: AdvancedAppearance | None = None
    arena_limits: ArenaLimits | None = None
    feedback: FeedbackMappings | None = None
    widgets: list[QWidget] = field(default_factory=list)


def advanced_parts(
    b: Binding,
    motion_values: dict[str, Any],
    *,
    duration: object,
    closed_loop: bool,
) -> AdvancedParts:
    """Retain, appearance/fades, arena limits, initial pose, image and feedback."""
    values = b.values
    parts = AdvancedParts()
    parts.retain = retain = QCheckBox("Retain state")
    retain.setToolTip(RETAIN_HINT)
    retain.setChecked(not values["reset"])
    if values["kind"] in ("video", "arena"):
        retain.hide()
    if "opacity" in values:
        parts.appearance = AdvancedAppearance(
            b.program,
            b.node,
            b.setting,
            duration,
            allow_link=not b.compact and not b.looming and values["kind"] != "video",
        )
    if parts.appearance is not None and b.compact:
        strip = QWidget()
        strip_layout = QHBoxLayout(strip)
        strip_layout.setContentsMargins(0, 0, 0, 0)
        strip_layout.setSpacing(8)
        strip_layout.addWidget(retain, 1, Qt.AlignmentFlag.AlignBottom)
        strip_layout.addWidget(parts.appearance, 3)
        parts.widgets.append(strip)
    else:
        parts.widgets.append(retain)
        if parts.appearance is not None:
            parts.widgets.append(parts.appearance)
    if values["kind"] == "arena":
        parts.arena_limits = ArenaLimits()
        parts.widgets.append(parts.arena_limits)
    if values["kind"] in ("arena", "video") or b.looming:
        center, center_field = initial_pose_fields(values, b.schema, b.definitions)
        parts.forms.append(center)
        parts.widgets.append(center_field)
    if values["kind"] == "image" and not b.looming and not b.sparse:
        image = ImageParameters(motion_values, b.schema, b.definitions)
        parts.forms.append(image)
        parts.widgets.append(image)
        if not b.compact:
            parts.primary.append(labelled_field("Fit", image.fit))
    parts.feedback = FeedbackMappings(
        b.setting,
        [channel.model_dump(mode="json") for channel in b.program.input_channels],
    )
    parts.feedback.set_closed_loop(closed_loop)
    parts.widgets.append(parts.feedback)
    return parts
