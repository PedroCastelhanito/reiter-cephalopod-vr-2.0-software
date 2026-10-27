"""Shared GUI test setup: offscreen Qt, one themed application and a hang timeout."""

import os
from pathlib import Path

import pytest

# Set before any QApplication exists, or tests open real windows on the operator
# desktop. An explicit QT_QPA_PLATFORM still wins for a deliberate native run.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from collections.abc import Callable, Iterator

from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication, QMessageBox

from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow

# Far above the slowest offscreen GUI test; turns a stalled event loop into a
# named failure with stacks instead of a silent run.
GUI_TIMEOUT_S = 120
GUI_TESTS = Path(__file__).parent


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if not config.pluginmanager.hasplugin("timeout"):
        return
    for item in items:
        if (
            GUI_TESTS in item.path.parents
            and item.get_closest_marker("timeout") is None
        ):
            item.add_marker(pytest.mark.timeout(GUI_TIMEOUT_S))


@pytest.fixture(autouse=True)
def unexpected_modals(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Fail a test whose unpatched static message box would block offscreen forever.

    The call returns NoButton (a cancel) instead of raising, because an exception
    escaping a Qt slot aborts the process. Tests expecting a dialog patch it themselves.
    """
    shown: list[str] = []

    def record(kind: str) -> Callable[..., QMessageBox.StandardButton]:
        def show(
            parent: object, title: str, text: str, *args: object, **kwargs: object
        ) -> QMessageBox.StandardButton:
            shown.append(f"{kind}: {title}: {text}")
            return QMessageBox.StandardButton.NoButton

        return show

    for kind in ("information", "warning", "critical", "question"):
        monkeypatch.setattr(QMessageBox, kind, staticmethod(record(kind)))
    yield shown
    if shown:
        pytest.fail("Unexpected modal message box: " + "; ".join(shown))


@pytest.fixture(scope="module")
def app() -> QApplication:
    result = QApplication.instance()
    if result is None:
        result = QApplication([])
    assert isinstance(result, QApplication)
    apply_theme(result)
    return result


@pytest.fixture
def window(app: QApplication) -> Iterator[DashboardWindow]:
    result = DashboardWindow(sample=True)
    ReviewControls(result)
    from cephvr.gui.protocol_document import review_program

    result.protocol.editor.set_program(review_program())
    result.show()
    app.processEvents()
    yield result
    result.close()
    result.deleteLater()
    QApplication.sendPostedEvents(result, QEvent.Type.DeferredDelete)
    app.processEvents()
