from time import perf_counter_ns

from PyQt6.QtCore import QEvent, QObject, QTimer, QEventLoop
from PyQt6.QtGui import QCursor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget
from cephvr.gui.protocol_timeline import ProgramTimeline
from cephvr.gui.trial_list import TrialList


class _MouseMoveProbe(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.expected_global = None
        self.match_count = 0
        self.loop = None

    def eventFilter(self, receiver, event):
        if event.type() == QEvent.Type.MouseMove:
            local = event.position().toPoint()
            global_point = event.globalPosition().toPoint()
            details = {
                "receiver": type(receiver).__name__,
                "object_name": receiver.objectName() if isinstance(receiver, QWidget) else "",
                "local": (local.x(), local.y()),
                "global": (global_point.x(), global_point.y()),
                "cursor": (QCursor.pos().x(), QCursor.pos().y()),
            }
            if self.expected_global == (global_point.x(), global_point.y()):
                self.match_count += 1
                print(f"MATCHING_MOUSE_MOVE {details!r}", flush=True)
                if self.loop is not None:
                    self.loop.quit()
            else:
                print(f"OTHER_MOUSE_MOVE {details!r}", flush=True)
        return False


def _state(widget):
    screen = QApplication.primaryScreen()
    top_left = widget.mapToGlobal(widget.rect().topLeft())
    bottom_right = widget.mapToGlobal(widget.rect().bottomRight())
    actual = QApplication.widgetAt(QCursor.pos())
    info = {
        "widget_at_cursor": (type(actual).__name__, actual.objectName()) if actual else None,
        "widget": type(widget).__name__,
        "name": widget.objectName(),
        "visible": widget.isVisible(),
        "active": widget.isActiveWindow(),
        "size": (widget.width(), widget.height()),
        "global_rect": (top_left.x(), top_left.y(), bottom_right.x(), bottom_right.y()),
        "cursor": (QCursor.pos().x(), QCursor.pos().y()),
        "screen_available": tuple(screen.availableGeometry().getRect()) if screen else None,
    }
    owner = widget.parentWidget() if type(widget).__name__ == "QWidget" and widget.parentWidget() else widget
    if hasattr(owner, "hover_position"):
        hp = owner.hover_position
        info["hover_position"] = (hp.x(), hp.y())
        hits = getattr(owner, "batch_hits", None)
        if hits:
            info["first_batch_hit"] = tuple(hits[0][0].getRect())
    if hasattr(owner, "hover_row"):
        info["hover_row"] = owner.hover_row
    return info


def _wrap_method(cls, name, item):
    original = getattr(cls, name)
    def wrapped(self, event):
        local = event.position().toPoint() if event is not None else None
        global_point = event.globalPosition().toPoint() if event is not None else None
        print(f"WIDGET_MOUSE_MOVE {item.nodeid} class={cls.__name__} local={local!r} global={global_point!r} before={_state(self)!r}", flush=True)
        result = original(self, event)
        print(f"WIDGET_MOUSE_MOVE_AFTER {item.nodeid} class={cls.__name__} state={_state(self)!r}", flush=True)
        return result
    setattr(cls, name, wrapped)
    return original


def pytest_runtest_call(item):
    window = item.funcargs.get("window")
    app = item.funcargs.get("app")
    if window is None or app is None:
        return
    window.raise_()
    window.activateWindow()
    QTest.qWaitForWindowActive(window, 1500)
    probe = _MouseMoveProbe(app)
    filtered_widgets = [window, *window.findChildren(QWidget)]
    for watched in filtered_widgets:
        watched.installEventFilter(probe)
    originals = [(ProgramTimeline, _wrap_method(ProgramTimeline, "mouseMoveEvent", item)),
                 (TrialList, _wrap_method(TrialList, "mouseMoveEvent", item))]
    original = QTest.mouseMove

    def _tracked_mouse_move(widget, pos=None, delay=-1):
        if pos is None:
            requested = None
        else:
            g = widget.mapToGlobal(pos)
            requested = (g.x(), g.y())
        print(f"MOUSE_MOVE_BEFORE requested_global={requested!r} state={_state(widget)!r}", flush=True)
        result = original(widget, delay=delay) if pos is None else original(widget, pos, delay)
        if requested is not None:
            loop = QEventLoop()
            probe.expected_global = requested
            probe.loop = loop
            started = perf_counter_ns()
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(loop.quit)
            timer.start(1000)
            loop.exec()
            elapsed_ms = (perf_counter_ns() - started) / 1_000_000
            timer.stop()
            probe.loop = None
            probe.expected_global = None
            print(f"BOUNDED_NATIVE_EVENT_WAIT target={requested!r} matching_events={probe.match_count} elapsed_ms={elapsed_ms:.3f} state={_state(widget)!r}", flush=True)
        print(f"MOUSE_MOVE_AFTER state={_state(widget)!r}", flush=True)
        return result

    QTest.mouseMove = staticmethod(_tracked_mouse_move)
    print(f"HOVER_DIAGNOSTIC_READY {item.nodeid}", flush=True)
    item._hover_probe = probe
    item._hover_original_mouse_move = original
    item._hover_original_methods = originals
    item._hover_widgets = filtered_widgets


def pytest_runtest_teardown(item, nextitem):
    original = getattr(item, "_hover_original_mouse_move", None)
    if original is not None:
        QTest.mouseMove = staticmethod(original)
    for cls, method in getattr(item, "_hover_original_methods", []):
        setattr(cls, "mouseMoveEvent", method)
    probe = getattr(item, "_hover_probe", None)
    if probe is not None:
        for watched in getattr(item, "_hover_widgets", []):
            try:
                watched.removeEventFilter(probe)
            except RuntimeError:
                pass

