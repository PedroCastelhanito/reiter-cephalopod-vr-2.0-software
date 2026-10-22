"""Fail every uncaught Qt-slot exception in the owning test's teardown."""
import sys
import traceback
import pytest

@pytest.fixture(autouse=True)
def retained_slot_exceptions(request):
    errors = []
    previous = sys.excepthook
    def capture(kind, error, tb):
        message = ''.join(traceback.format_exception(kind, error, tb))
        errors.append(message)
        print('UNCAUGHT QT SLOT ' + request.node.nodeid + '\n' + message, flush=True)
    sys.excepthook = capture
    yield
    sys.excepthook = previous
    if errors:
        pytest.fail('Uncaught Qt-slot exception:\n' + '\n'.join(errors), pytrace=False)
