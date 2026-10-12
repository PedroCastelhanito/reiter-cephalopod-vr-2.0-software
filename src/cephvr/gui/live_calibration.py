"""Coalesce live scale/offset edits until exact presentation evidence arrives."""

from collections.abc import Callable

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QLineEdit

from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.calibration_profile import MonitorBinding, face_mapping
from cephvr.gui.projector_geometry import FACES
from cephvr.gui.projectors import ProjectorsPanel
from cephvr.visual_stimulus.config.calibration_adjustments import validated_adjustments
from cephvr.visual_stimulus.v1 import messages_pb2 as messages
from cephvr.visual_stimulus.v1 import runtime_pb2 as vp


class LiveCalibration(QObject):
    def __init__(
        self,
        projectors: ProjectorsPanel,
        *,
        snapshot: Callable[[], pb.Snapshot | None],
        send: Callable[..., bool],
    ) -> None:
        super().__init__(projectors)
        self.projectors = projectors
        self.snapshot = snapshot
        self.send = send
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.flush)
        self.dirty = False
        self.edited_fields: set[tuple[str, str]] = set()
        self.inflight = 0
        self.identity: tuple[str, str, int] | None = None
        projectors.calibration.adjustments_changed.connect(self.edited)

    def eligible(self, state: pb.Snapshot | None) -> bool:
        return bool(
            state is not None
            and self.projectors.can_review
            and state.session.phase == pb.SESSION_PHASE_CONFIGURATION
            and state.HasField("visual_stimulus_display")
            and state.visual_stimulus_display.HasField("calibration")
            and state.visual_stimulus_display.calibration.state
            == vp.DISPLAY_CALIBRATION_STATE_ACTIVE
            and state.visual_stimulus_display.calibration.calibration_view
            == "frame_grid"
            and state.visual_stimulus_display.calibration.controller_generation
            == state.controller_generation
            and state.visual_stimulus_display.calibration.configuration_revision
            == state.configuration.revision
        )

    def edited(self, face: str = "", key: str = "") -> None:
        if self.eligible(self.snapshot()):
            if face and key:
                self.edited_fields.add((face, key))
            self.dirty = True
            self.timer.start()

    def install(self, state: pb.Snapshot) -> None:
        if not self.eligible(state):
            self.reset()
            return
        evidence = state.visual_stimulus_display.calibration
        identity = (
            state.controller_generation,
            evidence.diagnostic_id,
            state.configuration.revision,
        )
        if self.identity is not None and self.identity != identity:
            self.reset()
        self.identity = identity
        if self.inflight and evidence.adjustment_sequence >= self.inflight:
            self.inflight = 0
            if self.dirty:
                self.timer.start()

    def flush(self) -> None:
        state = self.snapshot()
        if not self.eligible(state):
            self.reset()
            return
        if self.inflight or not self.dirty:
            return
        assert state is not None
        evidence = state.visual_stimulus_display.calibration
        try:
            for field_key in self.edited_fields:
                control = self.projectors.calibration.controls[field_key]
                assert isinstance(control, QLineEdit)
                if not control.text().strip():
                    raise ValueError("Incomplete live adjustment")
            calibration = self.projectors.calibration_files.calibration_snapshot()
            values = calibration["values"]
            assert isinstance(values, dict)
            adjustments = []
            for face in FACES:
                monitor = MonitorBinding(
                    "live",
                    0,
                    0,
                    int(values[f"screens.{face}.reference_width_px"]),
                    int(values[f"screens.{face}.reference_height_px"]),
                    0,
                    8,
                )
                vertices, _ = face_mapping(calibration, face, monitor)
                adjustments.append(
                    messages.DisplayCalibrationAdjustment(
                        mapping_id=f"diagnostic_{face.lower()}",
                        destination_xy=[
                            coordinate
                            for vertex in vertices
                            for coordinate in vertex["xy"]
                        ],
                    )
                )
            validated_adjustments(
                (item.mapping_id, item.destination_xy) for item in adjustments
            )
        except (ValueError, TypeError, KeyError):
            # Partial/invalid typing leaves the last confirmed projection visible.
            self.dirty = False
            return
        sequence = evidence.adjustment_sequence + 1
        if self.send(
            "update_display_calibration",
            expected_revision=state.configuration.revision,
            diagnostic_id=evidence.diagnostic_id,
            adjustment_sequence=sequence,
            adjustments=tuple(item.SerializeToString() for item in adjustments),
        ):
            self.inflight = sequence
            self.dirty = False
        else:
            self.dirty = False
            self.projectors.console.appendPlainText(
                "Live grid update was not sent: controller queue unavailable."
            )

    def reset(self) -> None:
        self.timer.stop()
        self.edited_fields.clear()
        self.dirty = False
        self.inflight = 0
        self.identity = None

    def finished(
        self, action: str, _command_id: str, status: str, _message: str
    ) -> None:
        if action == "update_display_calibration" and status != "completed":
            self.reset()

    def command_finished(self, action: str, success: bool, _message: str) -> None:
        if action == "update_display_calibration" and not success:
            self.reset()

    def disconnected(self, connected: bool, *_args: object) -> None:
        if not connected:
            self.reset()
