"""Responsive planner controls; program and history are owned by ProtocolEditor."""

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QResizeEvent, QShortcut
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QMenu,
    QWidget,
)

from cephvr.gui.components import Card, button, label
from cephvr.gui.notices import FormNotice
from cephvr.gui.protocol_hierarchy import ProtocolHierarchy
from cephvr.gui.protocol_timeline import ProgramTimeline
from cephvr.gui.subgroup_editor import SubgroupEditor
from cephvr.gui.trial_list import TrialList


class PlannerControls(QWidget):
    epoch_action = pyqtSignal(str)
    group_action = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(14)
        self._stacked: bool | None = None
        self.trial_card = Card("Trials")
        self.trial_card.setFixedWidth(208)
        self.trials = TrialList()
        self.trial_card.body.addWidget(self.trials, 1)
        self.add_button = self.trials.add
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
        self.hierarchy = ProtocolHierarchy()
        self.group_editor = self.hierarchy.group
        self.timeline = ProgramTimeline(details=False)
        self.timeline_card.body.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.timeline.height_changed.connect(self.fit_timeline_card)
        self.group_editor.more.toggled.connect(self.fit_timeline_card)
        self.group_editor.changed.connect(self.fit_timeline_card)
        self.sequence_summary = label("")
        self.sequence_summary.setAlignment(Qt.AlignmentFlag.AlignLeft)
        actions = QHBoxLayout()
        actions.addWidget(self.sequence_summary, 1)
        self.timeline_card.body.addLayout(actions)
        self.timeline_card.body.addWidget(self.timeline)
        self.group_divider = QFrame()
        self.group_divider.setProperty("role", "section-divider")
        self.group_divider.setFixedHeight(1)
        self.timeline_card.body.addWidget(self.group_divider)
        self.group_controls = QHBoxLayout()
        self.group_controls.setSpacing(0)
        self.selected_group_label = label("Selected group", "label")
        # Top-aligned so it shares a baseline with the Group name/Repetitions captions.
        self.group_controls.addWidget(
            self.selected_group_label, 0, Qt.AlignmentFlag.AlignTop
        )
        self.group_controls.addSpacing(16)
        self.group_controls.addStretch(1)
        self.group_controls.addWidget(self.group_editor)
        self.group_controls.addSpacing(0)
        self.timeline_card.body.addLayout(self.group_controls)
        self.timeline.viewport_changed.connect(self.align_group_controls)
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
        actions.addWidget(self.output_preview_button)
        self.timeline_card.header.addWidget(self.timeline_actions)
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
        self._arrange_grid()

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        self._arrange_grid()

    def _arrange_grid(self) -> None:
        stacked = self.width() < 700
        if stacked == self._stacked:
            return
        self._stacked = stacked
        for widget in (self.trial_card, self.timeline_card, self.settings_card):
            self.grid.removeWidget(widget)
        if stacked:
            self.grid.addWidget(self.trial_card, 0, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)
            self.grid.addWidget(self.timeline_card, 1, 0, 1, 2)
            self.grid.addWidget(self.settings_card, 2, 0, 1, 2)
        else:
            self.grid.addWidget(self.trial_card, 0, 0)
            self.grid.addWidget(self.timeline_card, 0, 1)
            self.grid.addWidget(self.settings_card, 1, 0, 1, 2)
        self.grid.setColumnStretch(1, 1)
        for row in (2, 3):
            self.grid.setRowStretch(row, 0)
        self.grid.setRowStretch(3 if stacked else 2, 1)

    def minimumSizeHint(self) -> QSize:
        size = super().minimumSizeHint()
        size.setWidth(0)
        return size

    def align_group_controls(self) -> None:
        right = min(
            self.timeline.width(),
            len(self.timeline.nodes) * self.timeline.block_width()
            - self.timeline.scrollbar.value()
            - 7,
        )
        available = max(0, round(right))
        compact = available < 400
        self.selected_group_label.setVisible(not compact)
        gap = self.group_controls.itemAt(1)
        assert gap is not None
        gap_spacer = gap.spacerItem()
        assert gap_spacer is not None
        gap_spacer.changeSize(0 if compact else 16, 0)
        label_width = (
            0 if compact else self.selected_group_label.sizeHint().width() + 16
        )
        self.group_editor.setFixedWidth(
            min(
                420,
                max(0, available - label_width),
            )
        )
        item = self.group_controls.itemAt(4)
        assert item is not None
        spacer = item.spacerItem()
        assert spacer is not None
        spacer.changeSize(max(0, self.timeline.width() - available), 0)
        self.group_controls.invalidate()

    def fit_timeline_card(self) -> None:
        """Keep aligned cards tall enough for all trial projector/layer details."""
        self.timeline_card.ensurePolished()
        self.trial_card.ensurePolished()
        self.sequence_summary.ensurePolished()
        self.timeline_card.body.invalidate()
        self.trial_card.body.invalidate()
        header_height = self.output_preview_button.sizeHint().height()
        self.trial_card.caption.setFixedHeight(header_height)
        self.timeline_card.caption.setFixedHeight(header_height)
        height = max(
            self.timeline_card.body.sizeHint().height(),
            self.trial_card.body.minimumSize().height(),
        )
        for card in (self.timeline_card, self.trial_card):
            if card.minimumHeight() != height:
                card.setFixedHeight(height)

    def install_menus(self) -> None:
        self.hierarchy.contents.block_actions.add.clicked.connect(
            lambda: self.epoch_action.emit("add")
        )
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
