"""Responsive planner controls; program and history are owned by ProtocolEditor."""

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QResizeEvent, QShortcut
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QMenu,
    QSizePolicy,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.batch_create import BatchCreate
from cephvr.gui.batch_edit import BatchEdit
from cephvr.gui.components import Card, button, equal_row_height, field, label
from cephvr.gui.group_editor import GroupEditor
from cephvr.gui.notices import FormNotice
from cephvr.gui.projector_layers import ProjectorLayers
from cephvr.gui.protocol_document import node_name
from cephvr.gui.protocol_timeline import ProgramTimeline
from cephvr.gui.screen_scope import ScreenScope
from cephvr.gui.stimulus_parameters import StimulusParameters
from cephvr.gui.stimulus_presets import FILE_TYPES
from cephvr.gui.timeline_menus import StimulusSelectionMenu
from cephvr.visual_stimulus.config.models.program_model import Epoch, Fixed, Node


class PlannerControls(QWidget):
    epoch_action = pyqtSignal(str)
    source_requested = pyqtSignal(str, bool)
    layer_action = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(14)
        self.trial_card = Card("Trials")
        self.trial_card.setFixedWidth(208)
        self.trials = QListWidget()
        self.trials.setProperty("role", "trials")
        self.trials.setAccessibleName("Trials")
        self.trials.setMinimumWidth(0)
        self.trials.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.trial_card.body.addWidget(self.trials, 1)
        self.add_button = button("+")
        self.delete_trial_button = button("−")
        self.move_trial_up_button = button("↑")
        self.move_trial_down_button = button("↓")
        for control, title in (
            (self.add_button, "New trial"),
            (self.delete_trial_button, "Delete trial"),
            (self.move_trial_up_button, "Move trial earlier"),
            (self.move_trial_down_button, "Move trial later"),
        ):
            control.setAccessibleName(title)
            control.setToolTip(title)
            control.setMinimumWidth(0)
        actions = QHBoxLayout()
        actions.addWidget(self.add_button, 1)
        actions.addWidget(self.delete_trial_button, 1)
        actions.addWidget(self.move_trial_up_button, 1)
        actions.addWidget(self.move_trial_down_button, 1)
        equal_row_height(self.add_button, self.delete_trial_button)
        self.trial_card.body.addLayout(actions)
        self.undo_action, self.redo_action = (
            QAction("Undo", self),
            QAction("Redo", self),
        )
        for action, shortcuts in (
            (self.undo_action, ("Ctrl+Z", "Meta+Z")),
            (self.redo_action, ("Ctrl+Y", "Meta+Shift+Z")),
        ):
            action.setShortcuts([QKeySequence(shortcut) for shortcut in shortcuts])
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.addAction(action)
        self.timeline_card = Card("Trial timeline")
        self.output_preview_button = button("Preview")
        self.add_epoch_button = button("+ Add epoch")
        navigation = QHBoxLayout()
        self.back_button = button("← Parent")
        self.breadcrumb = label("Trial", wrap=True)
        navigation.addWidget(self.back_button)
        navigation.addWidget(self.breadcrumb, 1)
        self.timeline = ProgramTimeline()
        self._fitted_timeline_height = -1
        self.timeline_card.body.addWidget(self.timeline)
        self.timeline.height_changed.connect(self.fit_timeline_card)
        self.sequence_summary = label("")
        self.sequence_summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        actions = QHBoxLayout()
        actions.addWidget(self.sequence_summary, 1)
        self.group_button = button("Repeat / vary…")
        self.preview_button = button("Expanded sequence…")
        self.timeline_card.body.addLayout(actions)
        self.settings_card = Card("Epoch editor")
        self.modes = QTabBar()
        self.modes.addTab("Batch generate")
        self.modes.addTab("Batch edit")
        self.modes.setExpanding(False)
        self.modes.setDrawBase(False)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.modes)
        mode_row.addStretch()
        self.settings_card.body.addLayout(mode_row)
        self.settings_card.body.addSpacing(8)
        self.create_batch = BatchCreate()
        self.batch_edit = BatchEdit()
        mode_row.addWidget(self.batch_edit.batch_actions)
        self.timeline_actions = QWidget()
        self.timeline_actions.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        timeline_actions = QHBoxLayout(self.timeline_actions)
        timeline_actions.setContentsMargins(0, 0, 0, 0)
        timeline_actions.addStretch()
        timeline_actions.addWidget(self.batch_edit.epoch_actions)
        timeline_actions.addWidget(self.output_preview_button)
        self.timeline_card.header.addWidget(self.timeline_actions, 1)
        self._timeline_actions_stacked = False
        self.duplicate_epoch_button = self.batch_edit.duplicate_epoch_button
        self.remove_epoch_button = self.batch_edit.remove_epoch_button
        self.batch_edit.epoch_action.connect(self.epoch_action.emit)
        for control, keys in (
            (self.duplicate_epoch_button, ("Ctrl+D", "Meta+D")),
            (self.remove_epoch_button, ("Backspace",)),
        ):
            shortcut = QShortcut(self)
            shortcut.setKeys([QKeySequence(key) for key in keys])
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.setAutoRepeat(False)
            shortcut.activated.connect(control.click)
        self.settings_card.body.addWidget(self.create_batch)
        self.settings_card.body.addWidget(self.batch_edit)
        self.advanced = QWidget()
        self.advanced_body = QVBoxLayout(self.advanced)
        self.advanced_body.setContentsMargins(0, 0, 0, 0)
        self.advanced_body.addLayout(navigation)
        self.settings_card.body.addWidget(self.advanced)
        self.hide_details = button("Close all parameters")
        self.hide_details.clicked.connect(lambda: self.advanced.hide())
        self.advanced_body.addWidget(self.hide_details)

        self.name = QLineEdit()
        self.name.setAccessibleName("Epoch name")
        self.name.setToolTip(
            "Letters, numbers, spaces, underscores or hyphens. Spaces are saved as underscores."
        )
        self.duration = QLineEdit()
        self.duration.setAccessibleName("Epoch duration in seconds")
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(field("Epoch", self.name), 1)
        row.addWidget(field("Shared duration (s)", self.duration), 1)
        self.epoch_fields = QWidget()
        self.epoch_fields.setLayout(row)
        self.advanced_body.addWidget(self.epoch_fields)
        self.projector_layers = ProjectorLayers()
        self.context = label("", "label", wrap=True)
        self.advanced_body.addWidget(self.context)
        self.details = label("", wrap=True)
        self.advanced_body.addWidget(self.details)
        self.scope_controls = ScreenScope()
        self.advanced_body.addWidget(self.scope_controls)
        self.parameters = StimulusParameters()
        self.advanced_body.addWidget(self.parameters)
        self.group_editor = GroupEditor()
        self.advanced_body.addWidget(self.group_editor)
        self.feedback = FormNotice()
        self.feedback.hide()
        self.settings_card.body.addWidget(self.feedback)
        self.management = QGridLayout()
        self.layer_button = button("Layers…")
        self.management_buttons = (
            self.layer_button,
            self.group_button,
            self.preview_button,
        )
        for index, control in enumerate(self.management_buttons):
            self.management.addWidget(control, 0, index)
        self.advanced_body.addLayout(self.management)
        self.add_epoch_button.hide()
        self.modes.setCurrentIndex(1)
        self.modes.currentChanged.connect(self.arrange_mode)
        self.arrange_mode()
        self.grid.addWidget(self.trial_card, 0, 0)
        self.grid.addWidget(self.timeline_card, 0, 1)
        self.grid.addWidget(self.settings_card, 1, 0, 1, 2)
        self.grid.setColumnStretch(1, 1)
        self.grid.setRowStretch(2, 1)
        for editor in (self.name, self.duration):
            editor.setMinimumWidth(0)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        size = super().minimumSizeHint()
        size.setWidth(0)
        return size

    def resizeEvent(self, event: QResizeEvent | None) -> None:  # noqa: N802
        super().resizeEvent(event)
        # Keep all timeline actions readable when the slim Trials column leaves less room.
        stacked = self.width() < 700
        for index, control in enumerate(self.management_buttons):
            self.management.removeWidget(control)
            self.management.addWidget(
                control, index if stacked else 0, 0 if stacked else index
            )
        if stacked == self._timeline_actions_stacked:
            return
        self._timeline_actions_stacked = stacked
        if stacked:
            self.timeline_card.header.removeWidget(self.timeline_actions)
            self.timeline_card.body.insertWidget(1, self.timeline_actions)
        else:
            self.timeline_card.body.removeWidget(self.timeline_actions)
            self.timeline_card.header.addWidget(self.timeline_actions, 1)
        self._fitted_timeline_height = -1
        self.fit_timeline_card()

    def fit_timeline_card(self) -> None:
        """Keep aligned cards tall enough for all trial projector/layer details."""
        if self.timeline.height() == self._fitted_timeline_height:
            return
        self.timeline_card.ensurePolished()
        self.sequence_summary.ensurePolished()
        self.timeline_card.body.invalidate()
        height = self.timeline_card.body.sizeHint().height()
        self.timeline_card.setFixedHeight(height)
        self.trial_card.setFixedHeight(height)
        self._fitted_timeline_height = self.timeline.height()

    def bind_metadata(self, node: Node) -> None:
        self.name.setText(node_name(node).replace("_", " "))
        fixed = isinstance(node, Epoch) and isinstance(node.duration, Fixed)
        self.duration.setReadOnly(not fixed)
        self.duration.setText(
            node.duration.duration.seconds
            if isinstance(node, Epoch) and isinstance(node.duration, Fixed)
            else "Variable / group"
        )
        self.name.setReadOnly(True)
        self.epoch_fields.setVisible(isinstance(node, Epoch))

    def install_menus(self) -> None:
        menu = QMenu(self.add_epoch_button)
        action = menu.addAction("Blank interval")
        assert action is not None
        action.triggered.connect(lambda: self.epoch_action.emit("add"))
        for preset in FILE_TYPES:
            action = menu.addAction(preset.replace("Looming image", "Looming") + "…")
            assert action is not None
            action.triggered.connect(
                lambda checked=False, name=preset: self.source_requested.emit(
                    name, True
                )
            )
        self.add_epoch_button.setMenu(menu)
        menu = self.epoch_menu = QMenu(self.timeline)
        self.timeline.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.timeline.customContextMenuRequested.connect(
            lambda point, context_menu=menu: (
                context_menu.popup(self.timeline.mapToGlobal(point))
                if self.isEnabled()
                else None
            )
        )
        rename = menu.addAction("Rename epoch")
        assert rename is not None
        self.rename_action = rename
        self.rename_action.triggered.connect(self.rename_epoch)
        self.selection_menu = StimulusSelectionMenu(self)
        menu.addMenu(self.selection_menu)
        for caption, operation in (
            ("Move earlier", "earlier"),
            ("Move later", "later"),
        ):
            action = menu.addAction(caption)
            assert action is not None
            action.triggered.connect(
                lambda checked=False, op=operation: self.epoch_action.emit(op)
            )
        menu = self.layer_menu = QMenu(self.layer_button)
        self.layer_button.setMenu(menu)
        for preset in FILE_TYPES:
            action = menu.addAction(preset.replace("Looming image", "Looming") + "…")
            assert action is not None
            action.triggered.connect(
                lambda checked=False, name=preset: self.source_requested.emit(
                    name, False
                )
            )
        menu.addSeparator()
        for caption, operation in (
            ("Remove selected layer", "remove"),
            ("Move layer forward", "forward"),
            ("Move layer backward", "backward"),
        ):
            action = menu.addAction(caption)
            assert action is not None
            action.triggered.connect(
                lambda checked=False, op=operation: self.layer_action.emit(op)
            )

    def arrange_mode(self) -> None:
        create = self.modes.currentIndex() == 0
        self.create_batch.setVisible(create)
        self.batch_edit.setVisible(not create)
        self.batch_edit.batch_actions.setVisible(not create)
        self.advanced.hide()

    def rename_epoch(self) -> None:
        self.modes.setCurrentIndex(1)
        self.advanced.show()
        self.name.setReadOnly(False)
        self.name.setFocus()
        self.name.selectAll()
