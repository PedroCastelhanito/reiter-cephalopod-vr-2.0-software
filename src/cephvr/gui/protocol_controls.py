"""Responsive planner controls; program and history are owned by ProtocolEditor."""

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QResizeEvent, QShortcut
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QListWidget,
    QMenu,
    QWidget,
)

from cephvr.gui.components import Card, button, equal_row_height, label
from cephvr.gui.notices import FormNotice
from cephvr.gui.protocol_hierarchy import ProtocolHierarchy
from cephvr.gui.protocol_timeline import ProgramTimeline
from cephvr.gui.subgroup_editor import SubgroupEditor


class PlannerControls(QWidget):
    epoch_action = pyqtSignal(str)
    group_action = pyqtSignal(str)

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
        self.trials.setMinimumHeight(44)
        self.trials.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.trial_card.body.addWidget(self.trials, 1)
        self.add_button = button("+")
        self.delete_trial_button = button("−")
        for control, title in (
            (self.add_button, "New trial"),
            (self.delete_trial_button, "Delete trial"),
        ):
            control.setAccessibleName(title)
            control.setToolTip(title)
            control.setMinimumWidth(0)
        actions = QHBoxLayout()
        actions.addWidget(self.add_button, 1)
        actions.addWidget(self.delete_trial_button, 1)
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
        self.add_group_button = button("+ Group")
        self.remove_group_button = button("− Group")
        self.remove_group_button.setToolTip("Remove the selected group")
        self.hierarchy = ProtocolHierarchy()
        self.add_epoch_button = self.hierarchy.add_epoch
        self.group_editor = self.hierarchy.group
        self.timeline = ProgramTimeline(details=False)
        self.timeline_card.body.addWidget(self.timeline)
        self.timeline.height_changed.connect(self.fit_timeline_card)
        self.sequence_summary = label("")
        self.sequence_summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        actions = QHBoxLayout()
        actions.addWidget(self.sequence_summary, 1)
        self.timeline_card.body.addLayout(actions)
        self.settings_card = Card("Sequence editor")
        self.settings_card.body.addWidget(self.hierarchy)
        self.subgroup = SubgroupEditor()
        self.settings_card.body.addSpacing(8)
        self.settings_card.body.addWidget(self.subgroup)
        self.feedback = FormNotice()
        self.settings_card.body.addWidget(self.feedback)
        self.timeline_actions = QWidget()
        actions = QHBoxLayout(self.timeline_actions)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addWidget(self.add_group_button)
        actions.addWidget(self.remove_group_button)
        actions.addWidget(self.output_preview_button)
        self.timeline_card.header.addWidget(self.timeline_actions)
        self._timeline_actions_stacked = False
        for operation, keys in (
            ("duplicate", ("Ctrl+D", "Meta+D")),
            ("remove", ("Backspace",)),
        ):
            shortcut = QShortcut(self)
            shortcut.setKeys([QKeySequence(key) for key in keys])
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.setAutoRepeat(False)
            shortcut.activated.connect(
                lambda op=operation: (
                    self.group_action if self.timeline.hasFocus() else self.epoch_action
                ).emit(op)
            )
        self.grid.addWidget(self.trial_card, 0, 0)
        self.grid.addWidget(self.timeline_card, 0, 1)
        self.grid.addWidget(self.settings_card, 1, 0, 1, 2)
        self.grid.setColumnStretch(1, 1)
        self.grid.setRowStretch(2, 1)

    def minimumSizeHint(self) -> QSize:
        size = super().minimumSizeHint()
        size.setWidth(0)
        return size

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        # Keep all timeline actions readable when the slim Trials column leaves less room.
        stacked = self.width() < 700
        if stacked == self._timeline_actions_stacked:
            return
        self._timeline_actions_stacked = stacked
        if stacked:
            self.timeline_card.header.removeWidget(self.timeline_actions)
            self.timeline_card.body.insertWidget(
                1, self.timeline_actions, alignment=Qt.AlignmentFlag.AlignRight
            )
        else:
            self.timeline_card.body.removeWidget(self.timeline_actions)
            self.timeline_card.header.addWidget(self.timeline_actions)
        self.fit_timeline_card()

    def fit_timeline_card(self) -> None:
        """Keep aligned cards tall enough for all trial projector/layer details."""
        self.timeline_card.ensurePolished()
        self.trial_card.ensurePolished()
        self.sequence_summary.ensurePolished()
        self.timeline_card.body.invalidate()
        self.trial_card.body.invalidate()
        height = max(
            self.timeline_card.body.sizeHint().height(),
            self.trial_card.body.minimumSize().height(),
        )
        for card in (self.timeline_card, self.trial_card):
            if card.minimumHeight() != height:
                card.setFixedHeight(height)

    def install_menus(self) -> None:
        self.add_epoch_button.clicked.connect(lambda: self.epoch_action.emit("add"))
        self.epoch_menu = QMenu(self.timeline)
        for caption, operation in (
            ("Duplicate", "duplicate"),
            ("Delete", "remove"),
            ("Move earlier", "earlier"),
            ("Move later", "later"),
        ):
            action = self.epoch_menu.addAction(caption)
            assert action is not None
            action.triggered.connect(
                lambda checked=False, op=operation: self.epoch_action.emit(op)
            )
        self.group_menu = QMenu(self.timeline)
        for caption, operation in (
            ("Duplicate group", "duplicate"),
            ("Remove group", "remove"),
            ("Move earlier", "earlier"),
            ("Move later", "later"),
        ):
            action = self.group_menu.addAction(caption)
            assert action is not None
            action.triggered.connect(
                lambda checked=False, op=operation: self.group_action.emit(op)
            )
        for timeline in (self.timeline, self.hierarchy.contents):
            timeline.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            timeline.customContextMenuRequested.connect(
                lambda point, target=timeline: (
                    (
                        self.group_menu if target is self.timeline else self.epoch_menu
                    ).popup(target.mapToGlobal(point))
                    if self.isEnabled()
                    else None
                )
            )

    def arrange_mode(self) -> None:
        from cephvr.gui.protocol_batches import flat_group

        self.subgroup.setVisible(
            hasattr(self, "program") and flat_group(self.program, self.hierarchy.scope)
        )
