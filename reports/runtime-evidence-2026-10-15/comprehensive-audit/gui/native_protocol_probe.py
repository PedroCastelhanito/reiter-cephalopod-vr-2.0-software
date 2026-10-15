"""Record Qt state for the two native Protocol cases without changing behavior."""

import faulthandler
import json
import os
import sys
import threading

import pytest


def expired():
    faulthandler.dump_traceback()
    os._exit(124)


watchdog = threading.Timer(40, expired)
watchdog.daemon = True
watchdog.start()


def rectangle(value):
    return [value.x(), value.y(), value.width(), value.height()]


def widget_info(widget):
    if widget is None:
        return None
    from PyQt6.QtCore import QPoint

    return {
        "class": type(widget).__name__,
        "name": widget.objectName(),
        "title": widget.windowTitle(),
        "geometry": rectangle(widget.geometry()),
        "global_origin": [
            widget.mapToGlobal(QPoint()).x(),
            widget.mapToGlobal(QPoint()).y(),
        ],
        "visible": widget.isVisible(),
        "active": widget.isActiveWindow(),
        "visible_region_empty": widget.visibleRegion().isEmpty(),
        "size_hint": [widget.sizeHint().width(), widget.sizeHint().height()],
        "minimum_hint": [
            widget.minimumSizeHint().width(),
            widget.minimumSizeHint().height(),
        ],
    }


class Diagnostics:
    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_makereport(self, item, call):
        result = yield
        if result.when != "call":
            return result
        from PyQt6.QtCore import QPoint
        from PyQt6.QtGui import QCursor
        from PyQt6.QtWidgets import QApplication, QWidget

        window = item.funcargs["window"]
        app = item.funcargs["app"]
        editor = window.protocol.editor
        contents = editor.hierarchy.contents
        target = (
            contents.batch_hits[0][0].center().toPoint()
            if contents.batch_hits
            else contents.rect().center()
        )
        target_global = contents.mapToGlobal(target)
        chain = []
        ancestor = contents
        while ancestor is not None:
            chain.append(
                {
                    **widget_info(ancestor),
                    "target_in_visible_region": ancestor.visibleRegion().contains(
                        ancestor.mapFromGlobal(target_global)
                    ),
                }
            )
            ancestor = ancestor.parentWidget()
        cards = {}
        for name in ("trial_card", "timeline_card"):
            card = getattr(editor, name)
            children = []
            for child in card.findChildren(QWidget):
                if child.isVisible():
                    origin = child.mapTo(card, QPoint())
                    children.append(
                        {
                            **widget_info(child),
                            "inside_card": card.rect().contains(
                                child.rect().translated(origin)
                            ),
                        }
                    )
            cards[name] = {
                **widget_info(card),
                "body_geometry": rectangle(card.body.geometry()),
                "body_size_hint": [
                    card.body.sizeHint().width(),
                    card.body.sizeHint().height(),
                ],
                "children": children,
            }
        screen = window.screen()
        report = {
            "test": item.name,
            "outcome": result.outcome,
            "active_window": widget_info(app.activeWindow()),
            "focus_widget": widget_info(app.focusWidget()),
            "modal": widget_info(app.activeModalWidget()),
            "popup": widget_info(app.activePopupWidget()),
            "target_global": [target_global.x(), target_global.y()],
            "cursor": [QCursor.pos().x(), QCursor.pos().y()],
            "widget_at_target": widget_info(QApplication.widgetAt(target_global)),
            "screen_geometry": rectangle(screen.geometry()),
            "available_geometry": rectangle(screen.availableGeometry()),
            "logical_dpi": screen.logicalDotsPerInch(),
            "device_pixel_ratio": screen.devicePixelRatio(),
            "font": {"family": app.font().family(), "points": app.font().pointSizeF()},
            "target_parent_chain": chain,
            "cards": cards,
            "top_levels": [
                widget_info(value)
                for value in QApplication.topLevelWidgets()
                if value.isVisible()
            ],
        }
        print(json.dumps(report), flush=True)
        return result


try:
    code = pytest.main(
        [
            *(
                sys.argv[2:]
                or [
                    "tests/gui/test_dashboard.py::test_inline_timeline_actions_target_blocks_append_and_preserve_undo",
                    "tests/gui/test_dashboard.py::test_trial_row_actions_scroll_target_and_align_cards",
                ]
            ),
            "-vv",
            "-s",
            "--basetemp=" + sys.argv[1],
            "-o",
            "faulthandler_timeout=15",
        ],
        plugins=[Diagnostics()],
    )
finally:
    watchdog.cancel()
raise SystemExit(code)
