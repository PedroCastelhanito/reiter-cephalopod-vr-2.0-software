"""Count file-dialog construction during isolated unrelated hover cases."""

from PyQt6.QtWidgets import QFileDialog

_original_init = QFileDialog.__init__
_calls = 0


def _tracked_init(self, *args, **kwargs):
    global _calls
    _calls += 1
    return _original_init(self, *args, **kwargs)


def pytest_configure(config):
    QFileDialog.__init__ = _tracked_init


def pytest_unconfigure(config):
    QFileDialog.__init__ = _original_init
    print("FILE_DIALOG_CONSTRUCTIONS", _calls, flush=True)
