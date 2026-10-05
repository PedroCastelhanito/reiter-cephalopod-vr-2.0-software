"""Separate read-only planning playback; no experiment/device commands."""

from time import monotonic_ns

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import button, combo, label
from cephvr.gui.trial_preview_canvas import PreviewCanvas
from cephvr.gui.trial_preview_media import PreviewMedia
from cephvr.gui.trial_preview_plan import PreviewPlan
from cephvr.gui.trial_preview_rig import PreviewRig
from cephvr.gui.trial_preview_surfaces import PreviewGeometry
from cephvr.visual_stimulus.config.models.program_model import Program


class TrialPreview(QDialog):
    def __init__(
        self,
        program: Program,
        screens: tuple[str, ...],
        asset_root: str,
        geometry: PreviewGeometry,
        parent: QWidget,
        index: int = 0,
    ) -> None:
        super().__init__(parent)
        if not screens:
            raise ValueError("Enable a projector in Devices before opening Preview")
        self.plan = PreviewPlan(program)
        self.setWindowTitle("Trial preview")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(960, 720)
        self.setMinimumSize(600, 460)
        self.time_ns = self.plan.starts[min(index, len(self.plan.starts) - 1)]
        self.playing = False
        self.anchor = monotonic_ns()
        self.media = PreviewMedia(program, asset_root, self)
        self.media.changed.connect(self.update_canvases)
        body = QVBoxLayout(self)
        body.setContentsMargins(18, 18, 18, 18)
        body.setSpacing(14)
        self.canvases: dict[str, PreviewCanvas] = {}
        for face in screens:
            canvas = PreviewCanvas(face, self.media, geometry)
            canvas.setParent(self)
            canvas.hide()
            self.canvases[face] = canvas
        self.rig_view = PreviewRig(geometry, self.canvases)
        body.addWidget(self.rig_view, 1)
        self.status = label("")
        body.addWidget(self.status)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 10000)
        self.slider.setAccessibleName("Trial preview position")
        self.slider.valueChanged.connect(self.scrub)
        body.addWidget(self.slider)
        actions = QHBoxLayout()
        self.previous = button("← Epoch")
        self.previous.clicked.connect(lambda: self.move_epoch(-1))
        self.play = button("Play")
        self.play.clicked.connect(self.toggle_play)
        self.next = button("Epoch →")
        self.next.clicked.connect(lambda: self.move_epoch(1))
        self.speed = combo(("0.25×", "0.5×", "1×", "2×"))
        self.speed.setCurrentIndex(2)
        self.speed.setMaximumWidth(100)
        self.speed.setAccessibleName("Preview playback speed")
        for widget in (self.previous, self.play, self.next, self.speed):
            actions.addWidget(widget)
        actions.addStretch()
        close = button("Close")
        close.clicked.connect(self.close)
        actions.addWidget(close)
        body.addLayout(actions)
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.tick)
        self.owner = parent.window() or parent
        self.owner.installEventFilter(self)
        self.update_canvases()

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:  # noqa: N802
        if (
            watched is self.owner
            and event is not None
            and event.type() == QEvent.Type.Close
        ):
            self.close()
        return super().eventFilter(watched, event)

    def scrub(self, value: int) -> None:
        self.time_ns = min(self.plan.total_ns - 1, value * self.plan.total_ns // 10000)
        self.anchor = monotonic_ns()
        self.update_canvases()

    def move_epoch(self, delta: int) -> None:
        index = max(0, min(len(self.plan.starts) - 1, self.plan.index + delta))
        self.time_ns = self.plan.starts[index]
        self.anchor = monotonic_ns()
        self.update_canvases()

    def toggle_play(self) -> None:
        if self.time_ns >= self.plan.total_ns - 1:
            self.time_ns = 0
        self.playing = not self.playing
        if self.playing:
            self.timer.start()
        else:
            self.timer.stop()
        self.play.setText("Pause" if self.playing else "Play")
        self.anchor = monotonic_ns()
        self.update_canvases()

    def tick(self) -> None:
        parent = self.parentWidget()
        if parent is not None and not parent.isEnabled():
            self.close()
            return
        now = monotonic_ns()
        if self.playing:
            scale = (0.25, 0.5, 1, 2)[self.speed.currentIndex()]
            self.time_ns = min(
                self.plan.total_ns - 1, self.time_ns + int((now - self.anchor) * scale)
            )
            if self.time_ns == self.plan.total_ns - 1:
                self.playing = False
                self.timer.stop()
                self.play.setText("Play")
            self.update_canvases()
        self.anchor = now

    def update_canvases(self) -> None:
        layers = self.plan.seek(self.time_ns)
        epoch = self.plan.epochs[self.plan.index]
        scene = next(
            s for s in self.plan.program.scenes if s.scene_id == epoch.scene_id
        )
        local = self.time_ns - epoch.start_ns
        self.media.retain_videos(
            {
                f"{layer.setting.instance_id}:{layer.setting.asset_id}"
                for layer in layers
                if layer.setting.kind == "video"
            }
        )
        for canvas in self.canvases.values():
            canvas.present(layers, local, scene.background_linear_rgb)
        self.rig_view.invalidate_frames()
        self.status.setText(
            f"{self.plan.index + 1} / {len(self.plan.epochs)} · {epoch.source_epoch_id.replace('_', ' ')} · {self.time_ns / 1e9:.2f} / {self.plan.total_ns / 1e9:g} s"
        )
        self.slider.blockSignals(True)
        self.slider.setValue(self.time_ns * 10000 // self.plan.total_ns)
        self.slider.blockSignals(False)
        self.previous.setEnabled(self.plan.index > 0)
        self.next.setEnabled(self.plan.index < len(self.plan.epochs) - 1)

    def closeEvent(self, event: QCloseEvent | None) -> None:  # noqa: N802
        self.timer.stop()
        self.owner.removeEventFilter(self)
        self.media.close()
        super().closeEvent(event)
